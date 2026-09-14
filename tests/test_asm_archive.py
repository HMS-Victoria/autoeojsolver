# -*- coding: utf-8 -*-
"""编译测试器与归档器测试（离线；无 g++ 时自动跳过编译相关用例）。"""

from __future__ import annotations

import json
import os

import pytest

from eojkit.archive import ArchiveMeta, SolutionArchiver, verdict_label
from eojkit.asm import CodeTester, LegacyCodeTester, _normalize
from eojkit.tools import find_gpp

HELLO = """#include <iostream>
using namespace std;
int main(){ long long a,b; while(cin>>a>>b) cout<<a+b<<"\\n"; return 0; }
"""

BROKEN = """#include <iostream>
int main(){ this is not c++ }
"""


@pytest.fixture(scope="module")
def gpp():
    return find_gpp()


# ==========================================================================
# _normalize
# ==========================================================================

@pytest.mark.parametrize(
    "a,b",
    [
        ("1 2\n", "1 2"),
        ("1 2\r\n", "1 2\n"),
        ("a  \nb\t\n", "a\nb"),
        ("\n\nx\n\n", "x"),
    ],
)
def test_normalize_equivalent(a, b):
    assert _normalize(a) == _normalize(b)


def test_normalize_different():
    assert _normalize("1") != _normalize("2")


# ==========================================================================
# CodeTester
# ==========================================================================

def test_tester_without_compiler_reports_cleanly(tmp_path):
    tester = CodeTester(gpp=r"C:\definitely\missing\g++.exe", workdir=str(tmp_path))
    result = tester.build("int main(){}", "1", quiet=True)
    assert not result.ok
    assert result.status in ("NO_COMPILER", "COMPILE_EXCEPTION", "COMPILE_ERROR")


def test_tester_missing_exe_returns_false(tmp_path):
    tester = CodeTester(gpp=r"C:\missing\g++.exe", workdir=str(tmp_path))
    assert tester.test_with_samples(str(tmp_path / "nope.exe"), [{"input": "1", "output": "1"}], quiet=True) is False


def test_tester_no_samples_is_ok(tmp_path):
    tester = CodeTester(gpp=r"C:\missing\g++.exe", workdir=str(tmp_path))
    assert tester.test_with_samples("anything", [], quiet=True) is True


@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_compile_and_run_success(tmp_path, gpp):
    tester = CodeTester(gpp=gpp, workdir=str(tmp_path))
    build = tester.build(HELLO, "1", quiet=True)
    assert build.ok, build.message
    assert os.path.isfile(build.exe_path)

    passed = tester.test_with_samples(
        build.exe_path,
        [{"input": "1 2\n", "output": "3\n"}, {"input": "10 20\n", "output": "30\n"}],
        quiet=True,
    )
    assert passed is True
    assert len(tester._test_results) == 2
    assert all(item.ok for item in tester._test_results)
    text = tester.get_test_result_text()
    assert "编译: 通过" in text
    assert "样例 1: 通过" in text


@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_compile_error_reported(tmp_path, gpp):
    tester = CodeTester(gpp=gpp, workdir=str(tmp_path))
    build = tester.build(BROKEN, "2", quiet=True)
    assert not build.ok
    assert build.status == "COMPILE_ERROR"
    assert build.message
    report = tester.error_report()
    assert "COMPILE_ERROR" in report


@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_sample_mismatch_reported(tmp_path, gpp):
    tester = CodeTester(gpp=gpp, workdir=str(tmp_path))
    build = tester.build(HELLO, "3", quiet=True)
    passed = tester.test_with_samples(build.exe_path, [{"input": "1 2\n", "output": "999\n"}], quiet=True)
    assert passed is False
    report = tester.error_report()
    assert "SAMPLE 1 FAIL" in report
    assert "999" in report
    text = tester.get_test_result_text()
    assert "样例 1: 失败" in text


@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_reset_clears_records(tmp_path, gpp):
    tester = CodeTester(gpp=gpp, workdir=str(tmp_path))
    build = tester.build(HELLO, "4", quiet=True)
    tester.test_with_samples(build.exe_path, [{"input": "1 1\n", "output": "2\n"}], quiet=True)
    assert len(tester._test_results) == 1
    tester.reset()
    assert len(tester._test_results) == 0
    assert len(tester.compiles) == 0


@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_cleanup_removes_artifacts(tmp_path, gpp):
    tester = CodeTester(gpp=gpp, workdir=str(tmp_path))
    build = tester.build(HELLO, "5", quiet=True)
    assert os.path.isfile(build.code_path)
    tester.cleanup("5")
    assert not os.path.exists(build.code_path)
    assert not os.path.exists(build.exe_path)


# ==========================================================================
# LegacyCodeTester（GUI/CLI 兼容）
# ==========================================================================

def test_legacy_tester_results_tuple_view(tmp_path):
    tester = LegacyCodeTester(gpp=r"C:\missing\g++.exe", workdir=str(tmp_path))
    tester.build("int main(){}", "9", quiet=True)
    rows = list(tester.results)
    assert rows and isinstance(rows[0], tuple)
    assert len(rows[0]) == 2
    status, _detail = rows[0]
    assert isinstance(status, str)


# ==========================================================================
# SolutionArchiver
# ==========================================================================

@pytest.fixture()
def archiver(tmp_path):
    return SolutionArchiver(str(tmp_path / "solutions"), quiet=True)


def test_archiver_writes_all_artifacts(archiver):
    info = {
        "id": "1001",
        "title": "A + B",
        "url": "https://acm.ecnu.edu.cn/problem/1001/",
        "description": "求和",
        "samples": [{"input": "1 2\n", "output": "3\n"}],
    }
    archiver.meta.title = "A + B"
    archiver.meta.verdict = "AC"
    archiver.meta.generated_at = "2026-01-01 00:00:00"
    archiver.save_statement("1001", info)
    archiver.save_samples("1001", info["samples"])
    archiver.save_code("1001", HELLO)
    archiver.save_readme("1001", "# 题目 1001 - A + B\n\n## 题目大意\n求和")
    archiver.save_test_result("1001", "## 本地测试结果\n- 编译: 通过")
    archiver.save_meta("1001")

    folder = os.path.join(archiver.solutions_dir, "1001")
    for name in ("statement.txt", "samples.txt", "solution.cpp", "README.md",
                 "test_result.txt", "meta.json"):
        assert os.path.isfile(os.path.join(folder, name)), name

    readme = open(os.path.join(folder, "README.md"), encoding="utf-8").read()
    assert "<!-- eojkit:meta -->" in readme
    assert "✅ AC" in readme

    meta = archiver.load_meta("1001")
    assert meta["title"] == "A + B"
    assert meta["verdict"] == "AC"


def test_index_rebuild(archiver):
    for pid, title in (("1002", "第二题"), ("1001", "第一题")):
        archiver.save_code(pid, HELLO)
        archiver.meta.title = title
        archiver.save_meta(pid)
    path = archiver.rebuild_index()
    content = open(path, encoding="utf-8").read()
    assert "| 1001 |" in content
    assert "| 1002 |" in content
    assert content.index("1001") < content.index("1002"), "应按题号数字排序"
    assert "第一题" in content


def test_index_parsing_roundtrip(archiver):
    archiver.save_code("1001", HELLO)
    archiver.meta.title = "含|竖线|的标题"
    archiver.meta.model = "deepseek-v4-pro"
    archiver.save_meta("1001")
    archiver.rebuild_index()
    rows = archiver.parse_index()
    assert "1001" in rows
    assert rows["1001"]["title"] == "含|竖线|的标题", "竖线应被转义且可逆解析"


def test_index_tolerates_missing_index(archiver):
    assert archiver.parse_index() == {}


def test_verdict_label():
    assert verdict_label("AC") == "✅ AC"
    assert verdict_label(None) == "⬜ 未提交"
    assert verdict_label("XYZ").startswith("🔄")


def test_readme_footer_not_duplicated(archiver):
    archiver.save_readme("1001", "# t\n\n<!-- eojkit:meta -->\n> already")
    text = open(os.path.join(archiver.solutions_dir, "1001", "README.md"), encoding="utf-8").read()
    assert text.count("<!-- eojkit:meta -->") == 1


def test_save_meta_defaults_generated_at(archiver):
    archiver.save_meta("2000")
    meta = archiver.load_meta("2000")
    assert meta["generated_at"]
    assert meta["problem_id"] == "2000"


# ==========================================================================
# 旧格式 index.md 的解析（3 列，第 3 列是状态而不是模型）
# ==========================================================================

LEGACY_INDEX = """# EOJ 刷题记录

更新于: 2026-05-28 12:00:00

| 题号 | 题目 | 状态 |
|------|------|------|
| 1001 | [A + B](1001/README.md) | ✅ AC |
| 1002 | [IP Address](1002/README.md) | ⬜ 未提交 |
| 1003 | [Three](1003/README.md) | 🔄 SUBMITTED |
"""


def test_parse_legacy_index_does_not_mistake_status_for_model(archiver):
    """回归：旧索引只有 3 列，若按 5 列解析会把 "✅ AC" 当成模型名。"""
    with open(os.path.join(archiver.solutions_dir, "index.md"), "w", encoding="utf-8") as fh:
        fh.write(LEGACY_INDEX)
    rows = archiver.parse_index()
    assert rows["1001"]["title"] == "A + B"
    assert rows["1001"]["model"] == "", "旧格式没有模型列，不能误读状态列为模型"
    assert rows["1001"]["updated"] == ""
    assert "AC" in rows["1001"]["verdict"]
    assert "SUBMITTED" in rows["1003"]["verdict"]


def test_rebuild_index_ignores_stale_legacy_columns(archiver):
    """重建索引必须以文件系统为唯一真相，不沿用旧索引的标题/状态列。"""
    with open(os.path.join(archiver.solutions_dir, "index.md"), "w", encoding="utf-8") as fh:
        fh.write(LEGACY_INDEX)
    archiver.save_code("1001", HELLO)
    archiver.meta.title = "正确的标题"
    archiver.meta.verdict = "AC"
    archiver.meta.model = "deepseek-v4-pro"
    archiver.meta.generated_at = "2026-02-02 00:00:00"
    archiver.save_meta("1001")

    archiver.rebuild_index()
    rows = archiver.parse_index()
    assert rows["1001"]["title"] == "正确的标题"
    assert rows["1001"]["model"] == "deepseek-v4-pro"
    assert rows["1001"]["updated"] == "2026-02-02 00:00:00"
    # 1002/1003 只存在于旧索引、磁盘上没有目录 → 重建后不应残留幽灵行
    assert "1002" not in rows
    assert "1003" not in rows


def test_rebuild_index_recovers_title_from_readme(archiver):
    path = archiver.path_for("1007", "README.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# 题目 1007 - 真正的题目名\n\n正文\n")
    archiver.rebuild_index()
    rows = archiver.parse_index()
    assert rows["1007"]["title"] == "真正的题目名"


def test_recover_title_rejects_bad_titles(archiver):
    """README/statement 首行是 '# Input'（旧版 Bug 产物）时不能当作标题。"""
    path = archiver.path_for("1008", "statement.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Input\n来源: https://acm.ecnu.edu.cn/problem/1008/\n\nbody\n")
    assert archiver._recover_title("1008") == ""


def test_normalize_legacy_verdict():
    from eojkit.archive import _normalize_legacy_verdict

    assert _normalize_legacy_verdict("✅ AC") == "✅ AC"
    assert _normalize_legacy_verdict("AC") == "✅ AC"
    assert _normalize_legacy_verdict("") == ""
    assert _normalize_legacy_verdict("⬜ 未提交") == "⬜ 未提交"
    assert _normalize_legacy_verdict("ARCHIVED").startswith("📚")
    assert _normalize_legacy_verdict("Unknown") == "❔ 未知"
    assert _normalize_legacy_verdict("1. A+B Problem").startswith("🔄")


# ==========================================================================
# refresh_titles：修复旧版抓错的标题，且不得覆盖已有元信息
# ==========================================================================

class _FakeJudge:
    """只实现 refresh_titles 需要的那一个方法。"""

    def __init__(self, titles):
        self.titles = titles
        self.calls = []

    def get_problem_info(self, problem_id, contest_id=None):
        self.calls.append(problem_id)
        title = self.titles.get(str(problem_id))
        if title is None:
            return None
        return {
            "id": str(problem_id),
            "title": title,
            "url": f"https://acm.ecnu.edu.cn/problem/{problem_id}/",
            "description": "d",
            "samples": [],
        }


def test_refresh_titles_fixes_bad_titles(archiver):
    # 造一个"旧版 Bug"现场：标题被存成 Input
    archiver.save_code("1001", HELLO)
    archiver.meta.title = "Input"
    archiver.save_meta("1001")
    archiver.save_readme("1001", "# 题目 1001 - Input\n\n## 题目大意\n求和", with_meta=False)
    with open(archiver.path_for("1001", "statement.txt"), "w", encoding="utf-8") as fh:
        fh.write("# Input\n来源: url\n\nbody\n")

    judge = _FakeJudge({"1001": "1001. Problem A+B (Big Integer)"})
    updated = archiver.refresh_titles(judge, quiet=True)

    assert updated == {"1001": "1001. Problem A+B (Big Integer)"}
    assert archiver.load_meta("1001")["title"] == "1001. Problem A+B (Big Integer)"
    readme = open(archiver.path_for("1001", "README.md"), encoding="utf-8").read()
    # 笔记标题不应重复题号（"题目 1001 - Problem A+B ..."）
    assert readme.splitlines()[0] == "# 题目 1001 - Problem A+B (Big Integer)"
    statement = open(archiver.path_for("1001", "statement.txt"), encoding="utf-8").read()
    assert statement.splitlines()[0] == "# 1001. Problem A+B (Big Integer)"


def test_strip_leading_id():
    from eojkit.archive import _strip_leading_id

    assert _strip_leading_id("1002. IP Address", "1002") == "IP Address"
    assert _strip_leading_id("1002 IP Address", "1002") == "IP Address"
    assert _strip_leading_id("30、数字字符个数", "30") == "数字字符个数"
    assert _strip_leading_id("IP Address", "1002") == "IP Address"
    assert _strip_leading_id("10025. Other", "1002") == "10025. Other"
    assert _strip_leading_id("1002.", "1002") == "1002."
    assert _strip_leading_id("", "1002") == ""


def test_refresh_titles_preserves_existing_metadata(archiver):
    """关键回归：刷新标题不能把已归档的模型/判词/接入点覆盖掉。"""
    archiver.save_code("1002", HELLO)
    archiver.meta.title = "Input"
    archiver.meta.verdict = "AC"
    archiver.meta.model = "deepseek-flash"
    archiver.meta.base_url = "https://example.invalid/v1"
    archiver.meta.generated_at = "2026-03-03 03:03:03"
    archiver.meta.local_tests = "全部样例通过"
    archiver.save_meta("1002")

    judge = _FakeJudge({"1002": "1002. IP Address"})
    archiver.refresh_titles(judge, quiet=True)

    meta = archiver.load_meta("1002")
    assert meta["title"] == "1002. IP Address"
    assert meta["verdict"] == "AC"
    assert meta["model"] == "deepseek-flash"
    assert meta["base_url"] == "https://example.invalid/v1"
    assert meta["generated_at"] == "2026-03-03 03:03:03"
    assert meta["local_tests"] == "全部样例通过"


def test_refresh_titles_skips_unfetchable(archiver):
    archiver.save_code("1003", HELLO)
    archiver.meta.title = "Input"
    archiver.save_meta("1003")
    judge = _FakeJudge({})  # 全部返回 None
    assert archiver.refresh_titles(judge, quiet=True) == {}
    assert archiver.load_meta("1003")["title"] == "Input", "抓取失败时不应改动元信息"


# ==========================================================================
# README 元信息脚注：判题结果晚到时的补写
# ==========================================================================

def test_verdict_footer_added_later(archiver):
    archiver.save_readme("1001", "# 题目\n\n正文")
    before = open(os.path.join(archiver.solutions_dir, "1001", "README.md"), encoding="utf-8").read()
    assert "EOJ 判题结果" not in before

    archiver.meta.verdict = "WA"
    assert archiver.refresh_readme_meta("1001") is True
    after = open(os.path.join(archiver.solutions_dir, "1001", "README.md"), encoding="utf-8").read()
    assert "EOJ 判题结果：❌ WA" in after
    assert after.count("<!-- eojkit:meta -->") == 1

    # 重复刷新应无变化
    assert archiver.refresh_readme_meta("1001") is False
    # 判词变化时应就地更新而不是追加
    archiver.meta.verdict = "AC"
    assert archiver.refresh_readme_meta("1001") is True
    final = open(os.path.join(archiver.solutions_dir, "1001", "README.md"), encoding="utf-8").read()
    assert final.count("EOJ 判题结果") == 1
    assert "✅ AC" in final
