# -*- coding: utf-8 -*-
"""
eojkit.tools —— 通用工具
========================

包含三块内容：

1. **统一日志**：``log_line`` / ``console``，替代原先散落各处的裸 ``print``，
   并支持 GUI 注入回调（旧版靠 ``sys.stdout`` 重定向，线程间竞争 GIL 会卡界面）。
2. **验证码求解**：``try_ocr_captcha`` / ``solve_captcha``，保留旧版全部启发式规则
   （OCR 混淆字符还原 + 正则兜底 + 纯数字回退），并修正了旧版批量模式
   用 ``image_data.decode('latin-1')`` 从 PNG 二进制里"提取数字"的无意义逻辑。
3. **路径/题号工具**：``find_gpp``、``extract_problem_ids_from_range``、
   ``list_existing_cpp_problems``。

Designed by HMS_Victorious
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Iterable, List, Optional, Sequence

__all__ = [
    "PROJECT_ROOT",
    "TEMP_DIR",
    "LOG_LEVELS",
    "set_log_sink",
    "get_log_sink",
    "log_line",
    "log_ok",
    "log_fail",
    "log_warn",
    "log_step",
    "configure_console",
    "find_gpp",
    "extract_problem_ids_from_range",
    "list_existing_cpp_problems",
    "try_ocr_captcha",
    "manual_captcha",
    "solve_captcha",
    "set_captcha_solver",
    "batch_mode_enabled",
    "set_batch_mode",
    "timestamp",
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 所有临时产物（编译中间文件、验证码图片、调试 HTML）统一放这里。
#: 旧版会把 ``submit_*.cpp`` / ``debug_submit_*.html`` / ``captcha_tmp.png``
#: 直接堆在项目根目录，跑几次就一片狼藉。
TEMP_DIR = os.path.join(tempfile.gettempdir(), "eojkit")


def ensure_temp_dir() -> str:
    """确保临时目录存在并返回其路径。"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    return TEMP_DIR

# ==========================================================================
# 日志
# ==========================================================================

LOG_LEVELS = ("DEBUG", "INFO", "OK", "WARN", "FAIL")


class _Console:
    """带可选回调的日志出口。

    GUI 通过 :func:`set_log_sink` 注入回调后，所有引擎输出都会走该回调，
    不再依赖 ``sys.stdout`` 重定向，从而避免多线程写同一控件导致的卡顿。
    """

    def __init__(self) -> None:
        self._sink: Optional[Callable[[str], None]] = None
        self._lock = threading.RLock()
        self.quiet = False

    def set_sink(self, sink: Optional[Callable[[str], None]]) -> None:
        with self._lock:
            self._sink = sink

    @property
    def sink(self):
        return self._sink

    def emit(self, text: str) -> None:
        if self.quiet:
            return
        with self._lock:
            sink = self._sink
        if sink is not None:
            try:
                sink(text)
                return
            except Exception:  # noqa: BLE001 - 日志失败不能影响主流程
                pass
        try:
            print(text)
        except Exception:  # noqa: BLE001
            pass


console = _Console()


def set_log_sink(sink: Optional[Callable[[str], None]]) -> None:
    """注册日志出口；传 ``None`` 恢复 print。"""
    console.set_sink(sink)


def get_log_sink():
    return console.sink


def configure_console(force_utf8: bool = True) -> None:
    """修正 Windows 控制台编码（GBK → UTF-8），幂等。"""
    if not force_utf8:
        return
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        elif sys.platform == "win32":
            import io as _io

            sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def log_line(message: str = "") -> None:
    console.emit(message)


def log_ok(message: str) -> None:
    console.emit(f"  [OK] {message}")


def log_fail(message: str) -> None:
    console.emit(f"  [FAIL] {message}")


def log_warn(message: str) -> None:
    console.emit(f"  [WARN] {message}")


def log_step(message: str) -> None:
    console.emit(f"\n=== {message} ===")


def timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ==========================================================================
# 运行模式（兼容旧全局 BATCH_MODE）
# ==========================================================================

_BATCH_MODE = False
_BATCH_LOCK = threading.Lock()


def set_batch_mode(enabled: bool) -> None:
    global _BATCH_MODE
    with _BATCH_LOCK:
        _BATCH_MODE = bool(enabled)


def batch_mode_enabled() -> bool:
    with _BATCH_LOCK:
        return _BATCH_MODE


# ==========================================================================
# 编译器探测
# ==========================================================================

_GPP_LOCK = threading.RLock()
_GPP_PATH: Optional[str] = None
_GPP_PROBED = False


def find_gpp(extra_paths: Sequence[str] = (), force: bool = False) -> Optional[str]:
    """查找 g++ 编译器，返回路径（找不到返回 None）。

    相对旧版的改进：结果缓存，避免每次解题都跑一次 ``g++ --version``；
    候选路径扩展到常见安装位置与 scoop/chocolatey 目录。
    """
    global _GPP_PATH, _GPP_PROBED
    with _GPP_LOCK:
        if _GPP_PROBED and not force:
            return _GPP_PATH

        from .paths import APP_DIR
        import shutil
        exe = "g++.exe" if os.name == "nt" else "g++"
        candidates = [
            str(APP_DIR / "toolchain" / "ucrt64" / "bin" / exe),
            str(APP_DIR / "toolchain" / "mingw64" / "bin" / exe),
            os.environ.get("EOJ_GPP") or os.environ.get("CXX"),
            *extra_paths,
            shutil.which(exe),
        ]

        for path in candidates:
            try:
                if path and os.path.isfile(path):
                    _GPP_PATH = path
                    _GPP_PROBED = True
                    log_ok(f"找到 g++: {path}")
                    return _GPP_PATH
            except OSError:
                continue

        _GPP_PATH = None
        _GPP_PROBED = True
        log_fail("未找到 g++ 编译器！请安装 MinGW-w64 或设置环境变量 EOJ_GPP")
        return None


def gpp_path() -> Optional[str]:
    return _GPP_PATH


# ==========================================================================
# 题号工具
# ==========================================================================

def extract_problem_ids_from_range(range_str: str) -> Optional[List[str]]:
    """``'1001-1005'`` → ``['1001', ..., '1005']``；解析失败返回 None。"""
    match = re.search(r"(\d+)\s*-\s*(\d+)", range_str or "")
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    if end < start:
        start, end = end, start
    return [str(i) for i in range(start, end + 1)]


def list_existing_cpp_problems(solutions_dir: Optional[str] = None) -> List[str]:
    """扫描存档目录，返回已有 ``solution.cpp`` 的题号列表（升序）。

    同时兼容新版 ``eoj_solutions/{id}/solution.cpp`` 结构与旧版
    ``eoj/{id}.cpp`` 平铺结构。
    """
    from .config import get_settings

    candidates: List[str] = []
    if solutions_dir:
        candidates.append(solutions_dir)
    else:
        settings_dir = get_settings().eoj.solutions_dir
        candidates.extend(
            [
                settings_dir,
                os.path.join(PROJECT_ROOT, "eoj_solutions"),
                os.path.join(PROJECT_ROOT, "eoj"),
            ]
        )

    target = None
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            target = candidate
            break
    if target is None:
        log_fail(f"存档目录不存在: {candidates[0] if candidates else '(未配置)'}")
        return []

    problems = set()
    for entry in os.listdir(target):
        full = os.path.join(target, entry)
        if os.path.isdir(full):
            if os.path.isfile(os.path.join(full, "solution.cpp")):
                match = re.match(r"(\d+)", entry)
                if match:
                    problems.add(match.group(1))
        elif entry.endswith(".cpp"):
            match = re.match(r"(\d+)", entry)
            if match:
                problems.add(match.group(1))
    return sorted(problems, key=int)


# ==========================================================================
# 验证码
# ==========================================================================

_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()
_CAPTCHA_SOLVER: Optional[Callable[[bytes], str]] = None


def set_captcha_solver(solver: Optional[Callable[[bytes], str]]) -> None:
    """注入自定义验证码求解器（GUI 弹窗用）。"""
    global _CAPTCHA_SOLVER
    _CAPTCHA_SOLVER = solver


def _get_ocr():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    with _OCR_LOCK:
        if _OCR_ENGINE is None:
            import ddddocr

            _OCR_ENGINE = ddddocr.DdddOcr(show_ad=False)
    return _OCR_ENGINE


#: OCR 常见混淆 → 运算符
_WORD_MAP = [
    ("minus", "-"), ("minu5", "-"), ("minu2", "-"), ("minu", "-"),
    ("mi2u5", "-"), ("mi2u2", "-"), ("mi2us", "-"), ("mi2u", "-"),
    ("m2u5", "-"), ("m2u2", "-"), ("m2us", "-"), ("m2u", "-"),
    ("inu5", "-"), ("inu2", "-"), ("inus", "-"),
    ("2u5", "-"), ("2u2", "-"), ("2us", "-"),
    ("times", "*"), ("time5", "*"), ("time2", "*"), ("time", "*"),
    ("ime5", "*"), ("ime2", "*"), ("imes", "*"),
    ("multipliedby", "*"), ("multiply", "*"),
    ("plus", "+"), ("plu5", "+"), ("plu2", "+"), ("plu", "+"),
    ("lu5", "+"), ("lue", "+"),
    ("subtract", "-"), ("5ubtract", "-"), ("5ubtrac5", "-"),
    ("dividedby", "/"), ("divide", "/"), ("divid", "/"), ("div", "/"),
]
_OP_CHARS = {"r": "+", "p": "+", "t": "+", "x": "*"}
_OP_KEYWORDS = (
    (("-",), ("minu", "mi2u", "m2u", "2u", "inu", "sub")),
    (("+",), ("plu", "lu", "add")),
    (("*",), ("time", "ime", "mul")),
    (("/",), ("div",)),
)


def _calc(op: str, a: int, b: int) -> int:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    return a // b if b else 0


#: ddddocr 把数字误认成字母的常见映射（用于单字符操作数还原）
_DIGIT_CONFUSION = {
    "o": "0", "q": "0", "d": "0",
    "i": "1", "l": "1", "j": "1", "|": "1",
    "z": "2",
    "e": "3",
    "a": "4",
    "s": "5",
    "g": "6",
    "t": "7", "f": "7",
    "b": "8",
    "p": "9",
}

#: 运算符词 → 符号（长词优先，避免 "times" 被 "time" 抢先匹配）
_OP_WORDS: Tuple[Tuple[str, str], ...] = tuple(
    sorted(
        (
            ("multipliedby", "*"), ("multiplied", "*"), ("multiply", "*"),
            ("times", "*"), ("time", "*"), ("mul", "*"),
            ("dividedby", "/"), ("divide", "/"), ("div", "/"),
            ("minus", "-"), ("subtract", "-"), ("sub", "-"),
            ("plus", "+"), ("add", "+"),
        ),
        key=lambda pair: -len(pair[0]),
    )
)

_RULE_OPERAND_CHARS = re.compile(r"[0-9a-z]")
_OP_WORD_RE = re.compile("|".join(word for word, _sym in _OP_WORDS))


def _to_number(token: str) -> Optional[int]:
    """把单个 OCR 字符还原成数字（``'T'`` → 7）。"""
    if not token:
        return None
    token = token.lower()
    if token.isdigit():
        return int(token)
    return int(_DIGIT_CONFUSION[token]) if token in _DIGIT_CONFUSION else None


def _read_operand_backward(chars, index: int) -> Optional[int]:
    """从 ``index`` 起向左读一个操作数。

    若与运算符相邻的是一段**纯数字**，则优先整段读取（``10plus5`` → 10）；
    否则按单字符还原（``7``→``T`` 这类形近字母场景）。
    """
    if index < 0 or index >= len(chars):
        return None
    end = index
    while index >= 0 and chars[index].isdigit():
        index -= 1
    digits = "".join(chars[index + 1: end + 1])
    if len(digits) > 1:
        return int(digits)
    if digits:
        return int(digits)
    return _to_number(chars[end])


def _read_operand_forward(chars, index: int) -> Optional[int]:
    """从 ``index`` 起向右读一个操作数。

    纯数字段优先（``4time55`` → 55），否则按单字符还原（``3timess`` → 5）。
    """
    if index < 0 or index >= len(chars):
        return None
    cursor = index
    while cursor < len(chars) and chars[cursor].isdigit():
        cursor += 1
    digits = "".join(chars[index:cursor])
    if digits:
        return int(digits)
    return _to_number(chars[index])


def _parse_arithmetic(text: str) -> Optional[str]:
    """解析 ``<一位数> <运算符词> <一位数>`` 形式的算术验证码。

    EOJ 的验证码操作数都是一位数，例如 ``8 minus 7``、``3 times 7``。
    OCR 常把数字认成形近字母（``7``→``T``、``5``→``s``、``0``→``O``），
    这里统一还原后再计算。返回 ``"结果"``；无法解析返回 ``None``。
    """
    lowered = (text or "").lower()
    match = _OP_WORD_RE.search(lowered)
    if not match:
        return None
    operator = dict(_OP_WORDS)[match.group(0)]

    left_chars = _RULE_OPERAND_CHARS.findall(lowered[: match.start()])
    right_chars = _RULE_OPERAND_CHARS.findall(lowered[match.end():])
    if not left_chars or not right_chars:
        return None

    # 与运算符相邻的字符才是操作数
    a = _read_operand_backward(left_chars, len(left_chars) - 1)
    b = _read_operand_forward(right_chars, 0)

    # OCR 有时把单个字形重复输出（"4time55" 其实是 4×5）：
    # 左侧是一位数且右侧是同一数字重复时，折叠成一位数。
    if a is not None and b is not None and a < 10 and b >= 10:
        digits = str(b)
        if len(set(digits)) == 1:
            b = int(digits[0])

    if a is None or b is None:
        return None

    answer = str(_calc(operator, a, b))
    log_ok(f"验证码: {a} {operator} {b} = {answer}")
    return answer


def try_ocr_captcha(image_data: bytes) -> Optional[str]:
    """用 ddddocr 识别 EOJ 的小学算术验证码，返回答案字符串或 None。

    策略：OCR 文本 → 单词级运算符还原 → 正则表达式提取 → 符号定位
    → 纯数字回退。
    """
    try:
        ocr = _get_ocr()
    except ImportError:
        log_line("  ddddocr 未安装，需要手动输入验证码")
        return None
    except Exception as exc:  # noqa: BLE001
        log_warn(f"ddddocr 初始化失败: {exc}")
        return None

    try:
        origin = (ocr.classification(image_data) or "").strip()
    except Exception as exc:  # noqa: BLE001
        log_warn(f"OCR 识别异常: {exc}")
        return None

    if not origin:
        log_line("  OCR 无法识别，需要手动输入")
        return None

    log_line(f"  OCR 识别结果: '{origin}'")

    # ---- 策略 0：<数字/字母> 运算符词 <数字/字母>，支持单字符"字母数字" ----
    # 例如 "3timesT"(T→7)、"8minus7"、"6plus2"。旧版只能处理两边都是数字的情况，
    # 单字符操作数会被丢掉，最后退化成把两边数字拼在一起（必然错误）。
    parsed = _parse_arithmetic(origin)
    if parsed is not None:
        return parsed

    # ---- 策略 A：单词级运算符还原 ----
    text = origin.lower().replace(" ", "")
    for old, new in _WORD_MAP:
        text = text.replace(old, new)
    text_a = text
    for old, new in _OP_CHARS.items():
        text_a = text_a.replace(old, new)

    # ---- 策略 B：正则提取 "数字 + 字母块 + 数字" ----
    regex_match = re.search(r"(\d+)\s*([a-z]+)\s*(\d+)", origin.lower())
    if regex_match:
        left, op_word, right = regex_match.groups()
        op_lower = op_word.lower()
        for ops, keywords in _OP_KEYWORDS:
            if any(keyword in op_lower for keyword in keywords):
                det = ops[0]
                answer = str(_calc(det, int(left), int(right)))
                log_ok(f"验证码: {left} {det} {right} = {answer}")
                return answer

    # ---- 策略 C：在还原后的文本里定位运算符 ----
    for expr in (text_a, text):
        found_op, op_idx = None, -1
        for candidate in "+-*/":
            idx = expr.find(candidate)
            if idx >= 0 and (op_idx < 0 or idx < op_idx):
                op_idx, found_op = idx, candidate
        if found_op is None or not (0 < op_idx < len(expr) - 1):
            continue
        left_raw, right_raw = expr[:op_idx], expr[op_idx + 1:]
        # 只提取数字，不做字母→数字替换（字母多为噪点）
        left_digits = "".join(c for c in left_raw if c.isdigit())
        right_digits = "".join(c for c in right_raw if c.isdigit())
        if left_digits and right_digits:
            answer = str(_calc(found_op, int(left_digits), int(right_digits)))
            log_ok(f"验证码: {left_digits} {found_op} {right_digits} = {answer}")
            return answer
        # 轻量数字还原后再试一次
        light = {"i": "1", "o": "0", "z": "2"}
        for old, new in light.items():
            left_raw = left_raw.replace(old, new)
            right_raw = right_raw.replace(old, new)
        left_digits2 = "".join(c for c in left_raw if c.isdigit())
        right_digits2 = "".join(c for c in right_raw if c.isdigit())
        if left_digits2 and right_digits2:
            answer = str(_calc(found_op, int(left_digits2), int(right_digits2)))
            log_ok(f"验证码: {left_digits2} {found_op} {right_digits2} = {answer}")
            return answer

    # ---- 回退：纯数字 ----
    origin_lower = origin.lower()
    for old, new in (("i", "1"), ("o", "0"), ("z", "2"), ("s", "5"), ("l", "1")):
        origin_lower = origin_lower.replace(old, new)
    digit_only = "".join(c for c in origin_lower if c.isdigit())
    if digit_only:
        log_warn(f"无法解析表达式，使用纯数字: {digit_only}")
        return digit_only

    log_line("  OCR 无法识别，需要手动输入")
    return None


def manual_captcha(image_data: bytes) -> str:
    """把验证码图片存盘并打开，让用户手动输入答案。"""
    path = os.path.join(ensure_temp_dir(), "captcha_tmp.png")
    try:
        with open(path, "wb") as fh:
            fh.write(image_data)
        log_line(f"\n  [!] 验证码图片已保存到: {path}")
        log_line("  [!] 请打开该图片，输入验证码答案")
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        log_warn(f"无法打开验证码图片: {exc}")
    try:
        return input("  请输入验证码答案: ").strip()
    except EOFError:
        return ""


def solve_captcha(image_data: bytes) -> str:
    """验证码求解总入口：自定义求解器 → OCR → 手动输入 / 批量兜底。"""
    if _CAPTCHA_SOLVER is not None:
        try:
            answer = _CAPTCHA_SOLVER(image_data)
            if answer:
                return str(answer).strip()
        except Exception as exc:  # noqa: BLE001
            log_warn(f"自定义验证码求解器失败: {exc}")

    result = try_ocr_captcha(image_data)
    if result:
        log_ok(f"自动识别验证码: {result}")
        return result

    if batch_mode_enabled():
        # 批量模式不弹窗：直接返回 "0" 兜底（旧版从 PNG 二进制里提数字是无效逻辑）
        log_warn("批次模式：OCR 失败，使用兜底值 0（该题登录可能失败，将自动跳过）")
        return "0"
    return manual_captcha(image_data)
