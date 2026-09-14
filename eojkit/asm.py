# -*- coding: utf-8 -*-
"""
eojkit.asm —— 本地编译与样例测试
================================

从旧 ``CodeTester`` 重构而来，改进点：

* **不再依赖全局 ``GPP_PATH``**：支持注入编译器路径，找不到编译器时给出明确原因，
  而不是靠 ``NameError`` 暴露问题。
* **输出有上限**：旧版把程序 stdout 全量读进内存后直接打印，样例输出巨大时
  会把 GUI 卡死；现在截断显示但完整比对。
* **结果结构化**：``TestResult`` 数据类携带状态码，归档文本由数据生成，
  避免旧版用 ``status.split('_')[1]`` 解析字符串的脆弱写法。
* **失败原因可直接喂给 AI 重写**：``error_report()`` 汇总编译器 stderr 与首个
  失败样例的期望/实际输出。

Designed by HMS_Victorious
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .config import get_settings
from .tools import TEMP_DIR, find_gpp, log_fail, log_line, log_ok, log_warn

__all__ = ["CodeTester", "LegacyCodeTester", "TestResult", "CompileResult"]

#: 展示用输出上限（字符），超出部分截断但比对仍用完整内容
MAX_DISPLAY = 2000
MAX_CAPTURE = 2 * 1024 * 1024


@dataclass
class CompileResult:
    ok: bool = False
    exe_path: Optional[str] = None
    code_path: Optional[str] = None
    status: str = ""
    message: str = ""
    elapsed: float = 0.0
    warning: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class TestResult:
    index: int = 0
    status: str = "PASS"          # PASS / FAIL / TIMEOUT / ERROR
    expected: str = ""
    actual: str = ""
    elapsed: float = 0.0
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "PASS"


def _normalize(text: str) -> str:
    """行尾空格无关、末尾空行无关的规范化比较。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.strip().split("\n")]
    return "\n".join(lines).strip()


def _clip(text: str, limit: int = MAX_DISPLAY) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[已截断，共 {len(text)} 字符]"


class CodeTester:
    """编译并运行 C++ 代码，用样例数据校验。

    :param gpp: 编译器路径；为 ``None`` 时自动探测。
    :param workdir: 编译产物目录；默认使用系统临时目录，避免污染项目根目录。
    """

    def __init__(
        self,
        gpp: Optional[str] = None,
        workdir: Optional[str] = None,
        *,
        compile_timeout: Optional[int] = None,
        run_timeout: Optional[int] = None,
        std: str = "c++17",
    ):
        runtime = get_settings().runtime
        self.gpp = gpp or runtime.gpp_path or find_gpp()
        # 编译中间产物统一放到临时目录，避免像旧版一样把 submit_*.cpp/exe
        # 丢在项目根目录
        self.workdir = workdir or os.path.join(TEMP_DIR, "build")
        self.compile_timeout = compile_timeout or runtime.compile_timeout
        self.run_timeout = run_timeout or runtime.run_timeout
        self.std = std
        self.compiles: List[CompileResult] = []
        self._test_results: List[TestResult] = []
        os.makedirs(self.workdir, exist_ok=True)

    # ------------------------------------------------------------------
    # 编译
    # ------------------------------------------------------------------
    def compile_code(self, code: str, problem_id, quiet: bool = False) -> Optional[str]:
        """编译源码，成功返回可执行文件路径，失败返回 ``None``。

        保留旧签名/返回值，方便旧调用方零改动迁移。
        """
        result = self.build(code, problem_id, quiet=quiet)
        return result.exe_path if result.ok else None

    def build(self, code: str, problem_id, quiet: bool = False) -> CompileResult:
        """编译源码并返回结构化结果。"""
        if not self.gpp:
            result = CompileResult(status="NO_COMPILER", message="未找到 g++ 编译器，跳过本地测试")
            self.compiles.append(result)
            if not quiet:
                log_fail(result.message)
            return result

        code_path = os.path.join(self.workdir, f"submit_{problem_id}.cpp")
        exe_path = os.path.join(self.workdir, f"submit_{problem_id}.exe")
        try:
            with open(code_path, "w", encoding="utf-8") as fh:
                fh.write(code)
        except OSError as exc:
            result = CompileResult(status="IO_ERROR", message=f"写入源文件失败: {exc}")
            self.compiles.append(result)
            return result

        if not quiet:
            log_line("\n  [编译] 编译代码...")
        command = [self.gpp, code_path, "-o", exe_path, f"-std={self.std}", "-O2", "-Wall"]
        started = time.time()
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=self.compile_timeout
            )
        except subprocess.TimeoutExpired:
            result = CompileResult(
                status="COMPILE_TIMEOUT",
                message=f"编译超时 (>{self.compile_timeout}s)",
                code_path=code_path,
                elapsed=time.time() - started,
            )
            self.compiles.append(result)
            if not quiet:
                log_fail(result.message)
            return result
        except Exception as exc:  # noqa: BLE001
            result = CompileResult(
                status="COMPILE_EXCEPTION",
                message=f"编译异常: {type(exc).__name__}: {exc}",
                code_path=code_path,
                elapsed=time.time() - started,
            )
            self.compiles.append(result)
            if not quiet:
                log_fail(result.message)
            return result

        elapsed = time.time() - started
        if proc.returncode != 0:
            message = _clip(proc.stderr or proc.stdout or "(无输出)", 800)
            result = CompileResult(
                status="COMPILE_ERROR",
                message=message,
                code_path=code_path,
                elapsed=elapsed,
                warning=proc.stderr or "",
            )
            self.compiles.append(result)
            if not quiet:
                log_fail("编译失败!")
                log_line(f"  {message}")
            return result

        result = CompileResult(
            ok=True,
            exe_path=exe_path,
            code_path=code_path,
            status="COMPILE_OK",
            elapsed=elapsed,
            warning=_clip(proc.stderr or "", 800),
        )
        self.compiles.append(result)
        if not quiet:
            log_ok(f"编译成功 ({elapsed:.1f}s)")
            if result.warning:
                log_warn(f"编译器警告:\n{_clip(result.warning, 400)}")
        return result

    # ------------------------------------------------------------------
    # 样例测试
    # ------------------------------------------------------------------
    def test_with_samples(self, exe_path: str, samples: Sequence[Dict[str, str]], quiet: bool = False) -> bool:
        """用样例逐个测试，返回是否全部通过。"""
        samples = list(samples or [])
        if not samples:
            if not quiet:
                log_line("  [跳过] 没有样例数据可供测试")
            return True
        if not exe_path or not os.path.isfile(exe_path):
            if not quiet:
                log_fail("可执行文件不存在，无法测试")
            return False

        if not quiet:
            log_line("\n  [测试] 用样例测试...")

        all_pass = True
        for index, sample in enumerate(samples, start=1):
            result = self.run_sample(exe_path, sample, index)
            self._test_results.append(result)
            if result.ok:
                if not quiet:
                    log_ok(f"样例 {index} 通过 ({result.elapsed:.2f}s)")
            else:
                all_pass = False
                if not quiet:
                    log_fail(f"样例 {index} {result.status}")
                    log_line(f"    期望: {_clip(result.expected, 200)}")
                    log_line(f"    实际: {_clip(result.actual, 200)}")
        return all_pass

    def run_sample(self, exe_path: str, sample: Dict[str, str], index: int = 1) -> TestResult:
        """运行单个样例，返回结构化结果。"""
        data_in = (sample or {}).get("input", "") or ""
        expected = (sample or {}).get("output", "") or ""
        started = time.time()
        try:
            proc = subprocess.run(
                [exe_path],
                input=data_in,
                capture_output=True,
                text=True,
                timeout=self.run_timeout,
                cwd=self.workdir,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                index=index,
                status="TIMEOUT",
                expected=expected,
                elapsed=time.time() - started,
                message=f"运行超过 {self.run_timeout}s",
            )
        except Exception as exc:  # noqa: BLE001
            return TestResult(
                index=index,
                status="ERROR",
                expected=expected,
                elapsed=time.time() - started,
                message=f"{type(exc).__name__}: {exc}",
            )

        elapsed = time.time() - started
        actual = (proc.stdout or "")[:MAX_CAPTURE]
        if _normalize(expected) == _normalize(actual):
            return TestResult(index=index, status="PASS", expected=expected, actual=actual, elapsed=elapsed)

        stderr = (proc.stderr or "")[:400]
        return TestResult(
            index=index,
            status="FAIL",
            expected=expected,
            actual=actual,
            elapsed=elapsed,
            message=f"returncode={proc.returncode}" + (f", stderr={stderr}" if stderr else ""),
        )

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    @property
    def all_ok(self) -> bool:
        return all(item.ok for item in self._test_results) and all(item.ok for item in self.compiles)

    def error_report(self) -> str:
        """生成给 AI 重写代码用的错误摘要（只取关键信息，控制 token 消耗）。"""
        parts: List[str] = []
        for item in self.compiles:
            if not item.ok:
                parts.append(f"[{item.status}] {item.message}")
        for item in self._test_results:
            if item.ok:
                continue
            parts.append(
                f"[SAMPLE {item.index} {item.status}]\n"
                f"Input/Expected:\n{_clip(item.expected, 600)}\n"
                f"Got:\n{_clip(item.actual, 600)}"
                + (f"\nNote: {item.message}" if item.message else "")
            )
        if not parts:
            return "无错误信息"
        return "\n\n".join(parts)

    def get_test_result_text(self) -> str:
        """生成归档用 ``test_result.txt`` 内容。"""
        lines = ["## 本地测试结果\n", f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
        if self.gpp:
            lines.append(f"编译器: {self.gpp} (-std={self.std})\n")

        for item in self.compiles:
            if item.status == "COMPILE_OK":
                lines.append(f"- 编译: 通过 ({item.elapsed:.1f}s)")
                if item.warning:
                    lines.append("  ```")
                    lines.extend(f"  {row}" for row in _clip(item.warning, 800).splitlines())
                    lines.append("  ```")
            elif item.status == "NO_COMPILER":
                lines.append("- 编译: 跳过（未找到 g++）")
            elif item.status == "COMPILE_TIMEOUT":
                lines.append("- 编译: 超时")
            else:
                lines.append(f"- 编译: 失败 ({item.status})")
                if item.message:
                    lines.append("  ```")
                    lines.extend(f"  {row}" for row in item.message.splitlines())
                    lines.append("  ```")

        for item in self._test_results:
            label = {"PASS": "通过", "FAIL": "失败", "TIMEOUT": "超时", "ERROR": "异常"}.get(
                item.status, item.status
            )
            lines.append(f"- 样例 {item.index}: {label} ({item.elapsed:.2f}s)")
            if not item.ok and item.actual:
                lines.append("  ```")
                lines.append(f"  期望: {_clip(item.expected, 300)}")
                lines.append(f"  实际: {_clip(item.actual, 300)}")
                lines.append("  ```")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------
    def cleanup(self, problem_id=None) -> None:
        """删除编译产物；``problem_id`` 为 None 时清理整个工作目录。"""
        targets = []
        if problem_id is None:
            targets.append(self.workdir)
        else:
            targets.extend(
                [
                    os.path.join(self.workdir, f"submit_{problem_id}.cpp"),
                    os.path.join(self.workdir, f"submit_{problem_id}.exe"),
                    os.path.join(self.workdir, f"submit_{problem_id}"),
                ]
            )
        for path in targets:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def reset(self) -> None:
        """清空本轮测试记录（批量刷题时复用同一个 tester 实例）。"""
        self.compiles.clear()
        self._test_results.clear()


class _LegacyResults:
    """让 ``tester.results`` 保持旧版 ``List[Tuple[str, str]]`` 的读法。

    旧版是 ``List[Tuple[str, str]]``，GUI/CLI 会写
    ``for status, detail in tester.results``；新版内部用结构化对象，
    这里提供一个只读的兼容视图。
    """

    def __init__(self, owner: "CodeTester"):
        self._owner = owner

    def _rows(self):
        rows = [(item.status, item.message) for item in self._owner.compiles]
        for item in self._owner._test_results:
            detail = ""
            if not item.ok:
                detail = f"Expected:\n{item.expected}\n\nGot:\n{item.actual}"
            rows.append((f"SAMPLE_{item.index}_{item.status}", detail))
        return rows

    def __iter__(self):
        return iter(self._rows())

    def __len__(self):
        return len(self._owner.compiles) + len(self._owner._test_results)

    def __getitem__(self, index):
        return self._rows()[index]

    def __bool__(self):
        return len(self) > 0

    def __repr__(self):  # pragma: no cover
        return f"LegacyResults({self._rows()!r})"


class LegacyCodeTester(CodeTester):
    """兼容旧版的 ``CodeTester``：额外暴露 ``results`` 元组视图。"""

    @property
    def results(self):  # type: ignore[override]
        return _LegacyResults(self)
