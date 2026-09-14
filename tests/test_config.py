# -*- coding: utf-8 -*-
"""配置中心与工具函数测试（离线）。"""

from __future__ import annotations

import json
import os
import sys

import pytest

from eojkit import config as cfg
from eojkit.config import (
    EOJConfig,
    LLMConfig,
    Settings,
    mask_secret,
    normalize_base_url,
    PROVIDER_PRESETS,
    SOLUTIONS_DIRNAME,
)
from eojkit.tools import extract_problem_ids_from_range


# ==========================================================================
# normalize_base_url
# ==========================================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1/", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1/chat/completions", "https://api.deepseek.com/v1"),
        ("http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/v1"),
        ("", cfg.DEFAULT_BASE_URL),
    ],
)
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


def test_llm_config_urls():
    conf = LLMConfig(base_url="https://api.deepseek.com", model="deepseek-v4-pro")
    assert conf.chat_url == "https://api.deepseek.com/v1/chat/completions"
    assert conf.models_url == "https://api.deepseek.com/v1/models"


def test_llm_config_candidates_dedupe():
    conf = LLMConfig(model="a", fallback_models=["a", "b", ""])
    assert conf.resolved_candidates() == ["a", "b"]


# ==========================================================================
# mask_secret
# ==========================================================================

def test_mask_secret():
    assert mask_secret("") == "(未设置)"
    assert mask_secret(None) == "(未设置)"
    assert mask_secret("sk-1234567890abcdef") == "sk-123...cdef"
    assert "*" in mask_secret("short")


# ==========================================================================
# 供应商预设
# ==========================================================================

def test_official_deepseek_models_present():
    """官方 /models 实测只认这两个 ID，预设里必须包含。"""
    models = PROVIDER_PRESETS["deepseek"]["models"]
    assert "deepseek-v4-pro" in models
    assert "deepseek-flash" in models


def test_presets_have_required_keys():
    for name, preset in PROVIDER_PRESETS.items():
        assert "label" in preset, name
        assert "base_url" in preset, name
        assert isinstance(preset["models"], list), name


# ==========================================================================
# Settings 分层优先级
# ==========================================================================

def _clean_env(monkeypatch):
    for key in ("EOJ_USERNAME", "EOJ_PASSWORD", "DEEPSEEK_API_KEY", "LLM_API_KEY",
                "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER", "EOJ_SOLUTIONS_DIR"):
        monkeypatch.delenv(key, raising=False)
    # 同时屏蔽项目 .env，避免本机文件干扰断言
    monkeypatch.setattr(cfg, "dotenv_values", lambda root=None, use_cache=True: {})


def test_defaults_have_no_secrets(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    settings = Settings(root=str(tmp_path), load_file=False)
    assert settings.llm.api_key == ""
    assert settings.eoj.username == ""
    assert settings.eoj.password == ""
    assert settings.llm.model == "deepseek-v4-pro"
    assert settings.llm.base_url == "https://api.deepseek.com/v1"


def test_env_overrides_file(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    (tmp_path / cfg.CONFIG_FILENAME).write_text(
        json.dumps({"api_key": "file-key", "model": "file-model", "username": "file-user"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    settings = Settings(root=str(tmp_path))
    assert settings.llm.api_key == "env-key"
    assert settings.llm.model == "env-model"
    assert settings.eoj.username == "file-user", "文件值应作为环境变量缺失时的回退"


def test_file_values_used_when_no_env(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    (tmp_path / cfg.CONFIG_FILENAME).write_text(
        json.dumps({"api_key": "file-key", "model": "deepseek-flash", "base_url": "https://x.example/v1"}),
        encoding="utf-8",
    )
    settings = Settings(root=str(tmp_path))
    assert settings.llm.api_key == "file-key"
    assert settings.llm.model == "deepseek-flash"
    assert settings.llm.base_url == "https://x.example/v1"


def test_legacy_gui_config_migration(tmp_path, monkeypatch):
    """旧 eoj_gui_config.json 应被自动迁移到 eoj_config.json。"""
    _clean_env(monkeypatch)
    legacy = tmp_path / "eoj_gui_config.json"
    legacy.write_text(json.dumps({"api_key": "old-key", "model": "deepseek-v4-flash"}), encoding="utf-8")
    settings = Settings(root=str(tmp_path))
    assert settings.llm.api_key == "old-key"
    assert settings.llm.model == "deepseek-v4-flash"
    assert (tmp_path / cfg.CONFIG_FILENAME).is_file(), "应生成新配置文件"
    assert (tmp_path / "eoj_gui_config.json.bak").is_file(), "应保留旧文件备份"


def test_apply_credentials_and_save(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    settings = Settings(root=str(tmp_path), load_file=False)
    settings.apply_credentials(username="u", password="p", api_key="k", model="m",
                               base_url="https://api.deepseek.com")
    assert settings.eoj.username == "u"
    assert settings.llm.model == "m"
    assert settings.llm.base_url == "https://api.deepseek.com/v1"
    path = settings.save()
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["api_key"] == "k"
    assert data["model"] == "m"


def test_remember_false_drops_password(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    settings = Settings(root=str(tmp_path), load_file=False)
    settings.apply_credentials(username="u", password="secret")
    settings.eoj.remember = False
    data = settings.to_file_dict()
    assert "password" not in data


def test_describe_masks_key(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    settings = Settings(root=str(tmp_path), load_file=False)
    settings.llm.api_key = "sk-abcdefghijklmnop"
    text = settings.describe()
    assert "sk-abcdefghijklmnop" not in text
    assert "..." in text


def test_dotenv_parsing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "DEEPSEEK_API_KEY=sk-from-dotenv\n"
        'QUOTED="value with spaces"\n'
        "export EXPORTED=yes\n"
        "EMPTY=\n"
        "NOEQUALS\n",
        encoding="utf-8",
    )
    values = cfg._parse_env_file(str(env_file))
    assert values["DEEPSEEK_API_KEY"] == "sk-from-dotenv"
    assert values["QUOTED"] == "value with spaces"
    assert values["EXPORTED"] == "yes"
    assert values["EMPTY"] == ""
    assert "NOEQUALS" not in values


# ==========================================================================
# 题号范围解析
# ==========================================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1001-1005", ["1001", "1002", "1003", "1004", "1005"]),
        ("1001 - 1003", ["1001", "1002", "1003"]),
        ("5-1", ["1", "2", "3", "4", "5"]),
        ("1001", None),
        ("abc", None),
        ("", None),
    ],
)
def test_extract_problem_ids_from_range(raw, expected):
    assert extract_problem_ids_from_range(raw) == expected


# ==========================================================================
# EOJConfig
# ==========================================================================

def test_eoj_config_default_solutions_dir():
    conf = EOJConfig()
    assert conf.solutions_dir.endswith(SOLUTIONS_DIRNAME)
    assert os.path.isabs(conf.solutions_dir)
