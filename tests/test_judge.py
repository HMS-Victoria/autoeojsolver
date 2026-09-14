# -*- coding: utf-8 -*-
"""EOJ 站点交互测试（离线，用本地 HTTP 服务器模拟 EOJ 页面）。"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eojkit.config import EOJConfig
from eojkit.judge.client import (
    EOJClient,
    PROBLEM_STATUS_MAP,
    SubmitResult,
    parse_verdict,
)

# ==========================================================================
# 题面 / 状态页 HTML 样本
# ==========================================================================

PROBLEM_HTML = """<html><body>
<div class="title">A + B Problem</div>
<div class="problem-body">
  <div class="passage">
    <p>Given two integers a and b, output a+b.</p>
    <p>Input has multiple test cases until EOF.</p>
  </div>
  <div class="example">
    <div class="input"><pre>1 2
</pre></div>
    <div class="output"><pre>3
</pre></div>
  </div>
  <div class="example">
    <div class="input"><pre>-5 5
</pre></div>
    <div class="output"><pre>0
</pre></div>
  </div>
  <div class="example">
    <div class="input"><pre>1000000000 1000000000
</pre></div>
    <div class="output"><pre>2000000000
</pre></div>
  </div>
</div>
<input type="hidden" name="csrfmiddlewaretoken" value="tok123">
<input type="hidden" name="problem" value="1001">
<select name="lang">
  <option value="cc17">C++17</option>
  <option value="cpp">C++11</option>
</select>
</body></html>"""

TABLE_SAMPLE_HTML = """<html><body>
<div class="problem-body">
  <div class="passage"><p>Sum</p></div>
  <table>
    <tr><td>Sample Input</td><td><pre>7 8</pre></td>
        <td>Sample Output</td><td><pre>15</pre></td></tr>
  </table>
</div>
</body></html>"""

NO_BODY_HTML = "<html><body><div class='other'>nothing here</div></body></html>"

STATUS_HTML_AC = """<html><body><table>
<tr><th>#</th><th>User</th><th>Nick</th><th>Result</th><th>Lang</th><th>Time</th></tr>
<tr><td>1</td><td>other</td><td>someone</td>
    <td><h5 class="status-span" data-status="1" data-score="0">Wrong Answer</h5></td>
    <td>cc17</td><td>1ms</td></tr>
<tr><td>2</td><td>tiger_P</td><td>tiger_P</td>
    <td><h5 class="status-span" data-status="0" data-score="100">Accepted</h5></td>
    <td>cc17</td><td>2ms</td></tr>
</table></body></html>"""

STATUS_HTML_PENDING = """<html><body><table>
<tr><th>#</th><th>User</th><th>Nick</th><th>Result</th><th>Lang</th><th>Time</th></tr>
<tr><td>1</td><td>tiger_P</td><td>x</td>
    <td><h5 class="status-span" data-status="7" data-score="0">Judging</h5></td>
    <td>cc17</td><td>-</td></tr>
</table></body></html>"""

STATUS_HTML_NONE_MINE = """<html><body><table>
<tr><th>#</th><th>User</th><th>Nick</th><th>Result</th><th>Lang</th><th>Time</th></tr>
<tr><td>1</td><td>other</td><td>someone</td><td>Accepted</td><td>cc17</td><td>1ms</td></tr>
</table></body></html>"""

LOGIN_HTML = """<html><body>
<form action="/login/" method="post">
  <input type="hidden" name="csrfmiddlewaretoken" value="csrf-abc">
  <input type="hidden" name="next" value="/">
  <input type="hidden" name="public_key" value="-----BEGIN PUBLIC KEY-----&#10;MFwwDQYJ&#10;-----END PUBLIC KEY-----">
  <img src="/captcha/image/abc123/" alt="captcha">
  <input type="hidden" name="captcha_0" value="hash0">
</form>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    routes = {}
    posts = []

    def log_message(self, *args):
        pass

    def _serve(self):
        entry = self.routes.get(self.path.split("?")[0], self.routes.get("*"))
        if entry is None:
            self.send_response(404)
            self.end_headers()
            return
        status, content_type, body = entry
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._serve()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _Handler.posts.append(
            {
                "path": self.path,
                "body": self.rfile.read(length).decode("utf-8", "replace"),
                "referer": self.headers.get("Referer"),
            }
        )
        entry = self.routes.get("POST " + self.path.split("?")[0])
        if entry is None:
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        status, content_type, body = entry
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def site():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.routes = {}
    _Handler.posts = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base, _Handler.routes, _Handler.posts
    finally:
        server.shutdown()
        server.server_close()


def _client(base, **kwargs):
    conf = EOJConfig(username="tiger_P", password="pw", base_url=base)
    client = EOJClient(conf, timeout=5)
    client.display_username = "tiger_P"
    client.logged_in = True
    return client


# ==========================================================================
# parse_verdict
# ==========================================================================

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Accepted", "AC"),
        ("Wrong Answer", "WA"),
        ("Time Limit Exceeded", "TLE"),
        ("Memory Limit Exceeded", "MLE"),
        ("Compile Error", "CE"),
        ("Runtime Error", "RE"),
        ("Judging", "PENDING"),
        ("Pending", "PENDING"),
        ("Presentation Error", "PE"),
        ("Something Else", "Something Else"),
        ("", None),
        (None, None),
    ],
)
def test_parse_verdict(text, expected):
    assert parse_verdict(text) == expected


def test_status_map_covers_eoj_codes():
    assert PROBLEM_STATUS_MAP["0"] == "AC"
    assert PROBLEM_STATUS_MAP["5"] == "CE"
    assert PROBLEM_STATUS_MAP["7"] == "PENDING"


# ==========================================================================
# 抓题
# ==========================================================================

def test_get_problem_info_extracts_all_samples(site):
    """回归：旧版 find() 只取第一个 example，多样例题会丢样例。"""
    base, routes, _posts = site
    routes["/problem/1001/"] = (200, "text/html; charset=utf-8", PROBLEM_HTML)
    client = _client(base)
    info = client.get_problem_info("1001")
    assert info is not None
    assert info["title"] == "A + B Problem"
    assert "Given two integers" in info["description"]
    assert len(info["samples"]) == 3
    assert info["samples"][0] == {"input": "1 2", "output": "3"}
    assert info["samples"][1] == {"input": "-5 5", "output": "0"}
    assert info["samples"][2]["output"] == "2000000000"


def test_get_problem_info_table_fallback(site):
    base, routes, _posts = site
    routes["/problem/2000/"] = (200, "text/html; charset=utf-8", TABLE_SAMPLE_HTML)
    client = _client(base)
    info = client.get_problem_info("2000")
    assert info is not None
    assert len(info["samples"]) == 1
    assert info["samples"][0]["input"] == "7 8"
    assert info["samples"][0]["output"] == "15"


def test_get_problem_info_handles_missing_body(site):
    base, routes, _posts = site
    routes["/problem/3000/"] = (200, "text/html; charset=utf-8", NO_BODY_HTML)
    client = _client(base)
    assert client.get_problem_info("3000") is None


def test_get_problem_info_handles_http_error(site):
    base, _routes, _posts = site
    client = _client(base)
    assert client.get_problem_info("4040") is None


# ==========================================================================
# 状态查询
# ==========================================================================

def test_check_status_reads_own_row(site):
    base, routes, _posts = site
    routes["/problem/status/"] = (200, "text/html; charset=utf-8", STATUS_HTML_AC)
    client = _client(base)
    assert client.check_status_once("1001") == "AC"


def test_check_status_reports_pending(site):
    base, routes, _posts = site
    routes["/problem/status/"] = (200, "text/html; charset=utf-8", STATUS_HTML_PENDING)
    client = _client(base)
    assert client.check_status_once("1001") == "PENDING"


def test_check_status_none_when_no_own_row(site):
    base, routes, _posts = site
    routes["/problem/status/"] = (200, "text/html; charset=utf-8", STATUS_HTML_NONE_MINE)
    client = _client(base)
    assert client.check_status_once("1001") is None


def test_check_status_contest_403_is_unknown(site):
    base, import_routes, _posts = site
    import_routes["*"] = (403, "text/html", "forbidden")
    client = _client(base)
    assert client.check_status_once("A", contest_id="1021") == "UNKNOWN"


def test_check_status_plain_403_returns_none(site):
    base, routes, _posts = site
    routes["*"] = (403, "text/html", "forbidden")
    client = _client(base)
    assert client.check_status_once("1001") is None


# ==========================================================================
# 提交
# ==========================================================================

def test_submit_302_success(site):
    base, routes, posts = site
    routes["/problem/1001/"] = (200, "text/html; charset=utf-8", PROBLEM_HTML)
    routes["POST /problem/1001/submit/"] = (200, "text/html", "ok")
    client = _client(base)
    result = client.submit("1001", "int main(){}")
    assert isinstance(result, SubmitResult)
    assert result.ok
    assert "status" in result.url
    assert posts and "code=int+main" in posts[-1]["body"] or "code=" in posts[-1]["body"]


def test_submit_picks_language_from_select(site):
    base, routes, posts = site
    routes["/problem/1001/"] = (200, "text/html; charset=utf-8", PROBLEM_HTML)
    client = _client(base)
    client.submit("1001", "int main(){}")
    assert "lang=cc17" in posts[-1]["body"], "应从 <select> 里挑到 cc17"


def test_submit_without_login_fails(site):
    base, _routes, _posts = site
    client = _client(base)
    client.logged_in = False
    result = client.submit("1001", "int main(){}")
    assert not result.ok
    assert "登录" in result.message


def test_submit_error_page_reports_failure(site):
    base, routes, _posts = site
    routes["/problem/1001/"] = (200, "text/html; charset=utf-8", PROBLEM_HTML)
    routes["POST /problem/1001/submit/"] = (200, "text/html; charset=utf-8", "<div>语言无效</div>")
    client = _client(base)
    result = client.submit("1001", "x", save_debug=False)
    assert not result.ok
    assert "语言无效" in result.message


# ==========================================================================
# 并发探测使用独立 session
# ==========================================================================

def test_per_thread_sessions_are_isolated(site):
    base, _routes, _posts = site
    client = _client(base)
    seen = {}
    import threading as _threading

    def grab():
        seen[_threading.get_ident()] = id(client.session)

    threads = [_threading.Thread(target=grab) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(seen) == 4
    assert len(set(seen.values())) == 4, "每个线程应拿到独立的 requests.Session"
    # 主线程自己的 session 与工作线程不同
    assert id(client.session) not in seen.values()
