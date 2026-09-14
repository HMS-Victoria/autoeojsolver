# -*- coding: utf-8 -*-
"""大模型接入层：OpenAI 兼容客户端 + 提示词 + 解题器。"""

from .client import (
    LLMClient,
    LLMError,
    LLMAuthError,
    LLMResponseError,
    LLMRateLimitError,
    LLMResponse,
    build_chat_payload,
    extract_code,
    extract_markdown,
)
from .solver import AISolver, DeepSeekSolver, SolverError
from . import prompts

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMAuthError",
    "LLMResponseError",
    "LLMRateLimitError",
    "LLMResponse",
    "build_chat_payload",
    "extract_code",
    "extract_markdown",
    "AISolver",
    "DeepSeekSolver",
    "SolverError",
    "prompts",
]
