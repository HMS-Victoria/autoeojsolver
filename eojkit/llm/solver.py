# -*- coding: utf-8 -*-
"""
eojkit.llm.solver —— AI 解题 / 笔记生成器（原 DeepSeekSolver 的重构版）
=======================================================================

对外保持旧接口：``generate_code`` / ``generate_analysis`` / ``regenerate_code``，
因此 GUI 与 CLI 无需改动即可继续使用；内部改为委托 :class:`eojkit.llm.client.LLMClient`。

相比旧版的实质修复
------------------
* **模型 ID 更新**：旧版默认 ``deepseek-v4-pro`` 尚可用，但下拉框里的
  ``deepseek-v4-flash`` 是遗留别名、``deepseek-chat`` 已进入停用流程；
  现在统一从 ``GET /models`` 探测真实可用模型。
* **空响应不再直接判死**：旧版 ``_call_api`` 只取 ``message.content``，
  而 v4 系列是推理模型，``content`` 可能因为 max_tokens 被 reasoning 吃光而为空，
  旧代码会返回 ``None`` 导致整题失败。现在会自动抬高 max_tokens 重试。
* **裸代码兜底**：实测 ``deepseek-v4-pro`` 经常不输出 ```cpp 围栏，
  旧正则提取不到就把思维链当代码写盘、编译必挂。现在走 ``extract_code`` 多策略提取。
* **失败可重试**：网络抖动 / 429 / 5xx 采用指数退避重试，并支持备选模型降级。

Designed by HMS_Victorious
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from ..config import LLMConfig, get_settings
from .client import LLMClient, LLMError, LLMResponse, extract_code, extract_markdown
from . import prompts

__all__ = ["DeepSeekSolver", "AISolver", "SolverError"]

log = logging.getLogger("eojkit.llm.solver")


class SolverError(RuntimeError):
    """AI 解题失败。"""


class DeepSeekSolver:
    """调用大模型生成解题代码与中文刷题笔记。

    :param config: 可选的 :class:`LLMConfig`；默认取全局 Settings。
    :param logger: 日志回调（GUI 用它把输出写进日志框）；默认走 ``print``。
    """

    #: 保留旧类属性，兼容外部引用 ``DeepSeekSolver.API_URL``
    API_URL = "https://api.deepseek.com/v1/chat/completions"

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        client: Optional[LLMClient] = None,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.settings = get_settings()
        #: 显式传入的配置不再被全局 Settings 覆盖
        self._explicit_config = config is not None
        self.config = config if config is not None else self.settings.llm
        self._logger = logger
        self._client = client or LLMClient(self.config, logger=logger)
        self.last_response: Optional[LLMResponse] = None
        #: 记录最近一次调用的诊断信息，便于归档与排障
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _emit(self, message: str) -> None:
        if self._logger:
            try:
                self._logger(message)
                return
            except Exception:  # noqa: BLE001
                pass
        print(message)

    def _sync_config(self) -> None:
        """把全局 Settings 的最新值同步进来。

        这样 GUI 里 ``engine.DEEPSEEK_API_KEY = ...`` 之类的运行时赋值
        依然生效（兼容层在 ``eoj_auto_solver`` 中把全局变量写回 Settings）。
        """
        if self._explicit_config:
            return
        live = self.settings.llm
        self.config.api_key = live.api_key
        self.config.base_url = live.base_url
        self.config.model = live.model
        self.config.timeout = live.timeout
        self.config.max_retries = live.max_retries

    def _ask(
        self,
        messages,
        *,
        max_tokens: int,
        temperature: float,
        timeout: Optional[int] = None,
        label: str = "AI",
    ) -> Optional[str]:
        """统一的模型调用入口，返回纯文本（失败返回 None 并打印原因）。"""
        self._sync_config()
        cfg = self.config
        self._emit(
            f"  [API] {label} · 模型 {cfg.model} · 接入点 {cfg.base_url} "
            f"(temperature={temperature}, max_tokens={max_tokens})"
        )
        try:
            resp = self._client.chat(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout or cfg.timeout,
            )
        except LLMError as exc:
            self.last_error = str(exc)
            self._emit(f"  [FAIL] {label} 调用失败: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._emit(f"  [FAIL] {label} 异常: {self.last_error}")
            return None

        self.last_response = resp
        self.last_error = ""
        self._emit(f"  [API] {label} 响应完成（{resp.summary()}）")
        return resp.text

    # ------------------------------------------------------------------
    # 旧接口兼容：_call_api
    # ------------------------------------------------------------------
    def _call_api(self, messages, max_tokens=4096, temperature=0.2, timeout=120):
        """保留旧签名，内部委托新客户端；失败返回 None。"""
        return self._ask(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            label="API",
        )

    # ------------------------------------------------------------------
    # 业务接口
    # ------------------------------------------------------------------
    def generate_code(self, problem_info: Dict) -> Optional[str]:
        """根据题目信息生成 C++ 代码（失败返回 None）。"""
        self._emit("\n  [AI] 调用大模型生成解题代码...")
        content = self._ask(
            [
                {"role": "system", "content": prompts.SYSTEM_CODER},
                {"role": "user", "content": prompts.build_code_prompt(problem_info)},
            ],
            max_tokens=max(self.config.max_tokens, 4096),
            temperature=0.2,
            label="生成代码",
        )
        if not content:
            return None
        code = extract_code(content)
        if not code:
            self._emit("  [FAIL] 未能从模型回复中提取到代码")
            return None
        self._emit(f"  [OK] 代码生成成功 ({len(code)} 字符)")
        return code

    def regenerate_code(self, problem_info: Dict, previous_code: str, error_info: str) -> Optional[str]:
        """根据编译/测试错误信息让 AI 重写代码。"""
        self._emit("\n  [AI] 调用大模型修正代码...")
        content = self._ask(
            [
                {"role": "system", "content": prompts.SYSTEM_CODER},
                {"role": "user", "content": prompts.build_fix_prompt(problem_info, previous_code, error_info)},
            ],
            max_tokens=max(self.config.max_tokens, 4096),
            temperature=0.3,
            label="修正代码",
        )
        if not content:
            return None
        code = extract_code(content)
        if not code:
            return None
        self._emit(f"  [OK] 修正代码生成成功 ({len(code)} 字符)")
        return code

    def generate_analysis(self, problem_info: Dict, code: Optional[str] = None) -> Optional[str]:
        """生成中文刷题笔记（README.md 内容）。"""
        self._emit("\n  [AI] 调用大模型生成中文刷题笔记...")
        content = self._ask(
            [
                {"role": "system", "content": prompts.SYSTEM_NOTE},
                {"role": "user", "content": prompts.build_note_prompt(problem_info, code)},
            ],
            max_tokens=max(self.config.max_tokens, 4096),
            temperature=0.3,
            label="生成笔记",
        )
        if not content:
            return None
        note = extract_markdown(content)
        if not note:
            return None
        self._emit(f"  [OK] 刷题笔记生成成功 ({len(note)} 字符)")
        return note

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------
    def health_check(self, model: Optional[str] = None) -> Dict:
        self._sync_config()
        return self._client.health_check(model=model)

    def list_models(self):
        self._sync_config()
        return self._client.list_models()

    def close(self) -> None:
        self._client.close()


#: 语义化别名 —— 现在支持任意 OpenAI 兼容供应商，不再限于 DeepSeek
AISolver = DeepSeekSolver
