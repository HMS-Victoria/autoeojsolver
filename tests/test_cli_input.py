# -*- coding: utf-8 -*-
"""控制台输入清洗的回归测试。

背景：Windows 上 ``sys.stdin`` 默认按 GBK(cp936) 解码，用管道喂命令时首行的
UTF-8 BOM（``EF BB BF``）会被解成「锘縟」之类的乱码，于是第一条命令永远匹配
不上，报「未知命令」。这个 bug 在交互式手工测试里很难复现（手输没有 BOM），
所以单独固化成用例。

为避免源码里出现难辨认的乱码字面量，用例统一用 ``\\uXXXX`` 转义书写。
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

#: BOM 首字节 EF 按 GBK 独占解码得到的字符 U+9518
MANGLED_HEAD = "\u9518"
#: 紧随其后的 CJK 区残渣字符（U+7E1F，即「縟」）
MANGLED_TAIL = "\u7e1f"
#: 解码器遇到不完整多字节序列时插入的替换字符
REPLACEMENT = "\ufffd"


@pytest.fixture(scope="module")
def console_cls():
    """加载 eoj_cli 并取出 EOJConsole（不实例化，避免构建真实引擎）。"""
    spec = importlib.util.spec_from_file_location(
        "eoj_cli_under_test", os.path.join(BASE_DIR, "eoj_cli.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.EOJConsole


@pytest.mark.parametrize(
    "raw, expected, why",
    [
        ("status", "status", "普通命令"),
        ("  stats  ", "stats", "两侧空白"),
        ("\ufeffstatus", "status", "正常解出的 BOM"),
        (MANGLED_HEAD + MANGLED_TAIL + "status", "status", "BOM 被 GBK 解错（锘縟）"),
        (MANGLED_HEAD + REPLACEMENT + MANGLED_TAIL + "status", "status", "含替换字符的残渣"),
        ("\ufeff\ufeffstatus", "status", "重复 BOM"),
        ("st\x00a\x00t\x00u\x00s\x00", "status", "PowerShell 5.1 管道的 NUL"),
        ("\r\n", "", "空行"),
        (None, "", "None"),
        # 以「锘」开头但不是 BOM 残渣的合法命令名必须原样保留
        (MANGLED_HEAD + "x", MANGLED_HEAD + "x", "长度不足，不当作残渣"),
    ],
)
def test_normalize_line(console_cls, raw, expected, why):
    assert console_cls._normalize_line(raw) == expected, why


def test_normalize_line_feeds_command_dispatch(console_cls):
    """清洗后的首行必须是可识别的命令，而不是「未知命令」。"""
    console = console_cls.__new__(console_cls)   # 不跑 __init__ / initialize
    seen = []
    console.parse_and_execute = lambda line: seen.append(line)  # type: ignore[method-assign]
    for raw in (
        "\ufeffstatus",
        MANGLED_HEAD + MANGLED_TAIL + "status",
        MANGLED_HEAD + REPLACEMENT + MANGLED_TAIL + "stats",
    ):
        console.parse_and_execute(console._normalize_line(raw))
    assert seen == ["status", "status", "stats"]
