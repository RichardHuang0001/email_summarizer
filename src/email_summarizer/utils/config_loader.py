#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_loader.py
统一配置加载器：从 config.yaml 加载所有配置，从 .env 加载敏感信息
首次使用时自动从模板创建 config.yaml，降低小白用户的配置门槛
"""
import os
import shutil
from typing import Dict, Any, Optional

import yaml
from dotenv import load_dotenv

# 计算项目根路径：src/email_summarizer/utils/ -> src/email_summarizer/ -> src/ -> 项目根
_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_UTILS_DIR)
_SRC_DIR = os.path.dirname(_PKG_DIR)
PROJECT_ROOT = os.path.dirname(_SRC_DIR)

_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
_EXAMPLE_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config_example", "config.example.yaml")

_config_cache: Optional[Dict[str, Any]] = None

# ---- 首次运行引导 ----
_BOOTSTRAP_MSG = """
已自动创建 config.yaml（从模板复制）。
配置方法请参考 README.md，只需修改 5 个值即可运行。
"""


def _bootstrap_config():
    """从模板复制 config.yaml（仅首次运行）"""
    if not os.path.exists(_EXAMPLE_CONFIG_PATH):
        raise FileNotFoundError(
            f"配置文件模板不存在: {_EXAMPLE_CONFIG_PATH}\n"
            f"请确保项目文件完整，或从 GitHub 重新下载。"
        )

    shutil.copy(_EXAMPLE_CONFIG_PATH, _CONFIG_PATH)
    print(_BOOTSTRAP_MSG)

    raise SystemExit(0)


def load_config(reload: bool = False) -> Dict[str, Any]:
    """
    加载统一配置（带缓存）
    - 首次运行：从模板复制 config.yaml 并显示引导
    - 从 config.yaml 读取所有参数
    - 从 .env 读取敏感信息并合并
    """
    global _config_cache
    if _config_cache is not None and not reload:
        return _config_cache

    # 加载 .env（敏感信息）
    load_dotenv()

    # config.yaml 不存在 → 首次运行，自动引导
    if not os.path.exists(_CONFIG_PATH):
        _bootstrap_config()

    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    # 从 .env 合并敏感信息
    api_key = os.getenv('OPENAI_API_KEY', '')
    email_password = os.getenv('EMAIL_PASSWORD', '')

    config.setdefault('llm', {})['api_key'] = api_key
    config.setdefault('email', {})['password'] = email_password

    # 代理设置：.env 中的值优先，否则使用 config.yaml 中的值
    net_cfg = config.setdefault('network', {})
    http_proxy = os.getenv('HTTP_PROXY') or net_cfg.get('http_proxy', '')
    https_proxy = os.getenv('HTTPS_PROXY') or net_cfg.get('https_proxy', '')
    if http_proxy:
        os.environ['HTTP_PROXY'] = http_proxy
    if https_proxy:
        os.environ['HTTPS_PROXY'] = https_proxy

    _config_cache = config
    return _config_cache


def get_config() -> Dict[str, Any]:
    """获取统一配置（公共接口）"""
    return load_config()


def get_project_root() -> str:
    """获取项目根路径"""
    return PROJECT_ROOT
