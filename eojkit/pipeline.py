# -*- coding: utf-8 -*-
"""
eojkit.pipeline —— 单题 / 批量解题流水线
=========================================

串联 ``登录 → 抓题 → AI 生成 → 编译测试 → AI 重写重试 → 提交 → 归档``。

相对旧 ``solve_single_problem`` 的修复：

* **编译器判定错误**：旧版用模块级 ``GPP_PATH`` 做分支，GUI 场景下它常为
  ``None`` → 直接跳过编译测试却仍然提交，等于"带病上线"。现在交给
  :class:`~eojkit.asm.CodeTester` 自行决定，并把"无编译器"明确告知用户。
* **错误信息采集靠字符串前缀**：旧版遍历 ``tester.results`` 找 ``'FAIL' in status``，
  现在走 :meth:`CodeTester.error_report`，一次给出编译错误 + 首个失败样例。
* **重试时不刷新测试记录**：旧版复用同一个 tester，``results`` 会跨轮累积，
  导致归档的 ``test_result.txt`` 混入历次失败的样例。现在每轮 ``reset()``。
* **返回值**：保留旧字符串状态码（``'SUCCESS'``/``'FAIL_*'``），
  同时新增 :class:`SolveOutcome` 结构化结果供新代码使用。

Designed by HMS_Victorious
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .archive import ArchiveMeta, SolutionArchiver, verdict_label
from .asm import CodeTester
from .config import get_settings
from .judge import EOJClient
from .llm import DeepSeekSolver
from .tools import (
    find_gpp,
    log_fail,
    log_line,
    log_ok,
    log_warn,
    timestamp,
)

__all__ = [
    "SolveOutcome",
    "solve_single_problem",
    "archive_existing_problem",
    "run_batch",
]

#: 状态码 → 中文说明
STATUS_TEXT = {
    "SUCCESS": "处理完成",
    "UNVERIFIED": "代码已生成，但未完成本地验证；未提交",
    "FAIL_LOGIN": "登录失败",
    "FAIL_FETCH": "抓题失败",
    "FAIL_CODE": "AI 生成代码失败",
    "FAIL_COMPILE": "编译失败",
    "FAIL_TEST": "样例测试未通过",
    "FAIL_SUBMIT": "提交失败",
    "FAIL_TIMEOUT": "单题超时",
    "FAIL_UNKNOWN": "未知错误",
}


@dataclass
class SolveOutcome:
    """单题解题结果。"""

    problem_id: str = ""
    status: str = "SUCCESS"
    code: str = ""
    attempts: int = 0
    tests_passed: bool = False
    submitted: bool = False
    submit_url: str = ""
    notes_saved: bool = False
    elapsed: float = 0.0
    model: str = ""
    error: str = ""
    extra: Dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "SUCCESS"

    @property
    def text(self) -> str:
        if self.status == "SUCCESS":
            return "已提交" if self.submitted else "本地验证通过，未提交"
        return STATUS_TEXT.get(self.status, self.status)

    def __bool__(self) -> bool:
        return self.ok


class _Timeout(Exception):
    """单题超时哨兵。"""


def solve_single_problem(
    problem_id,
    skip_login=False,
    skip_submit=False,
    skip_analysis=False,
    eoj_client=None,
    solver=None,
    tester=None,
    archiver=None,
    contest_id=None,
    *,
    skip_test=False,
    max_retries=None,
    per_problem_timeout=None,
    judge_wait=0,
):
    """解决单题并归档，返回状态码字符串（保持旧接口）。

    需要结构化结果时请用 :func:`solve`。
    """
    outcome = solve(
        problem_id,
        skip_login=skip_login,
        skip_submit=skip_submit,
        skip_analysis=skip_analysis,
        eoj_client=eoj_client,
        solver=solver,
        tester=tester,
        archiver=archiver,
        contest_id=contest_id,
        skip_test=skip_test,
        max_retries=max_retries,
        per_problem_timeout=per_problem_timeout,
        judge_wait=judge_wait,
    )
    return outcome.status


def solve(
    problem_id,
    *,
    skip_login=False,
    skip_submit=False,
    skip_analysis=False,
    eoj_client=None,
    solver=None,
    tester=None,
    archiver=None,
    contest_id=None,
    skip_test=False,
    max_retries=None,
    per_problem_timeout=None,
    judge_wait=0,
) -> SolveOutcome:
    """执行一次完整解题流程。"""
    settings = get_settings()
    runtime = settings.runtime
    retries = runtime.max_retries if max_retries is None else max_retries
    timeout = runtime.per_problem_timeout if per_problem_timeout is None else per_problem_timeout
    started = time.time()

    outcome = SolveOutcome(
        problem_id=str(problem_id),
        model=settings.llm.model,
    )

    def _timed_out(step: str) -> bool:
        if timeout <= 0:
            return False
        elapsed = time.time() - started
        if elapsed > timeout:
            log_line(f"\n  [超时] 题目 {problem_id} 用时 {elapsed:.0f}s 超过 {timeout}s（{step}），跳过！")
            return True
        return False

    header = (
        f"  开始解题: Contest {contest_id} Problem {problem_id}"
        if contest_id
        else f"  开始解题: Problem {problem_id}"
    )
    log_line("\n" + "=" * 60)
    log_line(header)
    log_line("=" * 60)

    # ---------------- 登录 ----------------
    if eoj_client is None and not skip_login:
        eoj_client = EOJClient()
    if not skip_login and eoj_client and not eoj_client.logged_in:
        if not eoj_client.login():
            outcome.status = "FAIL_LOGIN"
            outcome.error = "EOJ 登录失败"
            return outcome

    if _timed_out("登录"):
        outcome.status = "FAIL_TIMEOUT"
        return outcome

    # ---------------- 抓题 ----------------
    try:
        problem_info = eoj_client.get_problem_info(problem_id, contest_id=contest_id) if eoj_client else None
    except Exception as exc:  # noqa: BLE001
        log_fail(f"抓题异常: {type(exc).__name__}: {exc}")
        problem_info = None
    if not problem_info:
        outcome.status = "FAIL_FETCH"
        outcome.error = "未能获取题目内容"
        return outcome

    if archiver:
        archiver.save_statement(problem_id, problem_info)
        archiver.save_samples(problem_id, problem_info.get("samples"))
        archiver.meta.title = problem_info.get("title", "")
        archiver.meta.url = problem_info.get("url", "")
        archiver.meta.samples = len(problem_info.get("samples") or [])

    if _timed_out("抓题"):
        outcome.status = "FAIL_TIMEOUT"
        return outcome

    # ---------------- AI 生成代码 ----------------
    if solver is None:
        solver = DeepSeekSolver()
    if _timed_out("AI 生成代码"):
        outcome.status = "FAIL_TIMEOUT"
        return outcome

    code = solver.generate_code(problem_info)
    if not code:
        outcome.status = "FAIL_CODE"
        outcome.error = getattr(solver, "last_error", "") or "AI 返回空结果"
        return outcome

    outcome.code = code
    if archiver:
        archiver.save_code(problem_id, code)

    # ---------------- AI 生成笔记 ----------------
    if not skip_analysis:
        analysis = solver.generate_analysis(problem_info, code)
        if analysis and archiver:
            archiver.save_readme(problem_id, analysis)
            outcome.notes_saved = True

    # ---------------- 编译测试 + AI 重写重试 ----------------
    tests_passed = False
    if skip_test:
        log_line("\n  [跳过] 已指定跳过本地编译测试")
    else:
        if tester is None:
            tester = CodeTester()
        if not tester.gpp:
            log_warn("无可用编译器，无法本地验证，禁止提交")
        else:
            for attempt in range(1, retries + 1):
                outcome.attempts = attempt
                log_line(f"\n  [尝试] 第 {attempt}/{retries} 次尝试...")
                tester.reset()
                build = tester.build(code, problem_id)
                if not build.ok:
                    if build.status == "NO_COMPILER":
                        break
                    error_info = tester.error_report()
                    if archiver:
                        archiver.save_test_result(problem_id, tester.get_test_result_text())
                    if attempt >= retries:
                        log_line("\n  [!] 已达到最大重试次数，编译仍失败")
                        outcome.status = "FAIL_COMPILE"
                        outcome.error = error_info
                        tester.cleanup(problem_id)
                        return outcome
                    log_line("\n  [!] 编译失败，让 AI 重写代码...")
                    new_code = solver.regenerate_code(problem_info, code, error_info)
                    if not new_code or new_code == code:
                        log_warn("AI 未能生成新代码，停止重试")
                        outcome.status = "FAIL_COMPILE"
                        outcome.error = error_info
                        tester.cleanup(problem_id)
                        return outcome
                    code = new_code
                    outcome.code = code
                    if archiver:
                        archiver.save_code(problem_id, code)
                    tester.cleanup(problem_id)
                    continue

                if not problem_info.get("samples"):
                    log_warn("编译成功，但题目没有样例，未验证且不会提交")
                    break
                tests_passed = tester.test_with_samples(build.exe_path, problem_info.get("samples") or [])
                if archiver:
                    archiver.save_test_result(problem_id, tester.get_test_result_text())
                if tests_passed:
                    log_ok(f"第 {attempt} 次尝试测试通过！")
                    break

                error_info = tester.error_report()
                if attempt >= retries:
                    log_line("\n  [!] 已达到最大重试次数，样例测试仍未通过，跳过提交")
                    outcome.status = "FAIL_TEST"
                    outcome.error = error_info
                    tester.cleanup(problem_id)
                    return outcome
                log_line("\n  [!] 样例测试未通过，让 AI 重写代码...")
                new_code = solver.regenerate_code(problem_info, code, error_info)
                if not new_code or new_code == code:
                    log_warn("AI 未能生成新代码，停止重试")
                    outcome.status = "FAIL_TEST"
                    outcome.error = error_info
                    tester.cleanup(problem_id)
                    return outcome
                code = new_code
                outcome.code = code
                if archiver:
                    archiver.save_code(problem_id, code)
                tester.cleanup(problem_id)

    outcome.tests_passed = tests_passed

    if not tests_passed:
        outcome.status = "UNVERIFIED"
        outcome.error = "未完成本地编译和样例测试，已阻止提交"
        log_warn(outcome.error)
        if archiver:
            archiver.meta.local_tests = "未验证；未提交"
            archiver.save_test_result(problem_id, outcome.error)
            archiver.save_meta(problem_id)
        if tester:
            tester.cleanup(problem_id)
        return outcome

    # ---------------- 提交 ----------------
    if skip_submit:
        log_line("\n  [跳过] 跳过提交（skip_submit=True）")
        outcome.status = "SUCCESS"
    elif eoj_client and eoj_client.logged_in:
        try:
            result = eoj_client.submit(problem_id, code, contest_id=contest_id)
        except Exception as exc:  # noqa: BLE001
            log_fail(f"提交异常: {type(exc).__name__}: {exc}")
            result = None
        if result and result.ok:
            outcome.submitted = True
            outcome.submit_url = result.url
        else:
            log_fail("提交失败")
            if tester:
                tester.cleanup(problem_id)
            outcome.status = "FAIL_SUBMIT"
            outcome.error = getattr(result, "message", "") or "提交未成功"
            return outcome
    else:
        log_line("\n  [跳过] EOJ 未登录，无法提交")

    # ---------------- 判题（可选） ----------------
    if judge_wait and eoj_client and eoj_client.logged_in and outcome.submitted:
        verdict = eoj_client.check_submission_status(problem_id, max_wait=judge_wait)
        outcome.extra["verdict"] = verdict
        if archiver:
            archiver.meta.verdict = verdict

    # ---------------- 归档收尾 ----------------
    if tester:
        tester.cleanup(problem_id)

    if archiver:
        archiver.meta.local_tests = (
            "全部样例通过" if tests_passed else ("未运行" if skip_test else "未通过/跳过")
        )
        archiver.meta.generated_at = timestamp()
        archiver.save_meta(problem_id)
        archiver.update_index(
            problem_id, problem_info, ac_status=outcome.extra.get("verdict")
        )

    outcome.elapsed = time.time() - started
    outcome.status = "SUCCESS"
    log_line(f"\n  [完成] 题目 {problem_id} 处理结束（{outcome.elapsed:.1f}s）")
    return outcome


# --------------------------------------------------------------------------
# 归档已有代码
# --------------------------------------------------------------------------

def _find_existing_code(problem_id, solutions_dir: Optional[str] = None) -> Optional[str]:
    """在存档目录里找已有解法（兼容新旧两种目录结构）。"""
    settings = get_settings()
    roots = [solutions_dir or settings.eoj.solutions_dir, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eoj")]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        nested = os.path.join(root, str(problem_id), "solution.cpp")
        if os.path.isfile(nested):
            with open(nested, "r", encoding="utf-8") as fh:
                return fh.read()
        for name in os.listdir(root):
            if name.startswith(str(problem_id)) and name.endswith(".cpp"):
                with open(os.path.join(root, name), "r", encoding="utf-8") as fh:
                    return fh.read()
    return None


def archive_existing_problem(
    problem_id,
    existing_code=None,
    solver=None,
    archiver=None,
    eoj_client=None,
) -> bool:
    """对已有代码生成刷题笔记（不重新刷题）。"""
    log_line("\n" + "=" * 60)
    log_line(f"  归档已有题目: Problem {problem_id}")
    log_line("=" * 60)

    if archiver is None:
        archiver = SolutionArchiver()
    if solver is None:
        solver = DeepSeekSolver()
    if eoj_client is None:
        eoj_client = EOJClient()
        if not eoj_client.logged_in:
            eoj_client.login()

    problem_info = eoj_client.get_problem_info(problem_id)
    if not problem_info:
        return False

    code = existing_code or _find_existing_code(problem_id, archiver.solutions_dir)
    if not code:
        log_fail(f"未找到 {problem_id} 的已有代码")
        return False

    archiver.save_statement(problem_id, problem_info)
    archiver.save_samples(problem_id, problem_info.get("samples"))
    archiver.save_code(problem_id, code)

    analysis = solver.generate_analysis(problem_info, code)
    if analysis:
        archiver.save_readme(problem_id, analysis)
    else:
        log_warn("笔记生成失败，仅归档题目与代码")

    archiver.meta.title = problem_info.get("title", "")
    archiver.meta.url = problem_info.get("url", "")
    archiver.meta.samples = len(problem_info.get("samples") or [])
    archiver.meta.generated_at = timestamp()
    archiver.save_meta(problem_id)
    archiver.update_index(problem_id, problem_info, ac_status="ARCHIVED")

    log_line(f"\n  [完成] 题目 {problem_id} 归档成功！")
    return True


# --------------------------------------------------------------------------
# 批量
# --------------------------------------------------------------------------

def run_batch(
    problem_ids: List[str],
    *,
    on_result: Optional[Callable[[SolveOutcome], None]] = None,
    quiet: bool = False,
    **solve_kwargs,
) -> Dict[str, object]:
    """批量解题，返回统计信息。"""
    settings = get_settings()
    interval = settings.runtime.submit_interval
    outcomes: List[SolveOutcome] = []
    success = failed = 0

    for index, pid in enumerate(problem_ids, start=1):
        log_line(f"\n[{index}/{len(problem_ids)}] Problem {pid}")
        try:
            outcome = solve(pid, **solve_kwargs)
        except KeyboardInterrupt:
            log_line("\n[!] 用户中断")
            break
        except Exception as exc:  # noqa: BLE001
            import traceback

            log_fail(f"{pid} 异常: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            outcome = SolveOutcome(problem_id=str(pid), status="FAIL_UNKNOWN", error=str(exc))

        outcomes.append(outcome)
        if outcome.ok:
            success += 1
            log_ok(f"[{pid}] 完成")
        else:
            failed += 1
            log_fail(f"[{pid}] {outcome.text}" + (f" — {outcome.error}" if outcome.error else ""))
        if on_result:
            try:
                on_result(outcome)
            except Exception:  # noqa: BLE001
                pass
        if index < len(problem_ids):
            time.sleep(max(interval, 0))

    return {
        "total": len(problem_ids),
        "success": success,
        "failed": failed,
        "outcomes": outcomes,
    }
