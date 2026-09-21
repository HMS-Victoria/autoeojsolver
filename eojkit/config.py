# -*- coding: utf-8 -*-
"""
eojkit.config —— 统一配置中心
==============================

替代旧版 ``eoj_auto_solver.py`` 顶部散落的全局变量与硬编码凭据。

配置优先级（从高到低）：

1. 显式传入的参数 / 运行时赋值（``settings.llm.model = ...``）
2. 环境变量（含项目根目录 ``.env`` 文件）
3. 持久化配置文件 ``eoj_config.json``（由 GUI 写入，含旧版 ``eoj_gui_config.json`` 迁移）
4. 代码内置默认值（**不含任何密钥**）

支持的模型供应商通过 ``base_url`` 区分，全部走 OpenAI 兼容的
``/chat/completions`` 协议，因此 DeepSeek / 硅基流动 / 月之暗面 / 阿里云百炼 /
Ollama 等都可以直接用，只需换 ``base_url`` + ``model``。

Designed by HMS_Victorious
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = [
    "PROJECT_ROOT",
    "CONFIG_FILENAME",
    "LEGACY_CONFIG_FILENAMES",
    "ENV_FILENAME",
    "SOLUTIONS_DIRNAME",
    "PROVIDER_PRESETS",
    "LLMConfig",
    "EOJConfig",
    "RuntimeConfig",
    "Settings",
    "get_settings",
    "reload_settings",
    "mask_secret",
    "config_path",
]

# --------------------------------------------------------------------------
# 路径常量
# --------------------------------------------------------------------------

from .paths import DATA_DIR

PROJECT_ROOT = str(DATA_DIR)

CONFIG_FILENAME = "eoj_config.json"
LEGACY_CONFIG_FILENAMES = ("eoj_gui_config.json",)
ENV_FILENAME = ".env"

#: 归档目录名（相对项目根）。可用 ``EOJ_SOLUTIONS_DIR`` 覆盖为任意绝对路径。
SOLUTIONS_DIRNAME = "solutions"

# --------------------------------------------------------------------------
# 供应商预设：base_url + 可用模型清单
# --------------------------------------------------------------------------
# 说明：模型 ID 会随官方迭代变化，因此这里只作为「下拉框候选」，
# 真正的可用性以运行时 ``GET {base_url}/models`` 探测结果为准
# （见 eojkit.llm.client.LLMClient.list_models）。

PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-v4-pro", "deepseek-flash"],
        "env_key": "DEEPSEEK_API_KEY",
    },
    "siliconflow": {
        "label": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
        "env_key": "SILICONFLOW_API_KEY",
    },
    "moonshot": {
        "label": "月之暗面 Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-32k", "kimi-k2-0905-preview"],
        "env_key": "MOONSHOT_API_KEY",
    },
    "dashscope": {
        "label": "阿里云百炼 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max"],
        "env_key": "DASHSCOPE_API_KEY",
    },
    "openai": {
        "label": "OpenAI 兼容",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini"],
        "env_key": "OPENAI_API_KEY",
    },
    "ollama": {
        "label": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5-coder:7b"],
        "env_key": "OLLAMA_API_KEY",
    },
    "custom": {
        "label": "自定义 (OpenAI 兼容)",
        "base_url": "",
        "models": [],
        "env_key": "LLM_API_KEY",
    },
}

DEFAULT_BASE_URL = PROVIDER_PRESETS["deepseek"]["base_url"]
DEFAULT_MODEL = PROVIDER_PRESETS["deepseek"]["models"][0]


# --------------------------------------------------------------------------
# .env 解析（零依赖，避免引入 python-dotenv）
# --------------------------------------------------------------------------

def _parse_env_file(path: str) -> Dict[str, str]:
    """解析简单的 KEY=VALUE 格式 .env 文件。"""
    data: Dict[str, str] = {}
    if not os.path.isfile(path):
        return data
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            raw_lines = fh.read().splitlines()
    except OSError:
        return data

    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # 去掉成对引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            data[key] = value
    return data


_ENV_FILE_CACHE: Dict[str, Any] = {"mtime": None, "data": {}}
_ENV_FILE_LOCK = threading.Lock()


def dotenv_values(root: Optional[str] = None, use_cache: bool = True) -> Dict[str, str]:
    """读取项目根目录的 .env（带 mtime 缓存）。"""
    root = root or PROJECT_ROOT
    path = os.path.join(root, ENV_FILENAME)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}

    if use_cache:
        with _ENV_FILE_LOCK:
            if _ENV_FILE_CACHE["mtime"] == mtime:
                return dict(_ENV_FILE_CACHE["data"])

    data = _parse_env_file(path)
    if use_cache:
        with _ENV_FILE_LOCK:
            _ENV_FILE_CACHE["mtime"] = mtime
            _ENV_FILE_CACHE["data"] = data
    return dict(data)


def _env(key: str, default: Any = None) -> Any:
    """按 环境变量 > .env 文件 的顺序取值。"""
    if key in os.environ and os.environ[key] != "":
        return os.environ[key]
    file_values = dotenv_values()
    if key in file_values and file_values[key] != "":
        return file_values[key]
    return default


def _env_bool(key: str, default: bool = False) -> bool:
    value = _env(key, None)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on", "是")


def _env_int(key: str, default: int) -> int:
    value = _env(key, None)
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    value = _env(key, None)
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def mask_secret(value: Optional[str], keep: int = 6) -> str:
    """把密钥打码成 ``sk-abc...`` 形式，用于日志与界面展示。"""
    if not value:
        return "(未设置)"
    value = str(value)
    if len(value) <= keep * 2:
        return value[:2] + "*" * max(len(value) - 2, 0)
    return f"{value[:keep]}...{value[-4:]}"


# --------------------------------------------------------------------------
# 配置文件读写
# --------------------------------------------------------------------------

def config_path(root: Optional[str] = None) -> str:
    return os.path.join(root or PROJECT_ROOT, CONFIG_FILENAME)


def _legacy_config_paths(root: str):
    for name in LEGACY_CONFIG_FILENAMES:
        yield os.path.join(root, name)


def load_config_file(root: Optional[str] = None, migrate_legacy: bool = True) -> Dict[str, Any]:
    """读取 JSON 配置文件；旧版 ``eoj_gui_config.json`` 会自动迁移。"""
    root = root or PROJECT_ROOT
    path = config_path(root)
    data: Dict[str, Any] = {}

    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, ValueError):
            pass
    elif migrate_legacy:
        for legacy in _legacy_config_paths(root):
            if not os.path.isfile(legacy):
                continue
            try:
                with open(legacy, "r", encoding="utf-8-sig") as fh:
                    loaded = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(loaded, dict):
                data.update(loaded)
                # 迁移：保留旧文件副本，写出新格式
                try:
                    shutil.copyfile(legacy, legacy + ".bak")
                    save_config_file(data, root)
                except OSError:
                    pass
            break
    return data


def save_config_file(data: Dict[str, Any], root: Optional[str] = None) -> str:
    """原子写入 JSON 配置文件。"""
    root = root or PROJECT_ROOT
    path = config_path(root)
    os.makedirs(root, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------
# 配置数据类
# --------------------------------------------------------------------------

@dataclass
class LLMConfig:
    """大模型接口配置。"""

    provider: str = "deepseek"
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    fallback_models: list = field(default_factory=list)
    temperature: float = 0.2
    max_tokens: int = 8192
    timeout: int = 180
    max_retries: int = 3
    retry_backoff: float = 2.0
    stream: bool = False
    verify_ssl: bool = True
    extra_headers: Dict[str, str] = field(default_factory=dict)
    #: 推理型模型把思考过程放在 reasoning_content，正文可能为空
    include_reasoning_as_fallback: bool = True

    def __post_init__(self) -> None:
        self.base_url = normalize_base_url(self.base_url)

    # -- 便捷属性 ---------------------------------------------------------
    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def models_url(self) -> str:
        return self.base_url.rstrip("/") + "/models"

    def resolved_candidates(self):
        """返回调用时依次尝试的模型列表（主模型 + 备选）。"""
        seen = []
        for name in [self.model, *self.fallback_models]:
            if name and name not in seen:
                seen.append(name)
        return seen

    def to_dict(self, include_key: bool = True) -> Dict[str, Any]:
        data = {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "fallback_models": list(self.fallback_models),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
        if include_key:
            data["api_key"] = self.api_key
        return data


def normalize_base_url(url: str) -> str:
    """把各种写法统一成 ``.../v1`` 结尾的 OpenAI 兼容根地址。"""
    url = (url or "").strip().rstrip("/")
    if not url:
        return DEFAULT_BASE_URL
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    if not url.endswith("/v1") and "/v1/" not in url:
        # api.deepseek.com -> api.deepseek.com/v1
        url = url + "/v1"
    return url


@dataclass
class EOJConfig:
    """EOJ 站点账号配置。"""

    username: str = ""
    password: str = ""
    base_url: str = "https://acm.ecnu.edu.cn"
    solutions_dir: str = ""
    remember: bool = True

    def __post_init__(self) -> None:
        if not self.solutions_dir:
            self.solutions_dir = os.path.join(PROJECT_ROOT, SOLUTIONS_DIRNAME)


@dataclass
class RuntimeConfig:
    """运行期行为配置。"""

    max_retries: int = 3              # 编译/测试失败后 AI 重写代码的次数
    per_problem_timeout: int = 0      # 单题总时长上限（秒），0=不限
    batch_mode: bool = False
    submit_interval: float = 1.0      # 批量提交间隔（秒）
    judge_wait: int = 30              # 等待判题的最长秒数
    compile_timeout: int = 30
    run_timeout: int = 5
    gpp_path: Optional[str] = None
    proxy: str = ""
    log_level: str = "INFO"


# --------------------------------------------------------------------------
# 汇总 Settings
# --------------------------------------------------------------------------

class Settings:
    """全局配置聚合对象，单例由 :func:`get_settings` 管理。"""

    def __init__(self, root: Optional[str] = None, load_file: bool = True):
        self.root = root or PROJECT_ROOT
        self._lock = threading.RLock()
        self._file_data: Dict[str, Any] = load_config_file(self.root) if load_file else {}
        self.llm = self._build_llm()
        self.eoj = self._build_eoj()
        self.runtime = self._build_runtime()

    # -- 构建各段 ---------------------------------------------------------
    def _file_get(self, *keys, default=None):
        for key in keys:
            if key in self._file_data and self._file_data[key] not in (None, ""):
                return self._file_data[key]
        return default

    def _build_llm(self) -> LLMConfig:
        # API Key：环境变量（多供应商）> 配置文件
        provider = str(
            _env("LLM_PROVIDER", self._file_get("provider", default="deepseek"))
        ).strip() or "deepseek"
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])

        api_key = ""
        for env_name in ("LLM_API_KEY", preset.get("env_key", ""), "DEEPSEEK_API_KEY"):
            if not env_name:
                continue
            value = _env(env_name, None)
            if value:
                api_key = str(value).strip()
                break
        if not api_key:
            api_key = str(self._file_get("api_key", "llm_api_key", default="") or "").strip()

        base_url = _env("LLM_BASE_URL", None) or self._file_get("base_url", default=None)
        if not base_url:
            base_url = preset.get("base_url") or DEFAULT_BASE_URL

        model = _env("LLM_MODEL", None) or self._file_get("model", default=None)
        if not model:
            model = (preset.get("models") or [DEFAULT_MODEL])[0]

        fallback = self._file_get("fallback_models", default=[]) or []
        env_fallback = _env("LLM_FALLBACK_MODELS", None)
        if env_fallback:
            fallback = [m.strip() for m in str(env_fallback).split(",") if m.strip()]
        if isinstance(fallback, str):
            fallback = [m.strip() for m in fallback.split(",") if m.strip()]

        return LLMConfig(
            provider=provider,
            base_url=str(base_url),
            api_key=api_key,
            model=str(model),
            fallback_models=list(fallback),
            temperature=_env_float("LLM_TEMPERATURE", float(self._file_get("temperature", default=0.2) or 0.2)),
            max_tokens=_env_int("LLM_MAX_TOKENS", int(self._file_get("max_tokens", default=8192) or 8192)),
            timeout=_env_int("LLM_TIMEOUT", int(self._file_get("llm_timeout", default=180) or 180)),
            max_retries=_env_int("LLM_MAX_RETRIES", int(self._file_get("max_retries_llm", default=3) or 3)),
            stream=_env_bool("LLM_STREAM", bool(self._file_get("stream", default=False))),
            verify_ssl=not _env_bool("LLM_INSECURE", False),
        )

    def _build_eoj(self) -> EOJConfig:
        username = _env("EOJ_USERNAME", self._file_get("username", default="")) or ""
        password = _env("EOJ_PASSWORD", self._file_get("password", default="")) or ""
        base_url = _env("EOJ_BASE_URL", self._file_get("eoj_base_url", default="https://acm.ecnu.edu.cn"))
        solutions_dir = _env(
            "EOJ_SOLUTIONS_DIR",
            self._file_get("solutions_dir", default=os.path.join(self.root, SOLUTIONS_DIRNAME)),
        )
        return EOJConfig(
            username=str(username).strip(),
            password=str(password),
            base_url=str(base_url).rstrip("/"),
            solutions_dir=str(solutions_dir),
            remember=bool(self._file_get("remember", default=True)),
        )

    def _build_runtime(self) -> RuntimeConfig:
        proxy = _env("EOJ_PROXY", self._file_get("proxy", default="")) or ""
        return RuntimeConfig(
            max_retries=_env_int("EOJ_MAX_RETRIES", int(self._file_get("retries", default=3) or 3)),
            per_problem_timeout=_env_int("EOJ_PER_PROBLEM_TIMEOUT", int(self._file_get("timeout", default=0) or 0)),
            batch_mode=_env_bool("EOJ_BATCH_MODE", False),
            submit_interval=_env_float("EOJ_SUBMIT_INTERVAL", float(self._file_get("submit_interval", default=1.0) or 1.0)),
            judge_wait=_env_int("EOJ_JUDGE_WAIT", int(self._file_get("judge_wait", default=30) or 30)),
            gpp_path=_env("EOJ_GPP", self._file_get("gpp_path", default=None)),
            proxy=str(proxy),
        )

    # -- 持久化 -----------------------------------------------------------
    def to_file_dict(self) -> Dict[str, Any]:
        """生成写回 JSON 的内容（保持旧版 GUI 字段名兼容）。"""
        with self._lock:
            data = dict(self._file_data)
            data.update(
                {
                    "username": self.eoj.username,
                    "password": self.eoj.password,
                    "api_key": self.llm.api_key,
                    "model": self.llm.model,
                    "base_url": self.llm.base_url,
                    "provider": self.llm.provider,
                    "solutions_dir": self.eoj.solutions_dir,
                    "remember": self.eoj.remember,
                    "timeout": self.runtime.per_problem_timeout,
                }
            )
            if not self.eoj.remember:
                data.pop("password", None)
            return data

    def save(self) -> str:
        return save_config_file(self.to_file_dict(), self.root)

    # -- 运行时改写 -------------------------------------------------------
    def apply_credentials(self, username=None, password=None, api_key=None, model=None, base_url=None) -> None:
        """GUI/CLI 在任务开始前调用，把界面上的值写回配置对象。"""
        with self._lock:
            if username is not None:
                self.eoj.username = username.strip()
            if password is not None:
                self.eoj.password = password
            if api_key is not None:
                self.llm.api_key = api_key.strip()
            if model:
                self.llm.model = model.strip()
            if base_url:
                self.llm.base_url = normalize_base_url(base_url)

    def reload(self) -> "Settings":
        with self._lock:
            self._file_data = load_config_file(self.root)
            self.llm = self._build_llm()
            self.eoj = self._build_eoj()
            self.runtime = self._build_runtime()
        return self

    def describe(self, reveal: bool = False) -> str:
        key = self.llm.api_key if reveal else mask_secret(self.llm.api_key)
        lines = [
            "当前配置",
            f"  供应商    : {self.llm.provider}",
            f"  接口地址  : {self.llm.base_url}",
            f"  模型      : {self.llm.model}",
            f"  API Key   : {key}",
            f"  EOJ 账号  : {self.eoj.username or '(未设置)'}",
            f"  存档目录  : {self.eoj.solutions_dir}",
        ]
        return "\n".join(lines)


_SETTINGS: Optional[Settings] = None
_SETTINGS_LOCK = threading.Lock()


def get_settings() -> Settings:
    """获取全局 Settings 单例。"""
    global _SETTINGS
    if _SETTINGS is None:
        with _SETTINGS_LOCK:
            if _SETTINGS is None:
                _SETTINGS = Settings()
    return _SETTINGS


def reload_settings() -> Settings:
    """重新读取配置文件与环境变量。"""
    global _SETTINGS
    with _SETTINGS_LOCK:
        if _SETTINGS is None:
            _SETTINGS = Settings()
        else:
            _SETTINGS.reload()
        return _SETTINGS
