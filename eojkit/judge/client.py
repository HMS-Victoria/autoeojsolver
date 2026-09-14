# -*- coding: utf-8 -*-
"""
eojkit.judge —— EOJ 站点交互
============================

覆盖 ``登录 → 抓题 → 提交 → 查状态`` 全流程。相对旧 ``EOJClient`` 的修复：

* **样例只取一个（文档说修了其实没修）**：旧代码用 ``find('div', class_='example')``
  只拿第一个样例容器，多样例题目的后续样例全部丢失 —— 这直接影响 AI 生成代码的
  正确率。现在 ``find_all`` 全量提取，并兼容 ``<pre>`` 缺失时回退到整块文本。
* **全局 session 被并发共享**：``fetch_contest_problems`` 用 4 线程探测
  ``local_id``，却共用一个 ``requests.Session``（非线程安全）。现在按线程隔离。
* **凭据来自全局变量**：改为读取 :class:`~eojkit.config.EOJConfig`，
  GUI 运行时赋值通过引擎兼容层同步。
* **提交结果只有 URL**：``submit_code`` 现在返回 :class:`SubmitResult`，
  含状态码、判题链接、错误原因与调试页面路径。

Designed by HMS_Victorious
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..config import EOJConfig, get_settings
from ..tools import (
    batch_mode_enabled,
    ensure_temp_dir,
    log_fail,
    log_line,
    log_ok,
    log_warn,
    solve_captcha,
)

__all__ = ["EOJClient", "SubmitResult", "PROBLEM_STATUS_MAP", "parse_verdict"]

DEFAULT_BASE_URL = "https://acm.ecnu.edu.cn"

#: EOJ 状态页 ``data-status`` 数值 → 判词
PROBLEM_STATUS_MAP = {
    "0": "AC",
    "1": "WA",
    "2": "TLE",
    "3": "MLE",
    "4": "RE",
    "5": "CE",
    "6": "PENDING",
    "7": "PENDING",
}

_VERDICT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    # 注意顺序：更具体的先匹配，避免 "Runtime Error" 被 "Time" 抢走
    ("Accepted", "AC"),
    ("Wrong", "WA"),
    ("Runtime", "RE"),
    ("Time Limit", "TLE"),
    ("Time", "TLE"),
    ("Memory", "MLE"),
    ("Compile", "CE"),
    ("Presentation", "PE"),
    ("Output Limit", "OLE"),
    ("Partially", "PARTIAL"),
    ("Pending", "PENDING"),
    ("Judging", "PENDING"),
)

#: 提交语言优先级（不同竞赛/题目开放的语言不同）
LANG_PREFERENCE = ("cc17", "cpp17", "cpp20", "cpp", "cc", "gcc")

#: 这些文本虽然可能出现在 ``div.title`` 里，但它们是**小标题**而不是题目标题
_RESERVED_TITLES = {
    "input", "output", "sample", "samples", "examples", "example",
    "输入", "输出", "输入格式", "输出格式", "样例", "样例输入", "样例输出",
    "题目描述", "提示", "说明", "hint", "note", "notes",
    "description", "题目标签", "服务",
}


def parse_verdict(result_text: Optional[str]) -> Optional[str]:
    """把状态页文本映射为标准判词。"""
    if not result_text:
        return None
    for keyword, verdict in _VERDICT_PATTERNS:
        if keyword.lower() in result_text.lower():
            return verdict
    return result_text.strip()


@dataclass
class SubmitResult:
    """一次提交的结构化结果。"""

    ok: bool = False
    url: str = ""                 # 判题状态链接
    http_status: int = 0
    message: str = ""
    debug_path: str = ""
    lang: str = ""
    verdict: Optional[str] = None

    def __bool__(self) -> bool:
        return self.ok


class EOJClient:
    """EOJ 网站交互客户端。

    :param config: EOJ 账号配置；默认取全局 Settings。
    :param logger: 可选日志回调。
    """

    BASE_URL = DEFAULT_BASE_URL

    def __init__(self, config: Optional[EOJConfig] = None, *, logger=None, timeout: int = 20):
        self._explicit_config = config is not None
        self.config = config or get_settings().eoj
        self.BASE_URL = (self.config.base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._logger = logger

        self.logged_in = False
        self.csrf_token: Optional[str] = None
        self.display_username = ""
        self.last_status_code: Optional[int] = None
        self._contest_cache: Dict[str, Tuple[List[Dict], float]] = {}
        self._cache_lock = threading.Lock()

        # 按线程隔离 session（探测 local_id 时是多线程并发）
        self._local = threading.local()
        self._sessions: List[requests.Session] = []
        self._sessions_lock = threading.Lock()

        proxy = get_settings().runtime.proxy
        self._proxies = {"http": proxy, "https": proxy} if proxy else None

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    def _emit(self, message: str) -> None:
        if self._logger:
            try:
                self._logger(message)
                return
            except Exception:  # noqa: BLE001
                pass
        log_line(message)

    @property
    def session(self) -> requests.Session:
        """当前线程的会话（线程安全）。"""
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                }
            )
            if self._proxies:
                sess.proxies.update(self._proxies)
            else:
                sess.trust_env = False
            self._local.session = sess
            with self._sessions_lock:
                self._sessions.append(sess)
        return sess

    def close(self) -> None:
        with self._sessions_lock:
            sessions = list(self._sessions)
            self._sessions.clear()
        for sess in sessions:
            try:
                sess.close()
            except Exception:  # noqa: BLE001
                pass

    def _get(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.get(url, **kwargs)
        self.last_status_code = resp.status_code
        return resp

    def _post(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.post(url, **kwargs)
        self.last_status_code = resp.status_code
        return resp

    def _sync_config(self) -> None:
        if self._explicit_config:
            return
        live = get_settings().eoj
        self.config = live
        self.BASE_URL = (live.base_url or DEFAULT_BASE_URL).rstrip("/")

    # ------------------------------------------------------------------
    # HTML 解析小工具
    # ------------------------------------------------------------------
    @staticmethod
    def _get_csrf(text: str) -> Optional[str]:
        match = re.search(
            r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', text or ""
        )
        return match.group(1) if match else None

    @staticmethod
    def _rsa_encrypt_password(password: str, pubkey_pem: str) -> str:
        """RSA-OAEP-SHA256 加密密码（与 EOJ 前端 forge.min.js 行为一致）。"""
        import base64

        from Crypto.Cipher import PKCS1_OAEP
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA

        key = RSA.importKey(pubkey_pem)
        cipher = PKCS1_OAEP.new(key, hashAlgo=SHA256)
        return base64.b64encode(cipher.encrypt(password.encode("utf-8"))).decode()

    @staticmethod
    def _extract_value(text: str, name: str) -> Optional[str]:
        """提取 ``name=xxx`` 的 value（兼容单/双引号与多行值）。"""
        pattern = re.compile(
            r"name\s*=\s*['\"]" + re.escape(name) + r"['\"]\s*[^>]*\s*value\s*=\s*['\"](.+?)['\"]",
            re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(text or "")
        if match:
            return match.group(1).strip()
        pattern2 = re.compile(
            r"id\s*=\s*['\"]id_" + re.escape(name) + r"['\"]\s*[^>]*\s*value\s*=\s*['\"](.+?)['\"]",
            re.DOTALL | re.IGNORECASE,
        )
        match2 = pattern2.search(text or "")
        return match2.group(1).strip() if match2 else None

    @staticmethod
    def _find_captcha_url(html: str) -> Optional[str]:
        patterns = (
            r'<img[^>]*src\s*=\s*[\'"](/captcha/image/[^\'"]+)[\'"]',
            r'<img[^>]*src\s*=\s*[\'"]([^\'"]*captcha[^\'"]*)[\'"]',
        )
        for pattern in patterns:
            match = re.search(pattern, html or "", re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        max_attempts: Optional[int] = None,
    ) -> bool:
        """登录 EOJ（RSA 加密密码 + 验证码识别，失败自动换一张验证码重试）。

        EOJ 的验证码是「小学算术题」，公式类（如 ``3 times 7``）靠 ddddocr
        识别本来就容易出错。旧版失败即放弃；现在会重新拉取验证码重试，
        批量模式下显著提高无人值守成功率。
        """
        self._sync_config()
        username = (username if username is not None else self.config.username) or ""
        password = password if password is not None else self.config.password

        if not username or not password:
            log_fail("未配置 EOJ 账号或密码（环境变量 EOJ_USERNAME / EOJ_PASSWORD）")
            return False

        self._emit("\n" + "=" * 50)
        self._emit("  登录 EOJ...")
        self._emit("=" * 50)

        if max_attempts is None:
            max_attempts = 3 if batch_mode_enabled() else 1

        last_error = ""
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                self._emit(f"  [重试] 第 {attempt}/{max_attempts} 次登录尝试（换新验证码）...")
                time.sleep(0.5)
            ok, last_error = self._login_once(username, password)
            if ok:
                log_ok("登录成功！" if attempt == 1 else f"登录成功（第 {attempt} 次尝试）")
                self.logged_in = True
                self._refresh_profile()
                return True
            if self._is_captcha_error(last_error):
                self._emit(f"  [WARN] 验证码识别错误: {last_error}")
                continue
            log_fail("登录失败！")
            if last_error:
                self._emit(f"  错误: {last_error}")
            return False

        log_fail(f"登录失败！已尝试 {max_attempts} 次（验证码识别率不足）")
        if last_error:
            self._emit(f"  错误: {last_error}")
        self._emit("  [提示] 可安装/更新 ddddocr，或在不加 --batch 的情况下手动输入验证码")
        return False

    @staticmethod
    def _is_captcha_error(message: str) -> bool:
        text = (message or "").lower()
        return any(keyword in text for keyword in ("认证码", "验证码", "captcha"))

    def _login_once(self, username: str, password: str) -> Tuple[bool, str]:
        """执行一次完整登录，返回 ``(是否成功, 错误信息)``。"""
        try:
            page = self._get(f"{self.BASE_URL}/login/")
        except requests.RequestException as exc:
            return False, f"无法访问登录页: {exc}"

        csrf = self._get_csrf(page.text)
        if not csrf:
            return False, "无法获取 CSRF token"

        # RSA 公钥
        encrypted_password = password
        pubkey_raw = self._extract_value(page.text, "public_key")
        if pubkey_raw:
            pubkey_b64 = re.sub(r"-----[A-Z ]+-----", "", pubkey_raw.replace("\r", "").replace("\n", "")).strip()
            pubkey_pem = f"-----BEGIN PUBLIC KEY-----\n{pubkey_b64}\n-----END PUBLIC KEY-----"
            try:
                encrypted_password = self._rsa_encrypt_password(password, pubkey_pem)
            except Exception as exc:  # noqa: BLE001
                log_warn(f"RSA 加密失败 ({exc})，回退明文密码")

        next_value = self._extract_value(page.text, "next") or "/login/"

        # 验证码
        captcha_path = self._find_captcha_url(page.text)
        captcha_answer = ""
        captcha_0 = self._extract_value(page.text, "captcha_0") or ""
        if captcha_path:
            captcha_url = urljoin(self.BASE_URL + "/", captcha_path.lstrip("/"))
            try:
                captcha_resp = self._get(captcha_url)
                captcha_answer = solve_captcha(captcha_resp.content) or ""
            except requests.RequestException as exc:
                log_warn(f"验证码获取失败: {exc}")
        else:
            log_warn("未找到验证码图片，尝试不带验证码登录")

        login_data = {
            "csrfmiddlewaretoken": csrf,
            "next": next_value,
            "username": username,
            "password": encrypted_password,
            "captcha_0": captcha_0,
            "captcha_1": captcha_answer,
            "remember_me": "on",
            "public_key": pubkey_raw or "",
        }

        try:
            resp = self._post(
                f"{self.BASE_URL}/login/",
                data=login_data,
                headers={"Referer": f"{self.BASE_URL}/login/"},
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            return False, f"登录请求失败: {exc}"

        if "login" not in resp.url.lower():
            return True, ""

        message = ""
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            for selector in ("div.error", "div.ui.error.message"):
                node = soup.select_one(selector)
                if node and node.get_text(strip=True):
                    message = node.get_text(strip=True)[:200]
                    break
        except Exception:  # noqa: BLE001
            pass
        return False, message

    def _refresh_profile(self) -> None:
        """登录后抓一次题面页，取 CSRF 与显示昵称。"""
        try:
            resp = self._get(f"{self.BASE_URL}/problem/1001/")
            self.csrf_token = self._get_csrf(resp.text)
            soup = BeautifulSoup(resp.text, "html.parser")
            for dropdown in soup.find_all("div", class_="dropdown"):
                text_div = dropdown.find("div", class_="text")
                if text_div and text_div.get_text(strip=True):
                    self.display_username = text_div.get_text(strip=True)
                    log_ok(f"显示昵称: {self.display_username}")
                    break
        except requests.RequestException:
            pass

    def ensure_login(self) -> bool:
        """未登录则登录一次。"""
        if self.logged_in:
            return True
        return self.login()

    # ------------------------------------------------------------------
    # 抓题
    # ------------------------------------------------------------------
    def get_problem_info(self, problem_id, contest_id=None) -> Optional[Dict]:
        """抓取题目描述与**全部**样例。

        返回 ``{id, title, description, full_html, samples, url, contest_id}``。
        """
        self._sync_config()
        if contest_id:
            self._emit(f"\n  [获取题目] Contest {contest_id} Problem {problem_id}...")
            url = f"{self.BASE_URL}/contest/{contest_id}/problem/{problem_id}/"
        else:
            self._emit(f"\n  [获取题目] Problem {problem_id}...")
            url = f"{self.BASE_URL}/problem/{problem_id}/"

        try:
            resp = self._get(url)
        except requests.RequestException as exc:
            log_fail(f"请求题目页失败: {exc}")
            return None

        if resp.status_code != 200:
            log_fail(f"无法获取题目 (HTTP {resp.status_code})")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        title = f"Problem {problem_id}"
        for selector in ("h1", ".ui.header", "h2", "title", "div.title"):
            node = soup.select_one(selector)
            if not node:
                continue
            text = node.get_text(strip=True)
            # 注意：EOJ 的子标题也用 div.title（"输入格式"/"Input"），必须排除，
            # 否则会像旧版一样把标题抓成 "Input"。
            if text and text not in _RESERVED_TITLES:
                title = text
                break
        if title.endswith("- ECNU Online Judge"):
            title = title[: -len("- ECNU Online Judge")].strip()
        if title.startswith("Problem #"):
            title = title[len("Problem #"):].strip()

        body = soup.find("div", class_="problem-body") or soup.find("div", class_="ui container")
        if not body:
            log_fail("无法获取题目内容（problem-body 缺失）")
            return None

        passage = body.find("div", class_="passage")
        description = (passage or body).get_text("\n", strip=True)

        samples = self._extract_samples(body)

        info = {
            "id": problem_id,
            "title": title,
            "description": description,
            "full_html": str(body),
            "samples": samples,
            "url": url,
            "contest_id": contest_id,
        }
        log_ok(f"题目: {title} (样例: {len(samples)} 个)")
        if not samples:
            log_warn("未提取到样例数据，AI 只能依据题面描述作答")
        return info

    @staticmethod
    def _extract_samples(body) -> List[Dict[str, str]]:
        """提取所有样例（修复旧版只取第一个 ``div.example`` 的问题）。"""
        samples: List[Dict[str, str]] = []

        def _read_pre(container) -> str:
            if container is None:
                return ""
            pre = container.find("pre")
            target = pre if pre is not None else container
            return target.get_text("\n", strip=True)

        containers = body.find_all("div", class_="example")
        for container in containers:
            data_in = _read_pre(container.find("div", class_="input"))
            data_out = _read_pre(container.find("div", class_="output"))
            if data_in or data_out:
                samples.append({"input": data_in, "output": data_out})

        if samples:
            return samples

        # 兜底：有些主题用 <table class="ui table"> 里的 Sample Input/Output 两列
        for table in body.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2 and "input" in cells[0].get_text(strip=True).lower():
                    data_in = _read_pre(cells[1])
                    data_out = ""
                    if len(cells) >= 4 and "output" in cells[2].get_text(strip=True).lower():
                        data_out = _read_pre(cells[3])
                    if data_in or data_out:
                        samples.append({"input": data_in, "output": data_out})
        return samples

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------
    def _pick_language(self, html: str, contest_id=None) -> str:
        """从提交页的 ``<select>`` 里挑一个可用的 C++ 语言；失败用默认值。"""
        try:
            soup = BeautifulSoup(html or "", "html.parser")
            options = []
            for select in soup.find_all("select"):
                name = (select.get("name") or "").lower()
                if "lang" not in name and "language" not in name:
                    continue
                for option in select.find_all("option"):
                    value = (option.get("value") or "").strip()
                    label = option.get_text(strip=True)
                    if value:
                        options.append((value, label))
            if options:
                for preferred in LANG_PREFERENCE:
                    for value, label in options:
                        if value.lower() == preferred:
                            return value
                for value, label in options:
                    blob = f"{value} {label}".lower()
                    if "c++" in blob or "g++" in blob:
                        return value
        except Exception:  # noqa: BLE001
            pass
        return "cpp" if contest_id else "cc17"

    def submit_code(self, problem_id, code: str, contest_id=None) -> Optional[str]:
        """提交代码，成功返回判题状态页 URL（保持旧返回类型）。

        .. note::
           需要结构化结果时请用 :meth:`submit`。
        """
        result = self.submit(problem_id, code, contest_id=contest_id)
        return result.url or None

    def submit(self, problem_id, code: str, contest_id=None, *, save_debug: bool = True) -> SubmitResult:
        """提交代码并返回 :class:`SubmitResult`。"""
        self._sync_config()
        if contest_id:
            self._emit(f"\n  [提交] 提交代码到 Contest {contest_id} Problem {problem_id}...")
            submit_url = f"{self.BASE_URL}/contest/{contest_id}/submit/{problem_id}"
            referer_url = f"{self.BASE_URL}/contest/{contest_id}/problem/{problem_id}/"
        else:
            self._emit(f"\n  [提交] 提交代码到 Problem {problem_id}...")
            submit_url = f"{self.BASE_URL}/problem/{problem_id}/submit/"
            referer_url = f"{self.BASE_URL}/problem/{problem_id}/"

        if not self.logged_in:
            log_fail("未登录，无法提交")
            return SubmitResult(ok=False, message="未登录")

        csrf = self.csrf_token
        submit_page_html = ""
        try:
            if contest_id or not csrf:
                page = self._get(referer_url)
                submit_page_html = page.text
                csrf = self._get_csrf(page.text) or csrf
                if csrf and not contest_id:
                    self.csrf_token = csrf
        except requests.RequestException as exc:
            log_warn(f"预取提交页失败: {exc}")

        lang = self._pick_language(submit_page_html, contest_id)
        payload = {
            "csrfmiddlewaretoken": csrf or "",
            "code": code,
            "problem": problem_id,
            "lang": lang,
        }

        try:
            resp = self._post(submit_url, data=payload, headers={"Referer": referer_url})
        except requests.RequestException as exc:
            log_fail(f"提交请求异常: {exc}")
            return SubmitResult(ok=False, message=str(exc), lang=lang)

        if resp.status_code == 302:
            location = resp.headers.get("Location", "")
            full = urljoin(self.BASE_URL + "/", location) if location else ""
            log_ok(f"代码已提交 (302 → {location or '(无 Location)'})")
            return SubmitResult(ok=True, url=full, http_status=302, lang=lang)

        if resp.status_code == 200:
            error_text = ""
            match = re.search(r"语言无效|提交失败|验证码|Invalid|error", resp.text or "")
            if match:
                error_text = match.group(0)
            if error_text:
                debug_path = self._save_debug(problem_id, resp.text) if save_debug else ""
                log_fail(f"提交不成功: {error_text}")
                return SubmitResult(
                    ok=False,
                    http_status=200,
                    message=error_text,
                    debug_path=debug_path,
                    lang=lang,
                )
            status_url = (
                f"{self.BASE_URL}/contest/{contest_id}/status/?problem={problem_id}"
                if contest_id
                else f"{self.BASE_URL}/problem/status/?problem={problem_id}"
            )
            log_ok("代码已提交 (HTTP 200)")
            self._emit(f"  [提交] 查看状态: {status_url}")
            return SubmitResult(ok=True, url=status_url, http_status=200, lang=lang)

        debug_path = self._save_debug(problem_id, resp.text) if save_debug else ""
        log_fail(f"提交失败 (HTTP {resp.status_code})")
        message = ""
        try:
            soup = BeautifulSoup(resp.text or "", "html.parser")
            node = soup.select_one("div.error") or soup.select_one("div.ui.error.message")
            if node:
                message = node.get_text(strip=True)[:300]
                self._emit(f"  [FAIL] 错误信息: {message}")
        except Exception:  # noqa: BLE001
            pass
        return SubmitResult(
            ok=False,
            http_status=resp.status_code,
            message=message,
            debug_path=debug_path,
            lang=lang,
        )

    @staticmethod
    def _save_debug(problem_id, html: str) -> str:
        """把调试页面存到临时目录（不再污染项目根目录），返回路径。"""
        path = os.path.join(
            ensure_temp_dir(), f"debug_submit_{problem_id}_{time.strftime('%H%M%S')}.html"
        )
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html or "")
            log_line(f"  [DEBUG] 响应已保存: {path}")
        except OSError:
            return ""
        return path

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def _target_users(self, current_user: Optional[str] = None) -> List[str]:
        """用于匹配状态页行归属的用户名列表（昵称优先）。"""
        targets: List[str] = []
        for candidate in (current_user, self.display_username, self.config.username):
            if candidate and candidate not in targets:
                targets.append(candidate)
        return targets

    def check_status_once(
        self,
        problem_id,
        current_user=None,
        debug_html=False,
        contest_id=None,
    ) -> Optional[str]:
        """扫一次状态页，返回自己的判词（``None`` = 没找到自己的提交）。"""
        self._sync_config()
        targets = self._target_users(current_user)
        if contest_id:
            status_url = f"{self.BASE_URL}/contest/{contest_id}/status/?problem={problem_id}"
        else:
            status_url = f"{self.BASE_URL}/problem/status/?problem={problem_id}"

        try:
            resp = self._get(status_url, timeout=10)
        except requests.RequestException as exc:
            log_warn(f"状态页请求失败: {exc}")
            return None

        if resp.status_code == 403:
            if contest_id:
                log_line(f"  [..] 竞赛 {contest_id} 状态页返回 403，跳过状态查询")
                return "UNKNOWN"
            log_warn("状态页返回 403，可能未登录")
            return None
        if resp.status_code != 200:
            log_warn(f"状态页返回 HTTP {resp.status_code}")
            return None

        if debug_html:
            self._emit(f"  [DEBUG] status 页长度: {len(resp.text)} 字符")
            self._emit(f"  [DEBUG] 前 3000 字符:\n{resp.text[:3000]}")

        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.find_all("tr")[1:15]:
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            user_found = False
            for index in (1, 2):
                if index < len(cells):
                    cell_text = cells[index].get_text(strip=True).lower()
                    if any(target.lower() in cell_text for target in targets):
                        user_found = True
                        break
            if not user_found:
                continue

            if debug_html:
                self._emit(f"  [DEBUG] 找到自己的行: {str(row)[:500]}")

            status_node = row.find("h5", class_=re.compile(r"status"))
            if status_node:
                data_status = status_node.get("data-status", "")
                score = status_node.get("data-score", "")
                if debug_html:
                    self._emit(f"  [DEBUG] data-status={data_status}, data-score={score}")
                if data_status in PROBLEM_STATUS_MAP:
                    return PROBLEM_STATUS_MAP[data_status]
                if data_status:
                    try:
                        if int(score) == 100:
                            return "AC"
                    except (TypeError, ValueError):
                        pass
                    return data_status

            for span in row.find_all("span"):
                verdict = parse_verdict(span.get_text(strip=True))
                if verdict in {v for _k, v in _VERDICT_PATTERNS}:
                    return verdict

            for index in (3, 4):
                if index < len(cells):
                    text = cells[index].get_text(strip=True)
                    if text and text != "-":
                        verdict = parse_verdict(text)
                        if verdict:
                            return verdict
            return "PENDING"

        return None

    def check_submission_status(self, problem_id, max_wait=30) -> str:
        """轮询等待判题结果（最长 ``max_wait`` 秒）。"""
        self._sync_config()
        status_url = f"{self.BASE_URL}/problem/status/?problem={problem_id}"
        deadline = time.time() + max_wait
        while time.time() < deadline:
            verdict = self.check_status_once(problem_id)
            if verdict and verdict not in ("PENDING", "UNKNOWN"):
                self._emit(f"  [状态] {verdict}")
                return verdict
            time.sleep(2)
        return "Unknown"

    # ------------------------------------------------------------------
    # 题目列表
    # ------------------------------------------------------------------
    def fetch_problem_list(self, page=1) -> List[Dict]:
        """获取题目列表某页。"""
        if not self.logged_in:
            log_warn("未登录，无法获取完整题目列表")
            return []
        self._emit(f"\n  [获取列表] 获取题目列表第 {page} 页...")
        try:
            resp = self._get(f"{self.BASE_URL}/problem/list/?page={page}")
        except requests.RequestException as exc:
            log_fail(f"请求失败: {exc}")
            return []
        if resp.status_code != 200:
            log_fail(f"无法获取题目列表 (HTTP {resp.status_code})")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            log_fail("未找到题目表格")
            return []

        problems: List[Dict] = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            pid = cells[0].get_text(strip=True)
            if not (pid and pid.isdigit()):
                continue
            link = cells[1].find("a")
            title = link.get_text(strip=True) if link else cells[1].get_text(strip=True)
            solved = "".join(ch for ch in cells[2].get_text(strip=True) if ch.isdigit())
            problems.append({"id": pid, "title": title, "solved_count": solved})

        log_ok(f"获取到 {len(problems)} 道题")
        return problems

    def fetch_all_problem_ids(self, max_pages=100) -> List[Dict]:
        """遍历分页获取所有题目。"""
        collected: List[Dict] = []
        for page in range(1, max_pages + 1):
            batch = self.fetch_problem_list(page)
            if not batch:
                break
            collected.extend(batch)
            time.sleep(0.5)
        self._emit(f"\n  [全部] 共获取到 {len(collected)} 道题")
        return collected

    def fetch_contest_problems(self, contest_id, force_refresh=False) -> List[Dict]:
        """获取竞赛题目列表（多策略兜底 + 并发探测 local_id）。"""
        if not self.logged_in:
            log_warn("未登录，无法获取竞赛题目列表")
            return []

        cache_key = str(contest_id)
        with self._cache_lock:
            cached = self._contest_cache.get(cache_key)
        if not force_refresh and cached and time.time() - cached[1] < 60:
            return cached[0]

        self._emit(f"\n  [获取竞赛] 获取竞赛 {contest_id} 题目列表...")
        link_pattern = re.compile(r"/contest/" + re.escape(str(contest_id)) + r"/problem/([A-Za-z0-9]+)/?$")
        problems: List[Dict] = []

        def _harvest(source_soup, source_label: str) -> None:
            for anchor in source_soup.find_all("a", href=link_pattern):
                href = anchor.get("href", "")
                match = link_pattern.search(href)
                if not match:
                    continue
                pid = match.group(1)
                title = anchor.get_text(strip=True)
                if not title or len(title) <= 1:
                    continue
                if any(item["id"] == pid for item in problems):
                    continue
                problems.append(
                    {
                        "id": pid,
                        "title": title,
                        "url": urljoin(self.BASE_URL + "/", href.lstrip("/")),
                        "local_id": None,
                    }
                )
            if problems:
                log_ok(f"从{source_label}找到 {len(problems)} 道题目")

        try:
            detail = self._get(f"{self.BASE_URL}/contest/{contest_id}/")
        except requests.RequestException as exc:
            log_fail(f"无法获取竞赛页面: {exc}")
            return []

        if detail.status_code != 200:
            # 竞赛首页 403/404 时仍尝试直接访问题目列表页
            log_warn(f"竞赛首页返回 HTTP {detail.status_code}，继续尝试其它入口")
        else:
            _harvest(BeautifulSoup(detail.text, "html.parser"), "首页")

        if not problems:
            self._emit("  [尝试] 首页未找到，尝试直接访问题目列表页...")
            for path in (f"/contest/{contest_id}/problem/", f"/contest/{contest_id}/problems/"):
                try:
                    resp = self._get(f"{self.BASE_URL}{path}", timeout=10)
                except requests.RequestException:
                    continue
                if resp.status_code == 200:
                    _harvest(BeautifulSoup(resp.text, "html.parser"), path)
                    if problems:
                        break

        if not problems:
            self._emit("  [尝试] 检查 standings 页面...")
            try:
                standings = self._get(f"{self.BASE_URL}/contest/{contest_id}/standings/")
            except requests.RequestException:
                standings = None
            if standings is not None and standings.status_code == 200:
                soup = BeautifulSoup(standings.text, "html.parser")
                table = soup.find("table")
                head = table.find("thead") if table else None
                if head:
                    for th in head.find_all("th")[1:]:
                        text = th.get_text(strip=True)
                        if not text or text == "#" or text.isdigit() or len(text) >= 50:
                            continue
                        letters = re.findall(r"[A-Z]", text)
                        pid = letters[0] if letters else text
                        if any(item["id"] == pid for item in problems):
                            continue
                        problems.append(
                            {
                                "id": pid,
                                "title": text,
                                "url": f"{self.BASE_URL}/contest/{contest_id}/problem/{pid}/",
                                "local_id": None,
                            }
                        )
                if problems:
                    log_ok(f"从 standings 找到 {len(problems)} 道题目")

        if not problems:
            log_fail("无法获取竞赛题目列表")
            self._emit("  [提示] 可能原因：未登录、竞赛未开始/已结束、无权访问该竞赛")
            return []

        self._probe_local_ids(problems)
        log_ok(f"共 {len(problems)} 道题目")
        for item in problems[:10]:
            suffix = f" (本地题号: {item['local_id']})" if item.get("local_id") else ""
            self._emit(f"    [{item['id']}] {item['title']}{suffix}")
        if len(problems) > 10:
            self._emit(f"    ... 共 {len(problems)} 题，仅显示前 10 题")

        with self._cache_lock:
            self._contest_cache[cache_key] = (problems, time.time())
        return problems

    def _probe_local_ids(self, problems: List[Dict], workers: int = 4) -> None:
        """并发探测竞赛题目对应的主站题号（汇总打印，避免刷屏卡 GUI）。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        self._emit("  [信息] 并发探测各题目的本地题号...")

        def _probe(item: Dict) -> str:
            try:
                resp = self._get(item["url"], timeout=5)
                if resp.status_code != 200:
                    return "http_error"
                match = re.search(
                    r'name=["\']problem["\'][^>]*value=["\'](\d+)["\']', resp.text
                )
                if match:
                    item["local_id"] = match.group(1)
                    return "found"
                return "not_found"
            except Exception:  # noqa: BLE001
                return "exception"

        counters = {"found": 0, "not_found": 0, "http_error": 0, "exception": 0}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_probe, item) for item in problems]
            for future in as_completed(futures):
                try:
                    counters[future.result()] = counters.get(future.result(), 0) + 1
                except Exception:  # noqa: BLE001
                    counters["exception"] += 1
        self._emit(
            f"  [信息] 探测完成: {len(problems)} 题, 成功获取 local_id: {counters['found']}"
            + (f", 未找到: {counters['not_found']}" if counters["not_found"] else "")
            + (f", HTTP异常: {counters['http_error']}" if counters["http_error"] else "")
            + (f", 异常: {counters['exception']}" if counters["exception"] else "")
        )
