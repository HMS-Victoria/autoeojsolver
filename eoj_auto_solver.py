#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EOJ 自动刷题 + 笔记归档工具 v4.0
================================

本文件现在是**向后兼容入口**，真正的实现在 :mod:`eojkit` 包里：

============================  ==========================================
旧版模块级名字                 现位置
============================  ==========================================
``EOJ_USERNAME`` / ``EOJ_PASSWORD``      → :mod:`eojkit.config`
``DEEPSEEK_API_KEY`` / ``DEEPSEEK_MODEL`` → :mod:`eojkit.config`
``EOJClient``                  → :mod:`eojkit.judge.client`
``DeepSeekSolver``             → :mod:`eojkit.llm.solver`
``CodeTester``                 → :mod:`eojkit.asm`
``SolutionArchiver``           → :mod:`eojkit.archive`
``solve_single_problem``       → :mod:`eojkit.pipeline`
============================  ==========================================

``eojstart.py``（GUI）与 ``eoj_cli.py``（CLI）继续通过
``import eoj_auto_solver as engine`` 使用这些名字，并且仍然可以直接
执行 ``engine.DEEPSEEK_MODEL = 'xxx'`` 之类的赋值 —— 下面的属性描述符
会把这类写入实时同步进 :class:`eojkit.config.Settings`。

v4.0 主要变化
-------------
1. **模型 API 接口更新**：模型 ID 改为官方在用的 ``deepseek-flash`` /
   ``deepseek-v4-pro``（经 ``GET /models`` 实测），废弃 ``deepseek-v4-flash``、
   ``deepseek-chat`` 等遗留写法；接口地址可配置，支持任意 OpenAI 兼容供应商。
2. **推理模型适配**：新模型把思维链放在 ``reasoning_content``，正文可能因
   max_tokens 被占满而为空；旧代码会直接判为失败。现在自动抬预算重试。
3. **稳定性**：鉴权/限流/网络错误区分处理，指数退避重试，主模型失败自动降级。
4. **安全**：源码中不再硬编码任何账号、密码、API Key。
5. **结构**：1900+ 行单文件拆分为 8 个职责单一的模块，并补上单元测试。

Designed by HMS_Victorious

用法::

  python eoj_auto_solver.py --problem 1001
  python eoj_auto_solver.py --range 1001-1020 --timeout 150
  python eoj_auto_solver.py --list-models          # 探测可用模型
  python eoj_auto_solver.py --doctor               # 环境自检
  python eoj_auto_solver.py --archive --all
  python eoj_auto_solver.py --check --problem 1001
"""

from __future__ import annotations

import os
import re
import sys
import time

# 让 ``python eoj_auto_solver.py`` 与 ``import eoj_auto_solver`` 都能找到 eojkit
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from eojkit import __version__
from eojkit.archive import ArchiveMeta, SolutionArchiver, verdict_label
from eojkit.asm import CodeTester as _StructuredCodeTester, CompileResult, TestResult
from eojkit.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    PROVIDER_PRESETS,
    config_path,
    get_settings,
    mask_secret,
    reload_settings,
)
from eojkit.judge import EOJClient, SubmitResult, parse_verdict
from eojkit.llm import AISolver, DeepSeekSolver, LLMClient, SolverError, extract_code, extract_markdown
from eojkit.pipeline import (
    STATUS_TEXT,
    SolveOutcome,
    archive_existing_problem,
    run_batch,
    solve,
    solve_single_problem,
)
from eojkit.tools import (
    PROJECT_ROOT,
    configure_console,
    extract_problem_ids_from_range,
    find_gpp as _probe_gpp,
    batch_mode_enabled,
    get_log_sink,
    list_existing_cpp_problems,
    log_fail,
    log_line,
    log_ok,
    log_warn,
    manual_captcha,
    set_batch_mode,
    set_captcha_solver,
    set_log_sink,
    solve_captcha,
    try_ocr_captcha,
)

configure_console()

__all__ = [
    "EOJClient",
    "DeepSeekSolver",
    "AISolver",
    "CodeTester",
    "SolutionArchiver",
    "LLMClient",
    "solve_single_problem",
    "solve",
    "archive_existing_problem",
    "run_batch",
    "main",
]

# ============================================================
# 兼容层：模块级可变配置
# ============================================================
# GUI/CLI 会写 ``engine.DEEPSEEK_MODEL = ...``。为了让这类历史写法继续生效、
# 又只保留一份配置真相，这里把本模块的 ``__class__`` 换成下面的子类：
#   * 读：模块全局里没有的配置名 → 从 Settings 取
#   * 写：命中配置名 → 转发给 Settings，不再在模块里留副本
# 这样 ``engine.DEEPSEEK_MODEL = 'x'`` 之后，``eojkit`` 内部读到的就是 'x'。

_SETTINGS = get_settings()

#: 模块级配置名 → (Settings 段, 字段)
CONFIG_ATTRS = {
    "EOJ_USERNAME": ("eoj", "username"),
    "EOJ_PASSWORD": ("eoj", "password"),
    "DEEPSEEK_API_KEY": ("llm", "api_key"),
    "DEEPSEEK_MODEL": ("llm", "model"),
    "LLM_BASE_URL": ("llm", "base_url"),
    "LLM_PROVIDER": ("llm", "provider"),
    "MAX_RETRIES": ("runtime", "max_retries"),
    "PER_PROBLEM_TIMEOUT": ("runtime", "per_problem_timeout"),
    "GPP_PATH": ("runtime", "gpp_path"),
    "PROXIES": ("runtime", "proxy"),
    "BATCH_MODE": ("runtime", "batch_mode"),
    "DEFAULT_SOLUTIONS_DIR": ("eoj", "solutions_dir"),
}

#: 已下线 / 仅存兼容别名 → 官方在用的模型 ID（经 GET /models 实测）
LEGACY_MODEL_ALIASES = {
    "deepseek-chat": "deepseek-flash",
    "deepseek-reasoner": "deepseek-flash",
    "deepseek-coder": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v3": "deepseek-v4-pro",
    "deepseek-v3.1": "deepseek-v4-pro",
    "deepseek-v3.2": "deepseek-v4-pro",
}


class _EOJSessionProxy:
    """旧版全局 ``session`` 的替代品。

    旧脚本在顶部建了一个全局 ``requests.Session()``。新版把会话收敛进
    :class:`EOJClient`（并按线程隔离）。为了让 ``engine.session.get(...)``
    这类历史写法仍能工作，这里转发到一个共享的浏览器会话。
    """

    _shared = None

    @classmethod
    def _session(cls):
        if cls._shared is None:
            cls._shared = EOJClient().session
        return cls._shared

    def __getattr__(self, name):
        return getattr(self._session(), name)


session = _EOJSessionProxy()


def _resolve_config(name):
    section, attribute = CONFIG_ATTRS[name]
    return getattr(_SETTINGS, section), attribute


class _CompatModule(sys.modules[__name__].__class__):
    """带配置代理的模块类型（见上方说明）。"""

    def __getattr__(self, name):
        if name in CONFIG_ATTRS:
            target, attribute = _resolve_config(name)
            return getattr(target, attribute)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name, value):
        if name in CONFIG_ATTRS:
            target, attribute = _resolve_config(name)
            if name == "DEEPSEEK_MODEL":
                value = _normalize_model(value)
            setattr(target, attribute, value)
            return
        super().__setattr__(name, value)


def _normalize_model(value):
    """把遗留模型名映射到官方在用的 ID。"""
    value = (value or "").strip()
    mapped = LEGACY_MODEL_ALIASES.get(value)
    if mapped and mapped != value:
        log_warn(f"模型 '{value}' 已停用或仅为兼容别名，自动改用 '{mapped}'")
        return mapped
    return value


sys.modules[__name__].__class__ = _CompatModule


# ------------------------------------------------------------------
# 兼容旧接口的包装类
# ------------------------------------------------------------------

# 旧版 CodeTester 的 ``results`` 是 List[Tuple[str, str]]，GUI/CLI 依赖该读法；
# LegacyCodeTester 在结构化实现之上补了这个只读视图。
from eojkit.asm import LegacyCodeTester as CodeTester  # noqa: E402


# ------------------------------------------------------------------
# 兼容旧接口的函数
# ------------------------------------------------------------------

def find_gpp() -> bool:  # type: ignore[misc]
    """旧接口：探测 g++ 并把路径写进全局 ``GPP_PATH``，返回是否找到。

    （新代码请直接用 :func:`eojkit.tools.find_gpp`，它返回路径或 ``None``。）
    """
    path = _probe_gpp()
    if path:
        _SETTINGS.runtime.gpp_path = path
        return True
    return False


def sync_runtime_settings(**overrides) -> None:
    """把 GUI/CLI 界面上的值写回 Settings（在启动任务前调用）。"""
    _SETTINGS.apply_credentials(
        username=overrides.get("username"),
        password=overrides.get("password"),
        api_key=overrides.get("api_key"),
        model=overrides.get("model"),
        base_url=overrides.get("base_url"),
    )
    provider = overrides.get("provider")
    if provider:
        _SETTINGS.llm.provider = str(provider).strip()
    if "solutions_dir" in overrides and overrides["solutions_dir"]:
        _SETTINGS.eoj.solutions_dir = overrides["solutions_dir"]


def save_gui_config(config: dict) -> str:
    """保存界面配置（GUI 用，保持旧字段名）。"""
    data = dict(_SETTINGS.to_file_dict())
    data.update({k: v for k, v in (config or {}).items() if v is not None})
    from eojkit.config import save_config_file

    return save_config_file(data)


def load_gui_config() -> dict:
    """读取界面配置（含旧版文件迁移）。"""
    settings = _SETTINGS
    return {
        "username": settings.eoj.username,
        "password": settings.eoj.password,
        "api_key": settings.llm.api_key,
        "solutions_dir": settings.eoj.solutions_dir,
        "remember": settings.eoj.remember,
        "model": settings.llm.model,
        "base_url": settings.llm.base_url,
        "provider": settings.llm.provider,
        "timeout": settings.runtime.per_problem_timeout,
    }


# ------------------------------------------------------------------
# 环境自检
# ------------------------------------------------------------------

def doctor() -> int:
    """打印环境自检报告，返回问题数量。"""
    settings = get_settings()
    issues = 0

    log_line("=" * 62)
    log_line(f"  EOJ 自动刷题系统 v{__version__} · 环境自检")
    log_line("=" * 62)

    log_line("\n[配置]")
    log_line(settings.describe())

    log_line("\n[依赖]")
    for module_name, package in (
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
        ("PIL", "pillow"),
        ("Crypto", "pycryptodome"),
    ):
        try:
            __import__(module_name)
            log_ok(f"{package}")
        except ImportError:
            log_fail(f"{package} 未安装 → pip install {package}")
            issues += 1
    try:
        import ddddocr  # noqa: F401

        log_ok("ddddocr（验证码自动识别）")
    except ImportError:
        log_warn("ddddocr 未安装，验证码需手动输入 → pip install ddddocr")

    log_line("\n[编译器]")
    if find_gpp():
        log_ok(f"g++: {_SETTINGS.runtime.gpp_path}")
    else:
        log_warn("未找到 g++，本地编译测试将被跳过")

    log_line("\n[大模型接口]")
    if not settings.llm.api_key:
        log_fail("未配置 API Key（设置环境变量 DEEPSEEK_API_KEY 或在 GUI 中填写）")
        issues += 1
    else:
        client = LLMClient(settings.llm)
        models = client.list_models()
        if models:
            log_ok(f"可用模型: {', '.join(models)}")
            if settings.llm.model not in models:
                log_warn(
                    f"当前配置的模型 '{settings.llm.model}' 不在可用列表中，"
                    f"建议改用 '{models[0]}'（python eoj_auto_solver.py --model {models[0]}）"
                )
                issues += 1
        else:
            log_warn("未能获取模型列表（将使用配置中的模型名）")
        health = client.health_check()
        if health.get("ok"):
            log_ok(
                f"连通性正常 · 模型 {health['model']} · 耗时 {health['latency']}s · "
                f"回复 {health.get('reply', '')!r}"
            )
            for note in health.get("notes") or []:
                log_warn(note)
        else:
            log_fail(f"连通性异常: {health.get('error')}")
            issues += 1
        client.close()

    log_line("\n[存档目录]")
    log_line(f"  {settings.eoj.solutions_dir}")
    existing = list_existing_cpp_problems()
    log_ok(f"已有解法: {len(existing)} 题")
    log_line(f"  配置文件: {config_path()}")

    log_line("\n" + "=" * 62)
    if issues:
        log_line(f"  自检完成：发现 {issues} 个需要处理的问题")
    else:
        log_line("  自检完成：一切正常 ✅")
    log_line("=" * 62)
    return issues


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="eoj_auto_solver.py",
        description=f"EOJ 自动刷题 + 笔记归档工具 v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python eoj_auto_solver.py --problem 1001
  python eoj_auto_solver.py --range 1001-1020 --timeout 150
  python eoj_auto_solver.py --problem 1001 --model deepseek-flash
  python eoj_auto_solver.py --problem 1001 --base-url https://api.deepseek.com/v1
  python eoj_auto_solver.py --list-models
  python eoj_auto_solver.py --doctor
  python eoj_auto_solver.py --archive --all
  python eoj_auto_solver.py --check --problem 1001
  python eoj_auto_solver.py --contest 1021 --all
""",
    )
    parser.add_argument("--problem", type=str, help="题号，如 1001")
    parser.add_argument("--url", type=str, help="题目完整 URL")
    parser.add_argument("--range", type=str, help="题目范围，如 1001-1020")
    parser.add_argument("--all", action="store_true", help="所有已有题目（用于 --archive）或竞赛全部题目")
    parser.add_argument("--no-submit", action="store_true", help="不提交，仅生成并测试代码")
    parser.add_argument("--no-login", action="store_true", help="不登录，仅获取题目和生成代码")
    parser.add_argument("--no-analysis", action="store_true", help="跳过生成中文刷题笔记")
    parser.add_argument("--no-test", action="store_true", help="跳过本地编译测试")
    parser.add_argument("--batch", action="store_true", help="批量模式：自动跳过弹窗/手动输入")
    parser.add_argument("--archive", action="store_true", help="归档模式：对已有代码生成笔记")
    parser.add_argument("--check", action="store_true", help="查状态模式：只查判题结果")
    parser.add_argument("--wait-judge", type=int, default=0, metavar="SEC", help="提交后等待判题的最长秒数，0=不等")
    parser.add_argument("--debug", action="store_true", help="调试模式：打印原始 HTML")
    parser.add_argument("--solutions-dir", type=str, help="笔记存档目录")
    parser.add_argument("--model", type=str, help="模型名（默认 deepseek-v4-pro；可用 --list-models 查看）")
    parser.add_argument("--base-url", type=str, help="OpenAI 兼容接入点，如 https://api.deepseek.com/v1")
    parser.add_argument("--provider", type=str, choices=sorted(PROVIDER_PRESETS), help="供应商预设")
    parser.add_argument("--api-key", type=str, help="临时指定 API Key（不落盘）")
    parser.add_argument("--list-models", action="store_true", help="列出接入点支持的模型后退出")
    parser.add_argument("--doctor", action="store_true", help="环境自检后退出")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="按 meta.json / 存档文件重建 solutions/index.md 后退出")
    parser.add_argument("--refresh-titles", action="store_true",
                        help="从 EOJ 重新拉取存档题目的真实标题（修复旧版抓成 Input 的标题）后退出")
    parser.add_argument("--contest", type=str, help="竞赛模式，指定竞赛 ID")
    parser.add_argument("--contest-problems", type=str, metavar="CID", help="列出指定竞赛的题目列表")
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="单题总时长上限（秒），0=不限时。超时自动跳过继续下一题",
    )
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # ---- 配置注入（命令行 > 环境变量 > 配置文件）----
    if args.provider:
        preset = PROVIDER_PRESETS[args.provider]
        _SETTINGS.llm.provider = args.provider
        if preset.get("base_url"):
            _SETTINGS.llm.base_url = preset["base_url"]
        if preset.get("models"):
            _SETTINGS.llm.model = preset["models"][0]
    if args.model:
        DEEPSEEK_MODEL = args.model  # noqa: F841 - 触发属性描述符
        log_line(f"  [配置] 使用模型: {_SETTINGS.llm.model}")
    if args.base_url:
        _SETTINGS.apply_credentials(base_url=args.base_url)
        log_line(f"  [配置] 接入点: {_SETTINGS.llm.base_url}")
    if args.api_key:
        _SETTINGS.llm.api_key = args.api_key.strip()
    if args.timeout:
        _SETTINGS.runtime.per_problem_timeout = args.timeout
        log_line(f"  [配置] 单题超时: {args.timeout}s")
    if args.solutions_dir:
        _SETTINGS.eoj.solutions_dir = args.solutions_dir
    if args.wait_judge:
        _SETTINGS.runtime.judge_wait = args.wait_judge

    # ---- 诊断类命令 ----
    if args.doctor:
        return 1 if doctor() else 0

    if args.list_models:
        log_line("=" * 62)
        log_line("  可用模型探测")
        log_line("=" * 62)
        log_line(f"  接入点: {_SETTINGS.llm.base_url}")
        log_line(f"  API Key: {mask_secret(_SETTINGS.llm.api_key)}")
        client = LLMClient(_SETTINGS.llm)
        models = client.list_models()
        if models:
            for name in models:
                mark = "  ← 当前使用" if name == _SETTINGS.llm.model else ""
                log_line(f"    • {name}{mark}")
            if _SETTINGS.llm.model not in models:
                log_warn(
                    f"当前配置的模型 '{_SETTINGS.llm.model}' 不在可用列表中，"
                    f"建议改用 {models[0]}"
                )
        else:
            log_fail("未能获取模型列表，请检查 API Key 与接入点")
        client.close()
        return 0 if models else 1

    # ---- 存档维护 ----
    if args.rebuild_index or args.refresh_titles:
        archiver = SolutionArchiver(_SETTINGS.eoj.solutions_dir)
        if args.refresh_titles:
            log_line("=" * 62)
            log_line("  从 EOJ 刷新题目真实标题")
            log_line("=" * 62)
            client = EOJClient()
            if not client.login():
                log_warn("登录失败，将以游客身份尝试（公开题目仍可读取标题）")
            updated = archiver.refresh_titles(client)
            log_ok(f"已刷新 {len(updated)} 道题的标题")
        archiver.rebuild_index()
        return 0

    log_line("=" * 62)
    log_line(f"  EOJ 自动刷题 + 笔记归档工具 v{__version__}")
    log_line("  华东师范大学在线评测系统")
    log_line(f"  模型: {_SETTINGS.llm.model} @ {_SETTINGS.llm.base_url}")
    log_line("  Designed by HMS_Victorious")
    log_line("=" * 62)

    # ---- 竞赛题目列表 ----
    if args.contest_problems:
        log_line(f"\n{'=' * 60}")
        log_line(f"  竞赛题目列表: Contest {args.contest_problems}")
        log_line(f"{'=' * 60}")
        client = EOJClient()
        if not client.login():
            log_fail("登录失败，无法获取竞赛题目")
            return 1
        problems = client.fetch_contest_problems(args.contest_problems)
        if problems:
            log_line(f"\n共 {len(problems)} 道题目:")
            for item in problems:
                log_line(f"  [{item['id']}] {item['title']}")
                log_line(f"    {item['url']}")
        log_line(f"\n提示: 使用 --contest {args.contest_problems} --all 自动刷该竞赛所有题目")
        return 0 if problems else 1

    # ---- 批量模式 ----
    if args.batch or args.range:
        ids = extract_problem_ids_from_range(args.range or "") or []
        if args.batch or len(ids) > 1:
            set_batch_mode(True)
            _SETTINGS.runtime.batch_mode = True
            log_line("[BATCH] 批量模式已启用，将自动跳过弹窗和手动输入")

    # ---- 解析题号 ----
    problem_ids = []
    contest_id = args.contest
    is_archive_mode = args.archive

    if args.problem:
        problem_ids = [args.problem]
    elif args.url:
        match = re.search(r"/problem/(\d+)/?", args.url)
        if not match:
            log_fail("无效的 URL 格式")
            return 1
        problem_ids = [match.group(1)]
    elif args.range:
        ids = extract_problem_ids_from_range(args.range)
        if not ids:
            log_fail("无效的范围格式")
            return 1
        problem_ids = ids
    elif args.all:
        if contest_id:
            client = EOJClient()
            if not client.login():
                log_fail("登录失败，无法获取竞赛题目")
                return 1
            contest_problems = client.fetch_contest_problems(contest_id)
            if not contest_problems:
                log_fail(f"无法获取竞赛 {contest_id} 的题目列表")
                return 1
            problem_ids = [item["id"] for item in contest_problems]
            log_line(f"[信息] 竞赛 {contest_id} 共 {len(problem_ids)} 道题: {', '.join(problem_ids)}")
        elif is_archive_mode:
            problem_ids = list_existing_cpp_problems()
            if not problem_ids:
                log_fail("存档目录下未找到 .cpp 文件")
                return 1
            log_line(f"[信息] 找到 {len(problem_ids)} 道已有题目")
        else:
            log_fail("--all 仅用于 --archive 模式或 --contest 模式")
            return 1
    else:
        parser.print_help()
        return 0

    if contest_id:
        log_line(f"\n[信息] 竞赛模式: Contest {contest_id}")

    # ---- 归档模式 ----
    if is_archive_mode:
        log_line(f"\n[任务] 归档模式: 对 {len(problem_ids)} 道已有题目生成笔记")
        solver = DeepSeekSolver()
        archiver = SolutionArchiver(_SETTINGS.eoj.solutions_dir)
        client = EOJClient()
        log_line("\n  [登录] 归档模式需要登录 EOJ 以获取完整题目信息...")
        if client.login():
            log_ok("登录成功")
        else:
            log_warn("登录失败，将以游客身份尝试（部分题目信息可能不完整）")

        success = fail = 0
        for pid in problem_ids:
            try:
                if archive_existing_problem(pid, solver=solver, archiver=archiver, eoj_client=client):
                    success += 1
                else:
                    fail += 1
            except KeyboardInterrupt:
                log_line("\n[!] 用户中断")
                break
            except Exception as exc:  # noqa: BLE001
                import traceback

                log_fail(f"归档异常 [{pid}]: {exc}")
                traceback.print_exc()
                fail += 1
            if len(problem_ids) > 1:
                time.sleep(2)

        archiver.rebuild_index()
        log_line("\n" + "=" * 60)
        log_line(f"  归档完成! 成功: {success}, 失败: {fail}")
        log_line(f"  存档目录: {archiver.solutions_dir}")
        log_line("=" * 60)
        return 0 if fail == 0 else 1

    # ---- 查状态模式 ----
    if args.check:
        log_line(f"\n{'=' * 60}")
        log_line("  == 查状态模式 ==")
        log_line(f"{'=' * 60}\n")
        client = EOJClient()
        if not client.login():
            log_fail("登录失败，无法查状态")
            return 1
        for pid in problem_ids:
            log_line(f"\n  [检查] {'Contest %s ' % contest_id if contest_id else ''}Problem {pid}...")
            result = client.check_status_once(pid, debug_html=args.debug, contest_id=contest_id)
            if result == "AC":
                log_line(f"  ✅ {pid}: AC")
            elif result in (None, "UNKNOWN"):
                log_line(f"  ⬜ {pid}: 无提交记录或未找到")
            else:
                log_line(f"  ❌ {pid}: {result}")
            if len(problem_ids) > 1:
                time.sleep(0.5)
        log_line(f"\n{'=' * 60}")
        log_line("  检查完成！")
        log_line(f"{'=' * 60}")
        return 0

    # ---- 正常刷题 ----
    log_line(f"\n[任务] 计划解题数量: {len(problem_ids)} 题")
    log_line(
        f"[任务] 题目: {', '.join(problem_ids[:10])}"
        + (f"... 等 {len(problem_ids)} 题" if len(problem_ids) > 10 else "")
    )

    find_gpp()

    client = None if args.no_login else EOJClient()
    solver = DeepSeekSolver()
    tester = None if args.no_test else CodeTester()
    archiver = SolutionArchiver(_SETTINGS.eoj.solutions_dir)

    stats = run_batch(
        problem_ids,
        eoj_client=client,
        solver=solver,
        tester=tester,
        archiver=archiver,
        skip_login=args.no_login,
        skip_submit=args.no_submit,
        skip_analysis=args.no_analysis,
        skip_test=args.no_test,
        contest_id=contest_id,
        judge_wait=_SETTINGS.runtime.judge_wait,
    )

    log_line(f"\n{'=' * 60}")
    log_line(f"  刷题完成！共 {stats['total']} 题")
    log_line(f"  ✅ 成功: {stats['success']}")
    log_line(f"  ❌ 失败: {stats['failed']}")
    log_line(f"{'=' * 60}")
    for outcome in stats["outcomes"]:
        if not outcome.ok:
            log_line(f"  [{outcome.problem_id}] {outcome.text}: {outcome.error[:120]}")
    log_line("  提示: 使用 --check 查看判题结果")
    log_line(f"  笔记存档: {archiver.solutions_dir}")
    log_line("=" * 60)
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
