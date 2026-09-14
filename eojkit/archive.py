# -*- coding: utf-8 -*-
"""
eojkit.archive —— 刷题笔记归档
==============================

把题目原文、样例、代码、AI 笔记、本地测试结果写入
``eoj_solutions/{题号}/``，并维护全局 ``index.md``。

相对旧版 ``SolutionArchiver`` 的改进：

* ``index.md`` 不再用正则逐行"猜"旧内容，而是解析成字典后稳定重写，
  避免题目标题里的 ``|`` 破坏表格。
* 新增 ``meta.json``，记录生成时间、使用的模型与接入点、判题结果，
  让笔记可以追溯"这题是哪个模型写的"。
* 写入全部走"临时文件 + 原子替换"，批量刷题中途中断不会留下半截文件。
* 归档 README 时自动补一个元信息脚注（模型 / 时间 / 本地测试结论）。

Designed by HMS_Victorious
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .config import get_settings
from .tools import log_ok, timestamp

__all__ = ["SolutionArchiver", "ArchiveMeta"]

INDEX_HEADER = [
    "# EOJ 刷题记录",
    "",
    "| 题号 | 题目 | 状态 | 模型 | 更新时间 |",
    "|------|------|------|------|----------|",
]

_VERDICT_ICON = {
    "AC": "✅ AC",
    "WA": "❌ WA",
    "TLE": "⏱ TLE",
    "MLE": "💾 MLE",
    "RE": "💥 RE",
    "CE": "🚫 CE",
    "PE": "⚠️ PE",
    "OLE": "📤 OLE",
    "UNKNOWN": "❔ 未知",
    "ARCHIVED": "📚 已归档",
}


def verdict_label(verdict: Optional[str]) -> str:
    if not verdict:
        return "⬜ 未提交"
    return _VERDICT_ICON.get(str(verdict).upper(), f"🔄 {verdict}")


def _atomic_write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)


def _escape_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


#: 这些"标题"其实是页面的小标题或抓取失败的产物，不能进索引
_BAD_TITLES = {
    "", "input", "output", "sample", "samples", "example", "examples",
    "输入", "输出", "输入格式", "输出格式", "样例", "题目描述", "提示",
    "description", "hint", "note", "notes",
}


def _unescape_cell(text: str) -> str:
    """还原 ``_escape_cell``（索引表格单元格）。"""
    return (text or "").replace("\\|", "|").strip()


def _normalize_legacy_verdict(text: str) -> str:
    """把旧 index.md 的状态列（已含 emoji 或裸判词）统一成展示格式。"""
    raw = _unescape_cell(text)
    if not raw:
        return ""
    upper = raw.upper()
    for code in ("AC", "WA", "TLE", "MLE", "RE", "CE", "PE", "OLE", "UNKNOWN"):
        if code in upper:
            return verdict_label(code)
    if "未提交" in raw:
        return "⬜ 未提交"
    if "ARCHIVED" in upper:
        return "📚 已归档"
    return f"🔄 {raw}"


@dataclass
class ArchiveMeta:
    """归档元信息（写入 ``meta.json``）。"""

    problem_id: str = ""
    title: str = ""
    url: str = ""
    verdict: str = ""
    model: str = ""
    base_url: str = ""
    prompt_version: str = ""
    generated_at: str = ""
    local_tests: str = ""
    samples: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


def _strip_leading_id(title: str, problem_id) -> str:
    """去掉标题里与题号重复的前缀：``"1002. IP Address"`` → ``"IP Address"``。

    仅在笔记标题里做这件事（``# 题目 1002 - IP Address``），
    归档索引仍然保留 EOJ 的完整标题。
    """
    text = (title or "").strip()
    prefix = str(problem_id)
    for separator in (". ", "．", "、", " - ", " ", ":"):
        candidate = prefix + separator
        if text.startswith(candidate):
            stripped = text[len(candidate):].strip()
            if stripped:
                return stripped
    return text


class SolutionArchiver:
    """题目归档器。

    :param solutions_dir: 存档根目录；默认取全局配置。
    """

    def __init__(self, solutions_dir: Optional[str] = None, quiet: bool = False):
        settings = get_settings()
        self.solutions_dir = os.path.abspath(solutions_dir or settings.eoj.solutions_dir)
        self.quiet = quiet
        self.meta = ArchiveMeta(
            model=settings.llm.model,
            base_url=settings.llm.base_url,
        )
        os.makedirs(self.solutions_dir, exist_ok=True)
        if not quiet:
            log_ok(f"存档目录: {self.solutions_dir}")

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------
    def problem_dir(self, problem_id) -> str:
        path = os.path.join(self.solutions_dir, str(problem_id))
        os.makedirs(path, exist_ok=True)
        return path

    def path_for(self, problem_id, filename: str) -> str:
        return os.path.join(self.problem_dir(problem_id), filename)

    # ------------------------------------------------------------------
    # 各类产物
    # ------------------------------------------------------------------
    def save_statement(self, problem_id, problem_info: Dict) -> str:
        lines = [
            f"# {problem_info.get('title', '')}",
            f"来源: {problem_info.get('url', '')}",
            f"题号: {problem_id}",
            "",
            problem_info.get("description", ""),
            "",
            "## 样例",
        ]
        for index, sample in enumerate(problem_info.get("samples") or [], start=1):
            lines.extend(
                [
                    f"\n### 样例 {index}",
                    "输入:",
                    sample.get("input", ""),
                    "输出:",
                    sample.get("output", ""),
                ]
            )
        path = self.path_for(problem_id, "statement.txt")
        _atomic_write(path, "\n".join(lines))
        if not self.quiet:
            log_ok(f"题目描述已保存: {path}")
        return path

    def save_samples(self, problem_id, samples) -> Optional[str]:
        samples = list(samples or [])
        if not samples:
            return None
        lines: List[str] = []
        for index, sample in enumerate(samples, start=1):
            lines.extend(
                [
                    f"=== Sample {index} Input ===",
                    sample.get("input", ""),
                    f"=== Sample {index} Output ===",
                    sample.get("output", ""),
                    "",
                ]
            )
        path = self.path_for(problem_id, "samples.txt")
        _atomic_write(path, "\n".join(lines))
        if not self.quiet:
            log_ok(f"样例数据已保存: {path}")
        return path

    def save_code(self, problem_id, code: str) -> str:
        path = self.path_for(problem_id, "solution.cpp")
        _atomic_write(path, code)
        if not self.quiet:
            log_ok(f"解题代码已保存: {path}")
        return path

    def save_readme(self, problem_id, analysis_content: str, with_meta: bool = True) -> str:
        content = analysis_content or ""
        if with_meta:
            content = self._append_meta_footer(problem_id, content)
            # 若此刻已知判题结果但之前写过 README，补写一次
            content = self._sync_verdict_footer(problem_id, content)
        path = self.path_for(problem_id, "README.md")
        _atomic_write(path, content)
        if not self.quiet:
            log_ok(f"刷题笔记已保存: {path}")
        return path

    def refresh_readme_meta(self, problem_id) -> bool:
        """判题结果出来之后，刷新 README 里的元信息脚注。"""
        path = self.path_for(problem_id, "README.md")
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        updated = self._sync_verdict_footer(problem_id, content)
        if updated == content:
            return False
        _atomic_write(path, updated)
        return True

    def _sync_verdict_footer(self, problem_id, content: str) -> str:
        """在元信息脚注中补齐/更新判题结果行。"""
        verdict = self.meta.verdict
        if not verdict:
            return content

        prefix = "> EOJ 判题结果："
        line = f"{prefix}{verdict_label(verdict)}"
        lines = content.splitlines()
        for index, existing in enumerate(lines):
            if existing.startswith(prefix):
                if existing == line:
                    return content
                lines[index] = line
                return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
        # 还没有该行：插到元信息块之后
        for index, existing in enumerate(lines):
            if existing.startswith("> 🤖 由"):
                lines.insert(index + 1, line)
                return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
        return content

    def save_test_result(self, problem_id, result_text: str) -> str:
        path = self.path_for(problem_id, "test_result.txt")
        _atomic_write(path, result_text)
        if not self.quiet:
            log_ok(f"测试结果已保存: {path}")
        return path

    def save_input(self, problem_id, data: str, name: str = "input.txt") -> str:
        path = self.path_for(problem_id, name)
        _atomic_write(path, data)
        return path

    def save_meta(self, problem_id, meta: Optional[ArchiveMeta] = None) -> str:
        record = meta or self.meta
        record.problem_id = str(problem_id)
        record.generated_at = record.generated_at or timestamp()
        path = self.path_for(problem_id, "meta.json")
        _atomic_write(path, json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
        return path

    def load_meta(self, problem_id) -> Optional[Dict]:
        path = self.path_for(problem_id, "meta.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # 元信息脚注
    # ------------------------------------------------------------------
    def _append_meta_footer(self, problem_id, content: str) -> str:
        if "<!-- eojkit:meta" in content:
            return content
        settings = get_settings()
        rows = [
            "",
            "---",
            "",
            "<!-- eojkit:meta -->",
            f"> 🤖 由 **{settings.llm.model}** 生成 · "
            f"接入点 `{settings.llm.base_url}` · 更新于 {timestamp()}",
        ]
        if self.meta.verdict:
            rows.append(f"> EOJ 判题结果：{verdict_label(self.meta.verdict)}")
        if self.meta.local_tests:
            rows.append(f"> 本地测试：{self.meta.local_tests}")
        return content.rstrip() + "\n" + "\n".join(rows) + "\n"

    # ------------------------------------------------------------------
    # 索引
    # ------------------------------------------------------------------
    def parse_index(self) -> Dict[str, Dict[str, str]]:
        """解析 ``index.md``，返回 ``{题号: {title, verdict, model, updated}}``。"""
        path = os.path.join(self.solutions_dir, "index.md")
        rows: Dict[str, Dict[str, str]] = {}
        if not os.path.isfile(path):
            return rows
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            return rows

        for line in content.splitlines():
            if not line.startswith("|"):
                continue
            # 先按未转义的竖线切分，再还原单元格内部的 \|
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            title_cell = cells[1]
            match = re.match(r"\[(.*?)\]\((.*?)\)", title_cell)
            rows[cells[0]] = {
                "title": _unescape_cell(match.group(1) if match else title_cell),
                "link": match.group(2) if match else f"{cells[0]}/README.md",
                # 注意：旧版 index.md 只有三列，第 3 列是**判题状态**而不是模型。
                # 只有确认列数 >= 5 时才把后两列当作「模型 / 更新时间」，
                # 否则一律视为未知，交给 meta.json 决定（避免把 "AC" 当模型名）。
                "verdict": _normalize_legacy_verdict(cells[2]) if len(cells) > 2 else "",
                "model": cells[3] if len(cells) >= 5 else "",
                "updated": cells[4] if len(cells) >= 5 else "",
            }
        return rows

    def rebuild_index(self) -> str:
        """扫描存档目录重建 ``index.md``。

        以文件系统为**唯一真相**：标题取自 ``meta.json`` / README 首行，
        判词与模型取自 ``meta.json``。旧 ``index.md`` 只用来保留链接路径，
        不再沿用它的标题/状态列（旧格式与新格式列义不同，沿用会串味）。
        """
        rows: Dict[str, Dict[str, str]] = {}
        for entry in sorted(os.listdir(self.solutions_dir)):
            folder = os.path.join(self.solutions_dir, entry)
            if not os.path.isdir(folder) or not re.match(r"^\d+$", entry):
                continue
            meta = self.load_meta(entry) or {}
            row: Dict[str, str] = {"link": f"{entry}/README.md"}
            title = self._recover_title(entry)
            if title:
                row["title"] = title
            if meta.get("verdict"):
                row["verdict"] = verdict_label(meta["verdict"])
            if meta.get("model"):
                row["model"] = meta["model"]
            if meta.get("generated_at"):
                row["updated"] = meta["generated_at"]
            rows[entry] = row

        lines = list(INDEX_HEADER)
        for pid in sorted(rows.keys(), key=int):
            row = rows[pid]
            title = _escape_cell(row.get("title") or f"题目 {pid}")
            lines.append(
                f"| {pid} | [{title}]({row.get('link') or f'{pid}/README.md'}) | "
                f"{row.get('verdict') or '⬜ 未提交'} | {_escape_cell(row.get('model') or '-')} | "
                f"{row.get('updated') or '-'} |"
            )
        lines.append("")
        lines.append(f"*索引由 eojkit 于 {timestamp()} 生成，共 {len(rows)} 题*")
        content = "\n".join(lines) + "\n"

        path = os.path.join(self.solutions_dir, "index.md")
        _atomic_write(path, content)
        if not self.quiet:
            log_ok(f"索引已更新: {path} ({len(rows)} 题)")
        return path

    def refresh_titles(self, client, problem_ids=None, quiet: bool = False) -> Dict[str, str]:
        """从 EOJ 拉取真实题目标题，写入 ``meta.json`` 并修正 README 首行。

        旧版抓标题时会命中页面的小标题，导致存档里出现 ``# Input`` 这类
        标题（README 笔记、statement、索引全都跟着错）。这个方法做一次性修复。

        :param client: :class:`~eojkit.judge.client.EOJClient` 实例
        :return: ``{题号: 新标题}``
        """
        if problem_ids is None:
            problem_ids = sorted(
                (
                    entry
                    for entry in os.listdir(self.solutions_dir)
                    if re.match(r"^\d+$", entry)
                    and os.path.isdir(os.path.join(self.solutions_dir, entry))
                ),
                key=int,
            )

        updated: Dict[str, str] = {}
        for pid in problem_ids:
            existing = self.load_meta(pid) or {}
            old = existing.get("title", "")
            try:
                info = client.get_problem_info(pid)
            except Exception as exc:  # noqa: BLE001
                if not quiet:
                    log_warn(f"[{pid}] 拉取题目失败: {exc}")
                continue
            if not info or not info.get("title"):
                continue
            new = info["title"]

            # 只更新标题相关字段，其余既有元信息（模型、接入点、判词、时间）
            # 必须原样保留 —— 否则会把归档历史覆盖成当前全局配置。
            merged = dict(existing)
            merged.update(
                {
                    "problem_id": str(pid),
                    "title": new,
                    "url": existing.get("url") or info.get("url", ""),
                }
            )
            self.save_meta(pid, ArchiveMeta(**{
                key: value for key, value in merged.items()
                if key in ArchiveMeta.__dataclass_fields__
            }))
            self._fix_readme_title(pid, new)
            self._fix_statement_title(pid, new)
            updated[pid] = new
            if not quiet and old != new:
                log_ok(f"[{pid}] 标题: {old or '(空)'} → {new}")
            time.sleep(0.3)
        return updated

    def _fix_statement_title(self, problem_id, new_title: str) -> bool:
        """把 ``statement.txt`` 首行标题修成正确值（旧版常写成 ``# Input``）。"""
        path = self.path_for(problem_id, "statement.txt")
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            return False
        lines = content.splitlines()
        if not lines:
            return False
        first = re.sub(r"^#\s*", "", lines[0]).strip()
        if first.lower() not in _BAD_TITLES:
            return False
        lines[0] = f"# {new_title}"
        _atomic_write(path, "\n".join(lines) + ("\n" if content.endswith("\n") else ""))
        return True

    def _fix_readme_title(self, problem_id, new_title: str) -> bool:
        """把 README 首行标题修成正确值，同时修正文中的 ``# 题目 N - old``。"""
        path = self.path_for(problem_id, "README.md")
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            return False

        lines = content.splitlines()
        changed = False
        for index, line in enumerate(lines):
            if not line.startswith("#"):
                if line.strip():
                    break
                continue
            stripped = re.sub(r"^#\s*", "", line).strip()
            stripped = re.sub(r"^题目\s*\d+\s*[-–—:：]\s*", "", stripped)
            if stripped.lower() in _BAD_TITLES:
                lines[index] = f"# 题目 {problem_id} - {_strip_leading_id(new_title, problem_id)}"
                changed = True
            break

        if not changed:
            return False
        _atomic_write(path, "\n".join(lines) + ("\n" if content.endswith("\n") else ""))
        return True

    def _recover_title(self, problem_id) -> str:
        """从 meta.json / README.md / statement.txt 里尽力还原题目标题。"""
        folder = os.path.join(self.solutions_dir, str(problem_id))
        meta = self.load_meta(problem_id) or {}
        title = (meta.get("title") or "").strip()
        if title and title.lower() not in _BAD_TITLES:
            return title

        for candidate in ("README.md", "statement.txt"):
            path = os.path.join(folder, candidate)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    first = fh.readline().strip()
            except OSError:
                continue
            first = re.sub(r"^#\s*", "", first)
            # 笔记首行形如 "题目 1001 - 真正的题目名"
            first = re.sub(r"^题目\s*\d+\s*[-–—:：]\s*", "", first).strip()
            if first and first.lower() not in _BAD_TITLES:
                return first
        return ""

    def update_index(self, problem_id, problem_info: Optional[Dict] = None, ac_status: Optional[str] = None) -> str:
        """增量更新索引（保留旧签名）。"""
        rows = self.parse_index()
        entry = rows.setdefault(str(problem_id), {"link": f"{problem_id}/README.md"})
        if problem_info:
            entry["title"] = problem_info.get("title") or entry.get("title", "")
        entry.setdefault("title", f"题目 {problem_id}")
        if ac_status is not None:
            entry["verdict"] = verdict_label(ac_status)
        entry.setdefault("verdict", "⬜ 未提交")
        entry["model"] = entry.get("model") or get_settings().llm.model
        entry["updated"] = timestamp()
        return self.rebuild_index()
