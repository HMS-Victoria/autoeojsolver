# -*- coding: utf-8 -*-
"""
eojkit.llm.client 单元测试
==========================

全部离线运行：用一个本地 HTTP 服务器模拟 OpenAI 兼容接口，
覆盖重试、推理模型空正文回退、截断抬预算、鉴权失败等关键分支。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eojkit.config import LLMConfig
from eojkit.llm.client import (
    LLMAuthError,
    LLMClient,
    LLMError,
    LLMResponseError,
    build_chat_payload,
    extract_code,
    extract_markdown,
)

# ==========================================================================
# 本地模拟服务
# ==========================================================================

class _Handler(BaseHTTPRequestHandler):
    """按脚本化的响应序列返回，并记录收到的请求体。"""

    script = []
    received = []
    lock = threading.Lock()

    def log_message(self, *args):  # 静音
        pass

    def _send(self, status, payload=None, raw=None):
        body = raw if raw is not None else json.dumps(payload or {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send(200, {"object": "list", "data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-flash"}]})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        with _Handler.lock:
            _Handler.received.append(body)
            index = len(_Handler.received) - 1
        entry = _Handler.script[index] if index < len(_Handler.script) else _Handler.script[-1]
        status = entry.get("status", 200)
        if entry.get("raw") is not None:
            self._send(status, raw=entry["raw"])
        else:
            self._send(status, entry.get("payload", {}))


@pytest.fixture()
def mock_api():
    """启动模拟服务，返回 (base_url, script, received)。"""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.script = []
    _Handler.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        yield base, _Handler.script, _Handler.received
    finally:
        server.shutdown()
        server.server_close()


def _config(base_url, **kwargs):
    defaults = dict(
        provider="custom",
        base_url=base_url,
        api_key="sk-test-key",
        model="deepseek-v4-pro",
        max_retries=0,
        retry_backoff=0.01,
        timeout=10,
        max_tokens=256,
    )
    defaults.update(kwargs)
    return LLMConfig(**defaults)


def _ok(content="hello", reasoning="", finish="stop", usage=None, model="deepseek-v4-pro"):
    message = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    return {
        "status": 200,
        "payload": {
            "id": "req-1",
            "model": model,
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    }


# ==========================================================================
# extract_code / extract_markdown
# ==========================================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("```cpp\nint main(){}\n```", "int main(){}"),
        ("```c++\nint main(){}\n```", "int main(){}"),
        ("```\nint main(){}\n```", "int main(){}"),
        ("Here you go:\n```cpp\nint x=1;\n```\nDone.", "int x=1;"),
        ("#include <bits/stdc++.h>\nint main(){}", "#include <bits/stdc++.h>\nint main(){}"),
        ("```cpp\nint main(){return 0;}", "int main(){return 0;}"),
        ("```cpp\n\nint a;\n\nint b;\n```", "int a;\n\nint b;"),
        ("", ""),
    ],
)
def test_extract_code(raw, expected):
    assert extract_code(raw) == expected


def test_extract_code_prefers_cpp_over_other_fence():
    raw = "```python\nprint(1)\n```\n```cpp\nint main(){}\n```"
    assert extract_code(raw) == "int main(){}"


def test_extract_markdown_strips_markdown_fence():
    raw = "```markdown\n# 题目 1 - A+B\n\n## 题目大意\n求和\n```"
    assert extract_markdown(raw) == "# 题目 1 - A+B\n\n## 题目大意\n求和"


def test_extract_markdown_passthrough():
    raw = "# 题目 1\n\n## 解题思路\n直接输出"
    assert extract_markdown(raw) == raw


# ==========================================================================
# build_chat_payload
# ==========================================================================

def test_build_chat_payload_defaults():
    payload = build_chat_payload("m", [{"role": "user", "content": "hi"}])
    assert payload["model"] == "m"
    assert payload["stream"] is False
    assert payload["temperature"] == 0.2
    assert "response_format" not in payload


def test_build_chat_payload_extras():
    payload = build_chat_payload(
        "m",
        [],
        response_format={"type": "json_object"},
        top_p=0.9,
        stop=["\n\n"],
        extra={"seed": 7},
    )
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["top_p"] == 0.9
    assert payload["stop"] == ["\n\n"]
    assert payload["seed"] == 7


# ==========================================================================
# 客户端：探测 / 调用 / 重试
# ==========================================================================

def test_list_models_from_endpoint(mock_api):
    base, _script, _recv = mock_api
    client = LLMClient(_config(base))
    assert client.list_models() == ["deepseek-v4-pro", "deepseek-flash"]


def test_list_models_fallback_when_unreachable():
    client = LLMClient(_config("http://127.0.0.1:9/v1", provider="deepseek"))
    models = client.list_models(timeout=1)
    assert models == ["deepseek-v4-pro", "deepseek-flash"]


def test_chat_success(mock_api):
    base, script, received = mock_api
    script.append(_ok("pong"))
    client = LLMClient(_config(base))
    resp = client.chat([{"role": "user", "content": "ping"}])
    assert resp.content == "pong"
    assert resp.model == "deepseek-v4-pro"
    assert resp.usage["total_tokens"] == 15
    assert received[0]["messages"][0]["content"] == "ping"


def test_chat_retries_then_succeeds(mock_api):
    base, script, received = mock_api
    script.append({"status": 500, "payload": {"error": {"message": "boom"}}})
    script.append(_ok("recovered"))
    client = LLMClient(_config(base, max_retries=2))
    messages = []
    resp = client.chat([{"role": "user", "content": "x"}])
    assert resp.content == "recovered"
    assert resp.attempts == 2
    assert len(received) == 2


def test_chat_auth_error_not_retried(mock_api):
    base, script, received = mock_api
    script.append({"status": 401, "payload": {"error": {"message": "bad key"}}})
    client = LLMClient(_config(base, max_retries=3))
    with pytest.raises(LLMAuthError):
        client.chat([{"role": "user", "content": "x"}])
    assert len(received) == 1, "鉴权失败不应重试"


def test_reasoning_model_empty_content_falls_back(mock_api):
    """v4 系列把思考放在 reasoning_content；正文为空时必须能用思考内容兜底。"""
    base, script, _received = mock_api
    script.append(_ok(content="", reasoning="some reasoning", usage={"completion_tokens": 20}))
    client = LLMClient(_config(base))
    resp = client.chat([{"role": "user", "content": "x"}], expect_text=False)
    assert resp.content == ""
    assert resp.reasoning == "some reasoning"
    assert resp.text == "some reasoning"
    assert resp.reasoning_tokens == 0


def test_truncated_response_raises_budget(mock_api):
    """finish_reason=length 且正文明显不完整时，应放大 max_tokens 重试。"""
    base, script, received = mock_api
    # 花括号不配对 = 代码被截断
    script.append(_ok("```cpp\nint main(){\n  cout << 1;", finish="length"))
    script.append(_ok("```cpp\nint main(){}\n```"))
    client = LLMClient(_config(base, max_tokens=100, max_retries=2))
    resp = client.chat([{"role": "user", "content": "x"}])
    assert "int main(){}" in resp.content
    assert received[0]["max_tokens"] == 100
    assert received[1]["max_tokens"] == 200, "第二次应放大预算"


def test_truncated_but_complete_content_accepted(mock_api):
    """正文已完整时不应因 finish_reason=length 白烧 token 重试。"""
    base, script, received = mock_api
    script.append(_ok("```cpp\nint main(){}\n```", finish="length"))
    client = LLMClient(_config(base, max_tokens=100, max_retries=2))
    resp = client.chat([{"role": "user", "content": "x"}])
    assert resp.content == "```cpp\nint main(){}\n```"
    assert len(received) == 1, "正文完整就不该重试"


def test_truncated_plain_text_accepted(mock_api):
    base, script, received = mock_api
    script.append(_ok("# 题目 1\n\n## 题目大意\n求和", finish="length"))
    client = LLMClient(_config(base, max_tokens=100, max_retries=2))
    resp = client.chat([{"role": "user", "content": "x"}])
    assert "求和" in resp.content
    assert len(received) == 1


def test_empty_content_with_expect_text_retries(mock_api):
    base, script, _received = mock_api
    script.append(_ok(content="", reasoning=""))
    script.append(_ok("second try"))
    client = LLMClient(_config(base, max_retries=2))
    resp = client.chat([{"role": "user", "content": "x"}])
    assert resp.content == "second try"


def test_fallback_model_used_after_primary_fails(mock_api):
    base, script, received = mock_api
    # 请求顺序：pro 第1次 -> pro 第2次(降级前最后一次) -> flash
    script.append({"status": 500, "payload": {"error": {"message": "boom"}}})
    script.append({"status": 500, "payload": {"error": {"message": "boom"}}})
    script.append(_ok("from fallback", model="deepseek-flash"))
    client = LLMClient(
        _config(base, model="deepseek-v4-pro", fallback_models=["deepseek-flash"], max_retries=1)
    )
    resp = client.chat([{"role": "user", "content": "x"}])
    assert resp.content == "from fallback"
    assert received[0]["model"] == "deepseek-v4-pro"
    assert received[-1]["model"] == "deepseek-flash"


def test_missing_api_key_raises():
    client = LLMClient(_config("http://127.0.0.1:9/v1", api_key=""))
    with pytest.raises(LLMAuthError):
        client.chat([{"role": "user", "content": "x"}])


def test_health_check_reports_failure():
    client = LLMClient(_config("http://127.0.0.1:9/v1"))
    health = client.health_check(timeout=2)
    assert health["ok"] is False
    assert "error" in health


def test_health_check_success(mock_api):
    base, script, _received = mock_api
    script.append(_ok("pong"))
    client = LLMClient(_config(base))
    health = client.health_check()
    assert health["ok"] is True
    assert health["models"] == ["deepseek-v4-pro", "deepseek-flash"]


def test_malformed_json_raises(mock_api):
    base, script, _received = mock_api
    script.append({"status": 200, "raw": b"<html>not json</html>"})
    client = LLMClient(_config(base))
    with pytest.raises(LLMError):
        client.chat([{"role": "user", "content": "x"}])


def test_settings_snapshot_in_response(mock_api):
    base, script, _received = mock_api
    script.append(_ok("x"))
    client = LLMClient(_config(base))
    resp = client.chat([{"role": "user", "content": "y"}])
    assert "model=" in resp.summary()
    assert resp.latency >= 0
