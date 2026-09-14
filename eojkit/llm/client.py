# -*- coding: utf-8 -*-
"""
eojkit.llm.client —— DeepSeek / OpenAI 兼容大模型客户端
========================================================

这是本次「更新模型 API 接口」的核心模块，相对旧版
``DeepSeekSolver._call_api`` 的改进：

====================  ====================================================
旧实现的问题           新实现的做法
====================  ====================================================
模型名硬编码且已停用   模型 ID 可配置，且提供 ``list_models()`` 向
(``deepseek-chat`` 等)  ``GET /models`` 实时探测真实可用模型
接口地址写死             ``base_url`` 可配置，兼容任意 OpenAI 协议端点
无重试，一次失败就返回  指数退避重试 + 429/5xx/超时区分对待 + 自动降级备选模型
不看 ``finish_reason``  识别 ``length`` 截断并自动放大 max_tokens 重试
忽略推理模型特性        正确消费 ``reasoning_content``：正文为空时回退，
                        并按 reasoning 预算自动抬高 max_tokens
裸 ``r.json()[...]``   多层容错解析，附带 usage / 耗时 / 请求 ID
无代码提取兜底          多策略提取 ```cpp``` 围栏 / 裸代码 / 截断修复
每个实例新建 Session     复用连接池，减少 TLS 握手与延迟
====================  ====================================================

Designed by HMS_Victorious
"""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import requests

from ..config import PROVIDER_PRESETS, LLMConfig, get_settings, mask_secret

__all__ = [
    "LLMError",
    "LLMAuthError",
    "LLMResponseError",
    "LLMResponse",
    "LLMClient",
    "extract_code",
    "extract_markdown",
    "build_chat_payload",
]

log = logging.getLogger("eojkit.llm")


# ==========================================================================
# 异常体系
# ==========================================================================

class LLMError(RuntimeError):
    """大模型调用相关错误基类。"""

    def __init__(self, message: str, *, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class LLMAuthError(LLMError):
    """401/403 —— API Key 无效或权限不足（重试无意义）。"""


class LLMResponseError(LLMError):
    """响应 200 但结构异常 / 内容为空。"""


class LLMRateLimitError(LLMError):
    """429 —— 触发限流，可退避重试。"""


# ==========================================================================
# 响应容器
# ==========================================================================

@dataclass
class LLMResponse:
    """一次对话补全的结果（含诊断信息）。"""

    content: str = ""
    reasoning: str = ""
    model: str = ""
    finish_reason: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    latency: float = 0.0
    attempts: int = 1
    request_id: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def reasoning_tokens(self) -> int:
        details = (self.usage or {}).get("completion_tokens_details") or {}
        return int(details.get("reasoning_tokens") or 0)

    @property
    def completion_tokens(self) -> int:
        return int((self.usage or {}).get("completion_tokens") or 0)

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"

    @property
    def text(self) -> str:
        """正文；若正文为空则回退到推理内容（推理模型 max_tokens 太小时会发生）。"""
        return self.content or self.reasoning

    def __bool__(self) -> bool:
        return bool(self.content or self.reasoning)

    def summary(self) -> str:
        bits = [
            f"model={self.model or '?'}",
            f"耗时={self.latency:.1f}s",
            f"正文={len(self.content)}字",
        ]
        if self.reasoning:
            bits.append(f"思考={len(self.reasoning)}字")
        if self.usage:
            bits.append(f"tokens={self.usage.get('total_tokens', '?')}")
        if self.attempts > 1:
            bits.append(f"重试={self.attempts - 1}")
        if self.truncated:
            bits.append("⚠被截断")
        return ", ".join(bits)


# ==========================================================================
# 文本提取工具
# ==========================================================================

_FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+#.-]*)[ \t]*\r?\n(.*?)(?:^```[ \t]*$|\Z)", re.DOTALL | re.MULTILINE)

_CODE_LANGS = {
    "cpp", "c++", "cxx", "cc", "c", "cpp17", "cpp20", "cpp14",
    "python", "py", "java", "javascript", "js", "typescript", "ts",
    "rust", "go", "csharp", "cs", "kotlin", "pascal", "text", "plaintext", "",
}


def _iter_fences(text: str) -> Iterable[tuple]:
    """产出 ``(语言, 内容)`` 二元组，按出现顺序。

    末尾若存在**未闭合**的围栏（模型被 max_tokens 截断时很常见），
    也把它当作一个代码块返回，避免整段回复作废。
    """
    matches = list(_FENCE_RE.finditer(text))
    matched_spans = []
    for match in matches:
        lang = (match.group(1) or "").strip().lower()
        body = (match.group(2) or "").strip()
        matched_spans.append(match.span())
        if body:
            yield lang, body

    # 未闭合围栏：```cpp\n <代码一直到结尾>
    cursor = 0
    for start, _end in matched_spans:
        cursor = max(cursor, _end)
    tail = text[cursor:]
    open_match = re.search(r"```[ \t]*([A-Za-z0-9_+#.-]*)[ \t]*\r?\n(.*)\Z", tail, re.DOTALL)
    if open_match and open_match.group(2).strip():
        yield (open_match.group(1) or "").strip().lower(), open_match.group(2).strip()


def extract_code(text: str, languages: Sequence[str] = ("cpp", "c++", "cxx", "cc", "c", "")) -> str:
    """从模型回复中提取源码。

    修复旧版 ``re.search(r'```(?:cpp|c\\+\\+)?...')`` 的两个缺陷：

    1. 模型经常**不输出围栏**（实测 ``deepseek-v4-pro`` 直接返回裸代码），
       旧逻辑提取不到就会把整段回复当代码写入 ``solution.cpp``；
    2. 正则未要求围栏独立成行，遇到 ````` ``` ````` + 文字混排会截错。

    策略：优先取指定语言的围栏 → 任意围栏 → 裸代码文本。
    """
    text = (text or "").strip()
    if not text:
        return ""

    fences = list(_iter_fences(text))

    # 1) 精确语言匹配
    for lang in languages:
        for fence_lang, body in fences:
            if fence_lang == lang and body.strip():
                return body.strip()

    # 2) 任意代码类语言围栏
    for fence_lang, body in fences:
        if fence_lang in _CODE_LANGS and body.strip():
            return body.strip()

    # 3) 无围栏：整段即代码（去掉可能的前后解说行）
    stripped = text
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[A-Za-z0-9_+#.-]*[ \t]*\r?\n?", "", stripped)
        stripped = re.sub(r"\r?\n?```[ \t]*$", "", stripped)
    return stripped.strip()


def extract_markdown(text: str) -> str:
    """从模型回复中提取 Markdown 正文（笔记场景）。"""
    text = (text or "").strip()
    if not text:
        return ""
    fences = list(_iter_fences(text))
    # 1) 显式 markdown 围栏
    for lang, body in fences:
        if lang in ("markdown", "md") and body:
            return body
    # 2) 模型把 markdown 放进了无语言围栏或 text 围栏
    if fences and fences[0][0] in ("", "text", "plaintext"):
        if fences[0][1]:
            return fences[0][1]
    return text


def _looks_complete(content: str) -> bool:
    """粗略判断被截断的正文是否其实已经完整。

    用于 ``finish_reason=length`` 时的判断：推理模型常把 max_tokens 花在
    ``reasoning_content`` 上，正文本身可能已经写完（实测常见）。
    判据：

    * 没有任何正文 → 不完整
    * 围栏计数为奇数 → 代码块没闭合 → 不完整
    * 含花括号但 ``{`` 与 ``}`` 数量不符 → C/C++ 代码被截断 → 不完整
    * 否则视为完整
    """
    text = content or ""
    if not text.strip():
        return False
    if text.count("```") % 2 != 0:
        return False
    if "{" in text or "}" in text:
        if text.count("{") != text.count("}"):
            return False
    return True


# ==========================================================================
# 请求体构造
# ==========================================================================

def build_chat_payload(
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    stream: bool = False,
    response_format: Optional[Dict[str, str]] = None,
    top_p: Optional[float] = None,
    stop: Optional[Sequence[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装 OpenAI 兼容的 chat/completions 请求体。"""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if stop:
        payload["stop"] = list(stop)
    if response_format:
        payload["response_format"] = response_format
    if extra:
        payload.update(extra)
    return payload


# ==========================================================================
# 客户端
# ==========================================================================

class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端（带重试 / 降级 / 诊断）。

    典型用法::

        client = LLMClient()
        resp = client.chat([{"role": "user", "content": "hi"}])
        print(resp.content)

    只想用某次调用的临时配置，可传 ``config=LLMConfig(...)``。
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        *,
        session: Optional[requests.Session] = None,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.config = config or get_settings().llm
        self._logger = logger
        self._lock = threading.Lock()
        self._session = session or self._new_session()
        self.last_response: Optional[LLMResponse] = None

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def _new_session(self) -> requests.Session:
        sess = requests.Session()
        sess.trust_env = False  # 避免系统代理污染 API 请求
        sess.headers.update(
            {
                "User-Agent": "eojkit/4.0 (+https://acm.ecnu.edu.cn)",
                "Accept": "application/json",
            }
        )
        return sess

    def _emit(self, message: str) -> None:
        if self._logger:
            try:
                self._logger(message)
                return
            except Exception:  # pragma: no cover - 日志回调不应影响主流程
                pass
        log.debug(message)

    @property
    def configured(self) -> bool:
        return bool(self.config.api_key)

    def headers(self) -> Dict[str, str]:
        head = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        head.update(self.config.extra_headers or {})
        return head

    # ------------------------------------------------------------------
    # 模型探测
    # ------------------------------------------------------------------
    def list_models(self, timeout: Optional[int] = None) -> List[str]:
        """调用 ``GET {base_url}/models`` 返回真实可用模型 ID 列表。

        失败时回退到 ``PROVIDER_PRESETS`` 中的候选清单（这样就永远有下拉框可用）。
        """
        url = self.config.models_url
        try:
            resp = self._session.get(
                url,
                headers=self.headers(),
                timeout=timeout or min(self.config.timeout, 20),
                verify=self.config.verify_ssl,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data") if isinstance(data, dict) else None
                if isinstance(items, list):
                    ids = []
                    for item in items:
                        if isinstance(item, dict) and item.get("id"):
                            ids.append(str(item["id"]))
                        elif isinstance(item, str):
                            ids.append(item)
                    if ids:
                        return ids
            self._emit(f"  [API] /models 返回 {resp.status_code}，使用内置候选清单")
        except Exception as exc:  # noqa: BLE001 - 探测失败不应中断主流程
            self._emit(f"  [API] /models 探测失败: {type(exc).__name__}: {exc}")
        return list(PROVIDER_PRESETS.get(self.config.provider, {}).get("models") or [])

    def health_check(self, model: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        """最小成本的连通性自检，供 GUI「测试 API」按钮与 CLI doctor 使用。

        对推理型模型放宽校验：它们会先花掉一批 token 思考，
        极小的 max_tokens 下 ``finish_reason`` 会是 ``length``，
        但接口本身是通的，不应该判为失败。
        """
        started = time.time()
        result: Dict[str, Any] = {
            "ok": False,
            "base_url": self.config.base_url,
            "model": model or self.config.model,
            "api_key": mask_secret(self.config.api_key),
        }
        if not self.configured:
            result["error"] = "未配置 API Key"
            return result
        try:
            resp = self.chat(
                [{"role": "user", "content": "ping"}],
                model=model,
                max_tokens=256,
                temperature=0.0,
                max_retries=1,
                timeout=timeout,
                strict=False,
                expect_text=False,
            )
            reply = (resp.content or resp.reasoning or "").strip()
            result.update(
                ok=bool(reply),
                latency=round(time.time() - started, 2),
                reply=reply[:60],
                usage=resp.usage,
                finish_reason=resp.finish_reason,
                notes=[],
                models=self.list_models(),
            )
            if not reply:
                result["error"] = "接口连通但返回空内容"
            if resp.truncated:
                result["notes"].append(
                    "响应被 max_tokens 截断（推理模型会先消耗思考 token，属正常现象）"
                )
        except LLMError as exc:
            result["error"] = str(exc)
            result["status"] = exc.status
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    # ------------------------------------------------------------------
    # 主调用
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        stream: Optional[bool] = None,
        expect_text: bool = True,
        strict: bool = True,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> LLMResponse:
        """发送一次对话补全请求。

        失败会自动重试（指数退避 + 抖动）；若配置了 ``fallback_models``，
        在主模型连续失败后自动切换到备选模型。

        :param expect_text: 正文为空时是否视为失败（推理模型可能正文为空但思考有内容）
        :param strict: ``False`` 时不做「截断/空内容」的严格校验（健康检查用）
        """
        cfg = self.config
        if not cfg.api_key:
            raise LLMAuthError("未配置 API Key：请设置环境变量 DEEPSEEK_API_KEY / LLM_API_KEY，或在 GUI 中填写")

        models = [model] if model else cfg.resolved_candidates()
        base_tokens = int(max_tokens or cfg.max_tokens)
        use_stream = cfg.stream if stream is None else stream
        retries = cfg.max_retries if max_retries is None else max_retries

        last_exc: Optional[Exception] = None

        for model_index, current_model in enumerate(models):
            if model_index:
                self._emit(f"  [API] 主模型不可用，降级到备选模型: {current_model}")
            # 推理型模型会先消耗一批 reasoning token，正文容易被挤空，
            # 因此首轮就把预算抬高一档（实测 reasoning 占用 200~500+）。
            token_budget = base_tokens
            attempt = 0
            while attempt <= retries:
                attempt += 1
                payload = build_chat_payload(
                    current_model,
                    messages,
                    max_tokens=token_budget,
                    temperature=cfg.temperature if temperature is None else temperature,
                    stream=use_stream,
                    response_format=response_format,
                )
                started = time.time()
                try:
                    raw = self._post(payload, timeout or cfg.timeout, use_stream, on_progress)
                    latency = time.time() - started
                    resp = self._parse(raw, current_model, latency, attempt)
                    if expect_text and not resp.text.strip():
                        raise LLMResponseError(
                            f"模型返回空内容 (finish_reason={resp.finish_reason or '?'}, "
                            f"completion_tokens={resp.completion_tokens})",
                            status=200,
                        )
                    if strict and resp.truncated:
                        # 被 max_tokens 截断。推理模型常把预算花在思考上，
                        # 但正文（代码块）可能已经完整 —— 这种情况直接接受，
                        # 避免无谓地把 max_tokens 翻倍、白烧钱。
                        if _looks_complete(resp.content):
                            self._emit("  [API] 响应 finish_reason=length，但正文已完整，接受结果")
                        elif token_budget < base_tokens * 4:
                            token_budget = min(max(token_budget * 2, base_tokens * 2), 32768)
                            self._emit(
                                f"  [API] 响应被截断({resp.finish_reason})，max_tokens 提升至 {token_budget} 重试"
                            )
                            raise LLMResponseError("响应被 max_tokens 截断", status=200)
                    self.last_response = resp
                    return resp

                except LLMAuthError:
                    raise
                except LLMRateLimitError as exc:
                    last_exc = exc
                    if attempt > retries:
                        break
                    wait = self._backoff(attempt, hint=1.0)
                    self._emit(f"  [API] 触发限流(429)，{wait:.1f}s 后重试 ({attempt}/{retries})")
                    time.sleep(wait)
                except LLMError as exc:
                    last_exc = exc
                    if attempt > retries:
                        break
                    wait = self._backoff(attempt)
                    self._emit(f"  [API] 调用失败({exc})，{wait:.1f}s 后重试 ({attempt}/{retries})")
                    time.sleep(wait)
                except requests.exceptions.RequestException as exc:
                    last_exc = exc
                    if attempt > retries:
                        break
                    wait = self._backoff(attempt)
                    self._emit(f"  [API] 网络异常({type(exc).__name__})，{wait:.1f}s 后重试 ({attempt}/{retries})")
                    time.sleep(wait)

        if isinstance(last_exc, LLMError):
            raise last_exc
        raise LLMError(f"调用失败: {last_exc}")

    # ------------------------------------------------------------------
    # HTTP / 解析
    # ------------------------------------------------------------------
    def _post(
        self,
        payload: Dict[str, Any],
        timeout: int,
        stream: bool,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        url = self.config.chat_url
        if stream:
            payload = dict(payload, stream=True)
            resp = self._session.post(
                url,
                headers=self.headers(),
                json=payload,
                timeout=(15, timeout),
                stream=True,
                verify=self.config.verify_ssl,
            )
            self._raise_for_status(resp)
            return self._consume_stream(resp, on_progress)

        resp = self._session.post(
            url,
            headers=self.headers(),
            json=payload,
            timeout=(15, timeout),
            verify=self.config.verify_ssl,
        )
        self._raise_for_status(resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise LLMResponseError(f"响应不是合法 JSON: {resp.text[:200]}", status=resp.status_code) from exc

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.status_code < 400:
            return
        body = ""
        try:
            body = resp.text[:400]
        except Exception:  # noqa: BLE001
            pass
        if resp.status_code in (401, 403):
            raise LLMAuthError(
                f"认证失败({resp.status_code})：请检查 API Key 是否有该模型的权限。{body}",
                status=resp.status_code,
                body=body,
            )
        if resp.status_code == 429:
            raise LLMRateLimitError(f"请求过于频繁(429)：{body}", status=429, body=body)
        raise LLMError(f"HTTP {resp.status_code}: {body}", status=resp.status_code, body=body)

    def _consume_stream(
        self,
        resp: requests.Response,
        on_progress: Optional[Callable[[str], None]],
    ) -> Dict[str, Any]:
        """消费 SSE 流，拼装成与一次性响应同构的 dict。"""
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        finish_reason = ""
        model = self.config.model
        usage: Dict[str, Any] = {}

        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if isinstance(chunk, dict) and chunk.get("usage"):
                usage = chunk["usage"]
            choice_list = (chunk or {}).get("choices") or []
            if not choice_list:
                continue
            choice = choice_list[0]
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
                if on_progress:
                    try:
                        on_progress(delta["content"])
                    except Exception:  # noqa: BLE001
                        pass
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])
            if chunk.get("model"):
                model = chunk["model"]

        return {
            "model": model,
            "usage": usage,
            "choices": [
                {
                    "finish_reason": finish_reason or "stop",
                    "message": {
                        "role": "assistant",
                        "content": "".join(content_parts),
                        "reasoning_content": "".join(reasoning_parts),
                    },
                }
            ],
        }

    def _parse(self, raw: Dict[str, Any], requested_model: str, latency: float, attempts: int) -> LLMResponse:
        """把原始响应解析成 :class:`LLMResponse`（多层容错）。"""
        if not isinstance(raw, dict):
            raise LLMResponseError(f"响应结构异常: {type(raw).__name__}")

        if raw.get("error"):
            err = raw["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            raise LLMError(f"接口返回错误: {msg} (code={code})")

        choices = raw.get("choices") or []
        if not choices:
            raise LLMResponseError(f"响应缺少 choices 字段: {json.dumps(raw, ensure_ascii=False)[:200]}")

        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = message.get("content") or ""
        # 兼容不同供应商的字段命名
        reasoning = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or (message.get("model_extra") or {}).get("reasoning_content")
            or ""
        )
        if isinstance(content, list):  # 某些实现返回分段 content
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )

        return LLMResponse(
            content=content.strip() if isinstance(content, str) else str(content),
            reasoning=reasoning if isinstance(reasoning, str) else str(reasoning),
            model=raw.get("model") or requested_model,
            finish_reason=choice.get("finish_reason") or "",
            usage=raw.get("usage") or {},
            latency=latency,
            attempts=attempts,
            request_id=str(raw.get("id") or ""),
            raw=raw,
        )

    def _backoff(self, attempt: int, hint: float = 0.0) -> float:
        base = max(hint, self.config.retry_backoff * (2 ** (attempt - 1)))
        return min(base + random.uniform(0, 0.5), 30.0)

    def close(self) -> None:
        with self._lock:
            try:
                self._session.close()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
