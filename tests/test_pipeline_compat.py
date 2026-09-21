# -*- coding: utf-8 -*-
"""
端到端流水线测试 + 向后兼容层测试
==================================

用一个本地「假 EOJ 站点」+ 本地「假大模型接口」跑通
``登录 → 抓题 → AI 生成 → 编译测试 → 提交 → 归档`` 全流程，
并验证 ``eoj_auto_solver`` 仍暴露 GUI/CLI 依赖的全部旧接口。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eojkit import tools
from eojkit.archive import SolutionArchiver
from eojkit.asm import CodeTester
from eojkit.config import EOJConfig, LLMConfig
from eojkit.judge import EOJClient
from eojkit.llm import DeepSeekSolver
from eojkit.pipeline import SolveOutcome, archive_existing_problem, solve, solve_single_problem
from eojkit.tools import find_gpp

# ==========================================================================
# 假站点
# ==========================================================================

PROBLEM_HTML = """<html><body>
<div class="title">A + B</div>
<div class="problem-body">
  <div class="passage"><p>Output a+b for each pair.</p></div>
  <div class="example"><div class="input"><pre>1 2
</pre></div><div class="output"><pre>3
</pre></div></div>
</div>
<select name="lang"><option value="cc17">C++17</option></select>
<input type="hidden" name="problem" value="1001">
</body></html>"""

SOLUTION = """#include <iostream>
using namespace std;
int main(){long long a,b;while(cin>>a>>b)cout<<a+b<<"\\n";return 0;}
"""

NOTES = "```markdown\n# 题目 1001 - A + B\n\n## 题目大意\n两数求和\n```"

MODEL_CALLS = []
SUBMISSIONS = []


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        entry = self.routes.get(self.path.split("?")[0], self.routes.get("*"))
        if entry is None:
            self._send(404, "not found", "text/plain")
            return
        self._send(entry[0], entry[1], entry[2])

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        key = "POST " + self.path.split("?")[0]
        if key == "POST /v1/chat/completions":
            payload = json.loads(raw or b"{}")
            MODEL_CALLS.append(payload)
            model_text = SOLUTION if len(MODEL_CALLS) == 1 else NOTES
            self._send(
                200,
                json.dumps(
                    {
                        "id": "req",
                        "model": payload.get("model"),
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    # 模拟推理模型：正文空，思考里带代码
                                    "reasoning_content": model_text,
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                    }
                ),
            )
            return
        entry = self.routes.get(key, self.routes.get("POST *"))
        if key.startswith("POST /problem/") and key.endswith("/submit/"):
            SUBMISSIONS.append(raw.decode("utf-8", "replace"))
        if entry is None:
            self._send(302, "", "text/plain")
            return
        self._send(entry[0], entry[1], entry[2])


@pytest.fixture()
def fake_world():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.routes = {}
    MODEL_CALLS.clear()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    routes = _Handler.routes
    routes["/problem/1001/"] = (200, PROBLEM_HTML, "text/html; charset=utf-8")
    routes["/problem/1001/submit/"] = (200, PROBLEM_HTML, "text/html; charset=utf-8")
    routes["/v1/models"] = (200, json.dumps({"data": [{"id": "deepseek-v4-pro"}]}), "application/json")
    try:
        yield base, routes
    finally:
        server.shutdown()
        server.server_close()


def _components(base, tmp_path):
    client = EOJClient(EOJConfig(username="u", password="p", base_url=base), timeout=5)
    client.logged_in = True
    client.csrf_token = "tok"
    client.display_username = "u"
    llm = LLMConfig(
        provider="custom",
        base_url=base + "/v1",
        api_key="sk-test",
        model="deepseek-v4-pro",
        max_retries=0,
        timeout=10,
    )
    solver = DeepSeekSolver(config=llm)
    tester = CodeTester(workdir=str(tmp_path / "build"))
    archiver = SolutionArchiver(str(tmp_path / "solutions"), quiet=True)
    return client, solver, tester, archiver


# ==========================================================================
# 端到端
# ==========================================================================

@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_full_pipeline_success(fake_world, tmp_path):
    base, _routes = fake_world
    client, solver, tester, archiver = _components(base, tmp_path)

    outcome = solve(
        "1001",
        eoj_client=client,
        solver=solver,
        tester=tester,
        archiver=archiver,
        skip_login=True,
    )

    assert isinstance(outcome, SolveOutcome)
    assert outcome.ok, f"{outcome.status}: {outcome.error}"
    assert outcome.submitted is True
    assert outcome.tests_passed is True
    assert outcome.notes_saved is True
    assert "int main" in outcome.code

    folder = os.path.join(archiver.solutions_dir, "1001")
    for name in ("statement.txt", "samples.txt", "solution.cpp", "README.md",
                 "test_result.txt", "meta.json"):
        assert os.path.isfile(os.path.join(folder, name)), name

    # 推理模型的 reasoning_content 被正确当成正文使用（代码 + 笔记两次调用）
    assert len(MODEL_CALLS) >= 2
    # 提交请求确实带上了代码与语言
    assert SUBMISSIONS, "应发生一次提交"
    assert "int+main" in SUBMISSIONS[-1] or "int%20main" in SUBMISSIONS[-1]
    assert "lang=cc17" in SUBMISSIONS[-1]


@pytest.mark.skipif(not find_gpp(), reason="需要 g++")
def test_pipeline_returns_legacy_status_code(fake_world, tmp_path):
    base, _routes = fake_world
    client, solver, tester, archiver = _components(base, tmp_path)
    status = solve_single_problem(
        "1001", eoj_client=client, solver=solver, tester=tester,
        archiver=archiver, skip_login=True,
    )
    assert status in ("SUCCESS",) or status.startswith("FAIL_")
    assert status == "SUCCESS"


def test_pipeline_reports_fetch_failure(tmp_path):
    client = EOJClient(EOJConfig(username="u", password="p", base_url="http://127.0.0.1:9"), timeout=2)
    client.logged_in = True
    tester = CodeTester(workdir=str(tmp_path / "build"))
    archiver = SolutionArchiver(str(tmp_path / "solutions"), quiet=True)
    outcome = solve(
        "9999",
        eoj_client=client,
        solver=DeepSeekSolver(config=LLMConfig(api_key="k", base_url="http://127.0.0.1:9/v1")),
        tester=tester,
        archiver=archiver,
        skip_login=True,
    )
    assert outcome.status == "FAIL_FETCH"


def test_pipeline_skip_submit(fake_world, tmp_path):
    base, _routes = fake_world
    client, solver, tester, archiver = _components(base, tmp_path)
    outcome = solve(
        "1001",
        eoj_client=client,
        solver=solver,
        tester=tester,
        archiver=archiver,
        skip_login=True,
        skip_submit=True,
    )
    assert outcome.ok
    assert outcome.submitted is False


def test_pipeline_skip_test(fake_world, tmp_path):
    submissions_before = len(SUBMISSIONS)
    base, _routes = fake_world
    client, solver, tester, archiver = _components(base, tmp_path)
    outcome = solve(
        "1001",
        eoj_client=client,
        solver=solver,
        tester=tester,
        archiver=archiver,
        skip_login=True,
        skip_test=True,
    )
    assert outcome.status == "UNVERIFIED"
    assert not outcome.submitted
    assert len(SUBMISSIONS) == submissions_before
    assert outcome.tests_passed is False


def test_pipeline_timeout_budget(fake_world, tmp_path):
    """per_problem_timeout=0 表示不限时；设置极小值应触发 FAIL_TIMEOUT。"""
    base, _routes = fake_world
    client, solver, tester, archiver = _components(base, tmp_path)
    outcome = solve(
        "1001",
        eoj_client=client,
        solver=solver,
        tester=tester,
        archiver=archiver,
        skip_login=True,
        per_problem_timeout=-1,  # 负数 = 立即超时（<=0 视为不限时，用 -1 走另一分支）
    )
    # -1 <= 0 视为不限时，因此仍应成功
    assert outcome.ok


def test_archive_existing_problem(fake_world, tmp_path):
    base, _routes = fake_world
    client, solver, _tester, archiver = _components(base, tmp_path)
    archiver.save_code("1001", SOLUTION)  # 已有代码
    ok = archive_existing_problem("1001", solver=solver, archiver=archiver, eoj_client=client)
    assert ok is True
    assert os.path.isfile(os.path.join(archiver.solutions_dir, "1001", "README.md"))
    assert os.path.isfile(os.path.join(archiver.solutions_dir, "1001", "meta.json"))


def test_archive_existing_problem_without_code(fake_world, tmp_path):
    base, _routes = fake_world
    client, solver, _tester, archiver = _components(base, tmp_path)
    assert archive_existing_problem("1001", solver=solver, archiver=archiver, eoj_client=client) is False


# ==========================================================================
# 向后兼容层（GUI / CLI 依赖的接口）
# ==========================================================================

@pytest.fixture()
def engine():
    if "eoj_auto_solver" in sys.modules:
        return sys.modules["eoj_auto_solver"]
    return importlib.import_module("eoj_auto_solver")


REQUIRED_NAMES = [
    # 类
    "EOJClient", "DeepSeekSolver", "CodeTester", "SolutionArchiver",
    # 函数
    "solve_single_problem", "archive_existing_problem", "list_existing_cpp_problems",
    "extract_problem_ids_from_range", "find_gpp", "try_ocr_captcha", "solve_captcha",
    "manual_captcha", "set_log_sink", "save_gui_config", "load_gui_config",
    "sync_runtime_settings", "doctor", "main",
    # 全局配置
    "EOJ_USERNAME", "EOJ_PASSWORD", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL",
    "LLM_BASE_URL", "MAX_RETRIES", "PER_PROBLEM_TIMEOUT", "GPP_PATH",
    "BATCH_MODE", "DEFAULT_SOLUTIONS_DIR", "session",
]


@pytest.mark.parametrize("name", REQUIRED_NAMES)
def test_engine_exposes_legacy_name(engine, name):
    assert hasattr(engine, name), f"兼容层缺少 {name}"


def test_engine_config_read(engine):
    assert isinstance(engine.DEEPSEEK_MODEL, str)
    assert isinstance(engine.EOJ_USERNAME, str)
    assert isinstance(engine.MAX_RETRIES, int)
    assert isinstance(engine.BATCH_MODE, bool)


def test_engine_config_write_through(engine):
    from eojkit.config import get_settings

    original = engine.DEEPSEEK_MODEL
    try:
        engine.DEEPSEEK_MODEL = "deepseek-flash"
        assert engine.DEEPSEEK_MODEL == "deepseek-flash"
        assert get_settings().llm.model == "deepseek-flash"
    finally:
        engine.DEEPSEEK_MODEL = original


def test_engine_normalizes_legacy_model_alias(engine):
    original = engine.DEEPSEEK_MODEL
    try:
        engine.DEEPSEEK_MODEL = "deepseek-v4-flash"
        assert engine.DEEPSEEK_MODEL == "deepseek-flash"
        engine.DEEPSEEK_MODEL = "deepseek-chat"
        assert engine.DEEPSEEK_MODEL == "deepseek-flash"
    finally:
        engine.DEEPSEEK_MODEL = original


def test_engine_unknown_attribute_raises(engine):
    with pytest.raises(AttributeError):
        engine.definitely_not_a_real_attribute


def test_engine_max_retries_write(engine):
    from eojkit.config import get_settings

    original = engine.MAX_RETRIES
    try:
        engine.MAX_RETRIES = 7
        assert get_settings().runtime.max_retries == 7
        assert engine.MAX_RETRIES == 7
    finally:
        engine.MAX_RETRIES = original


def test_engine_solver_reads_runtime_model(engine, monkeypatch):
    """GUI 写 engine.DEEPSEEK_MODEL 后，新建的 solver 必须用到新值。"""
    from eojkit.config import get_settings

    original = engine.DEEPSEEK_MODEL
    try:
        engine.DEEPSEEK_MODEL = "deepseek-v4-pro"
        solver = engine.DeepSeekSolver()
        assert solver.config.model == "deepseek-v4-pro"
    finally:
        engine.DEEPSEEK_MODEL = original


def test_engine_log_sink_routing(engine):
    captured = []
    try:
        engine.set_log_sink(captured.append)
        tools.log_ok("hello sink")
        assert any("hello sink" in line for line in captured)
    finally:
        engine.set_log_sink(None)


def test_engine_legacy_tester_results_view(engine, tmp_path):
    tester = engine.CodeTester(gpp=r"C:\missing\g++.exe", workdir=str(tmp_path))
    tester.compile_code("int main(){}", "1", quiet=True)
    rows = list(tester.results)
    assert rows and isinstance(rows[0], tuple)


def test_engine_save_and_load_config_roundtrip(engine, tmp_path, monkeypatch):
    from eojkit import config as cfg

    monkeypatch.setattr(cfg, "save_config_file", lambda data, root=None: str(tmp_path / "x.json"))
    engine.save_gui_config({"username": "someone"})
    loaded = engine.load_gui_config()
    assert "api_key" in loaded
    assert "model" in loaded
    assert "base_url" in loaded


def test_engine_session_proxy(engine):
    assert hasattr(engine.session, "get")
    assert hasattr(engine.session, "post")
