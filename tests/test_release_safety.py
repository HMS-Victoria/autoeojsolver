from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from eojkit.asm import CodeTester
from eojkit.pipeline import solve


@pytest.mark.parametrize("mode", ["missing", "skip", "no_samples", "removed", "zero_attempts"])
def test_unverified_never_submits(tmp_path, mode):
    site = Mock(logged_in=True)
    site.get_problem_info.return_value = {
        "title": "synthetic", "samples": [] if mode == "no_samples" else [{"input": "", "output": "42"}]
    }
    model = Mock()
    model.generate_code.return_value = "int main(){}"
    tester = Mock(gpp=None if mode == "missing" else "synthetic-compiler")
    tester.build.return_value = SimpleNamespace(ok=mode != "removed", status="NO_COMPILER", exe_path="fake")
    outcome = solve("synthetic", eoj_client=site, solver=model, tester=tester,
                    skip_login=True, skip_analysis=True, skip_test=mode == "skip",
                    max_retries=0 if mode == "zero_attempts" else 1)
    assert outcome.status == "UNVERIFIED"
    assert not outcome.ok and not outcome.tests_passed and not outcome.submitted
    site.submit.assert_not_called()


def test_runtime_crash_with_expected_output_is_not_pass(tmp_path, monkeypatch):
    tester = CodeTester(gpp="synthetic", workdir=str(tmp_path))
    monkeypatch.setattr("eojkit.asm.subprocess.run", lambda *a, **k: SimpleNamespace(
        stdout="42\n", stderr="synthetic crash", returncode=1))
    assert not tester.run_sample("fake.exe", {"output": "42\n"}).ok


@pytest.mark.parametrize("layout", ["ucrt64", "mingw64"])
def test_bundle_compiler_precedes_environment_and_path(tmp_path, monkeypatch, layout):
    from eojkit import tools, paths
    compiler = tmp_path / "toolchain" / layout / "bin" / "g++.exe"
    compiler.parent.mkdir(parents=True)
    compiler.touch()
    monkeypatch.setattr(paths, "APP_DIR", tmp_path)
    monkeypatch.setenv("EOJ_GPP", "other-compiler")
    try:
        assert tools.find_gpp(force=True) == str(compiler)
    finally:
        tools._GPP_PROBED = False


def test_cli_submission_requires_explicit_choice():
    from eoj_auto_solver import build_arg_parser
    parser = build_arg_parser()
    assert parser.parse_args([]).no_submit
    assert not parser.parse_args(["--submit"]).no_submit
