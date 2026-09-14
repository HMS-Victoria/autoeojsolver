# -*- coding: utf-8 -*-
"""验证码解析启发式测试（离线，不调用 ddddocr）。"""

from __future__ import annotations

import pytest

from eojkit.tools import _parse_arithmetic, _to_number, _calc

# 真实 OCR 输出样本（来自 eojkit 的实测日志）
CASES = [
    ("8minus7", "1"),
    ("8minus1", "7"),
    ("3times7", "21"),
    ("3timesT", "21"),        # 实测：7 被识别成 T
    ("6plus2", "8"),
    ("9minus3", "6"),
    ("4times5", "20"),
    ("4time5s", "20"),        # 5 被识别成 s（右侧只取第一位）
    ("4time55", "20"),        # 实测：单个 5 被认成两个字符 "55"
    ("10plus5", "15"),
    ("2multipliedby3", "6"),
    ("8dividedby2", "4"),
    ("12minus4", "8"),
    ("3timess", "15"),        # 5 被识别成 s
    ("7plus1", "8"),
    ("2timesO", "0"),         # 0 被识别成 O
    ("5plusl", "6"),          # 1 被识别成 l
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_parse_arithmetic(raw, expected):
    assert _parse_arithmetic(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "hello", "abc", "times", "3 4", "??"],
)
def test_parse_arithmetic_unparseable(raw):
    assert _parse_arithmetic(raw) is None


@pytest.mark.parametrize(
    "token,expected",
    [("7", 7), ("T", 7), ("s", 5), ("O", 0), ("l", 1), ("z", 2), ("q", 0), ("x", None), ("", None)],
)
def test_to_number(token, expected):
    assert _to_number(token) == expected


def test_calc_ops():
    assert _calc("+", 2, 3) == 5
    assert _calc("-", 2, 3) == -1
    assert _calc("*", 2, 3) == 6
    assert _calc("/", 7, 2) == 3
    assert _calc("/", 7, 0) == 0
