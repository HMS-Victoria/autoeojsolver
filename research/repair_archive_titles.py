# -*- coding: utf-8 -*-
"""一次性存档修复脚本：从 EOJ 取回真实标题。

背景：早期版本的 ``get_problem_info`` 用 ``div.title`` 抓标题，命中的是页面小标题，
导致部分存档的 ``statement.txt`` 首行标题被写成 ``# Input``；这些目录同时缺少
``meta.json``，于是 ``index.md`` 里只能显示描述片段。

本脚本对每个待修复题号执行一次「取回标题 → 修正 README/statement 首行 → 写回
meta.json」的流程，逻辑与 ``eojkit.archive.SolutionArchiver.refresh_titles``
保持一致（直接复用其 ``_fix_statement_title`` / ``_fix_readme_title``）。

用法::

    python research/repair_archive_titles.py            # 修复缺失标题的目录
    python research/repair_archive_titles.py 1119 1185  # 只修复指定题号
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eojkit.archive import ArchiveMeta, SolutionArchiver  # noqa: E402
from eojkit.tools import configure_console, timestamp  # noqa: E402

BASE_URL = "https://acm.ecnu.edu.cn"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

#: 明确已弃用的题目，不再尝试抓取
DEPRECATED = {"1169": "（题目已弃用）"}

_RESERVED = {
    "", "input", "output", "sample", "samples", "example", "examples",
    "输入", "输出", "输入格式", "输出格式", "样例", "样例输入", "样例输出",
    "题目描述", "提示", "说明", "description", "hint", "note", "notes",
}


def fetch_title(session: requests.Session, problem_id: str):
    """返回 ``(title, url)``；抓不到时返回 ``(None, url)``。"""
    url = f"{BASE_URL}/problem/{problem_id}/"
    resp = session.get(url, timeout=20)
    if resp.status_code != 200:
        return None, url
    resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text

    for pattern in (
        r"<h1[^>]*>(.*?)</h1>",
        r'<div[^>]+class="[^"]*ui header[^"]*"[^>]*>(.*?)</div>',
        r"<h2[^>]*>(.*?)</h2>",
    ):
        for raw in re.findall(pattern, html, re.S):
            text = re.sub(r"<[^>]+>", "", raw)
            text = re.sub(r"\s+", " ", text).strip()
            if text and text.lower() not in _RESERVED:
                return text, url
    return None, url


def main(argv) -> int:
    configure_console()
    archiver = SolutionArchiver()
    root = archiver.solutions_dir

    targets = [a for a in argv if a.isdigit()]
    explicit = bool(targets)
    if not targets:
        targets = sorted(
            (d for d in os.listdir(root) if d.isdigit()), key=int
        )
        # 只自动挑选「标题缺失或被抓成页面小标题」的目录
        picked = []
        for pid in targets:
            meta_path = os.path.join(root, pid, "meta.json")
            title = ""
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, encoding="utf-8-sig") as fh:
                        title = str((json.load(fh) or {}).get("title") or "").strip()
                except (OSError, ValueError):
                    title = ""
            if not title or title.lower() in _RESERVED:
                picked.append(pid)
        targets = picked
    print(f"待修复目录: {len(targets)} 个 -> {', '.join(targets)}\n")

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})

    fixed = skipped = failed = 0
    for pid in targets:
        meta_path = os.path.join(root, pid, "meta.json")
        meta = {}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8-sig") as fh:
                    meta = json.load(fh) or {}
            except (OSError, ValueError):
                meta = {}

        old_title = (meta.get("title") or "").strip()
        if not explicit and old_title and old_title.lower() not in _RESERVED:
            print(f"  [跳过] {pid}: 已有标题 {old_title!r}")
            skipped += 1
            continue

        title, url = None, f"{BASE_URL}/problem/{pid}/"
        if pid in DEPRECATED:
            title = DEPRECATED[pid]
            print(f"  [标记] {pid}: {title}")
        else:
            try:
                title, url = fetch_title(session, pid)
            except requests.RequestException as exc:
                print(f"  [FAIL] {pid}: 抓取异常 {type(exc).__name__}: {exc}")

        if not title:
            print(f"  [FAIL] {pid}: 未取到标题，保持原样")
            failed += 1
            time.sleep(0.5)
            continue

        # 复用 archiver 的标题修正逻辑（与 refresh_titles 同一套规则）
        meta["problem_id"] = pid
        meta["title"] = title
        meta["url"] = url
        meta.setdefault("verdict", "")
        meta.setdefault("model", "")
        meta.setdefault("base_url", "")
        meta.setdefault("prompt_version", "")
        meta.setdefault("local_tests", "")
        meta.setdefault("samples", 0)
        meta.setdefault("notes", [])
        meta.setdefault("generated_at", timestamp())

        archiver.meta.problem_id = pid
        archiver._fix_statement_title(pid, title)
        archiver._fix_readme_title(pid, title)
        archiver.save_meta(pid, ArchiveMeta(**{
            key: meta.get(key) for key in ArchiveMeta.__dataclass_fields__
        }))

        print(f"  [OK] {pid}: {old_title or '(无)'} -> {title}")
        fixed += 1
        if pid not in DEPRECATED:
            time.sleep(0.4)

    print(f"\n完成：修复 {fixed} · 跳过 {skipped} · 失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
