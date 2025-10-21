#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py
为邮箱服务提供容错的配置加载：
- 优先读取 EMAIL_CONFIGS JSON 中对应服务；缺失项自动回填默认值
- 如果没有 EMAIL_CONFIGS 或解析失败，则使用简单环境变量：
  EMAIL_USE, EMAIL_USERNAME/EMAIL_USER, EMAIL_PASSWORD/EMAIL_AUTH_CODE,
  IMAP_HOST(可选), SMTP_HOST(可选), SMTP_PORT(可选)
- 为电脑小白优化：只需要填 EMAIL_USE、EMAIL_USERNAME、EMAIL_PASSWORD 即可
"""
import os
import json
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

SUPPORTED_SERVICES = {"GMAIL", "163", "QQ", "OUTLOOK"}
DEFAULTS: Dict[str, Dict] = {
    "GMAIL": {
        "imap_host": "imap.gmail.com",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
    },
    "OUTLOOK": {
        "imap_host": "outlook.office365.com",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
    },
    "QQ": {
        "imap_host": "imap.qq.com",
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
    },
    "163": {
        "imap_host": "imap.163.com",
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
    },
}


def _read_simple_vars(svc: str) -> Dict:
    """从简单环境变量读取配置，并使用默认值回填缺失项"""
    username = os.getenv("EMAIL_USERNAME") or os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD") or os.getenv("EMAIL_AUTH_CODE")

    imap_host = os.getenv("IMAP_HOST") or DEFAULTS[svc]["imap_host"]
    smtp_host = os.getenv("SMTP_HOST") or DEFAULTS[svc]["smtp_host"]
    smtp_port_raw = os.getenv("SMTP_PORT")
    smtp_port = int(smtp_port_raw) if smtp_port_raw else int(DEFAULTS[svc]["smtp_port"])

    return {
        "service_name": svc,
        "imap_host": imap_host,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "username": username,
        "password": password,
    }


def get_email_service_config() -> Dict:
    """
    统一加载邮箱服务配置（容错）：
    - 如果 EMAIL_CONFIGS JSON 存在且有效，读取对应服务并与简单变量合并
    - 否则使用简单变量 + 默认值
    - 校验用户名/密码是否存在
    """
    svc = (os.getenv("EMAIL_USE") or "GMAIL").upper()
    if svc not in SUPPORTED_SERVICES:
        raise ValueError(f"不支持的邮箱服务: {svc}。请在 .env 中将 EMAIL_USE 设置为 GMAIL/163/QQ/OUTLOOK 之一。")

    # 尝试解析 EMAIL_CONFIGS JSON
    cfg_json = os.getenv("EMAIL_CONFIGS")
    if cfg_json:
        try:
            cfg = json.loads(cfg_json)
            if isinstance(cfg, dict) and svc in cfg:
                base = DEFAULTS[svc].copy()
                src = cfg.get(svc, {}) or {}

                # 合并配置，缺失项回填默认值
                imap_host = src.get("imap_host") or base["imap_host"]
                smtp_host = src.get("smtp_host") or base["smtp_host"]
                smtp_port = int(src.get("smtp_port", base["smtp_port"]))
                username = src.get("username") or os.getenv("EMAIL_USERNAME") or os.getenv("EMAIL_USER")
                password = src.get("password") or os.getenv("EMAIL_PASSWORD") or os.getenv("EMAIL_AUTH_CODE")

                result = {
                    "service_name": svc,
                    "imap_host": imap_host,
                    "smtp_host": smtp_host,
                    "smtp_port": smtp_port,
                    "username": username,
                    "password": password,
                }

                if not result["username"] or not result["password"]:
                    raise ValueError("缺少邮箱账号或授权码：请在 .env 中填写 EMAIL_USERNAME 和 EMAIL_PASSWORD（或 EMAIL_USER/EMAIL_AUTH_CODE）。")
                return result
        except Exception:
            # JSON 解析失败则回退到简单变量
            pass

    # 使用简单变量方案
    simple = _read_simple_vars(svc)
    if not simple["username"] or not simple["password"]:
        raise ValueError("缺少邮箱账号或授权码：请在 .env 中填写 EMAIL_USERNAME 和 EMAIL_PASSWORD（或 EMAIL_USER/EMAIL_AUTH_CODE）。")
    return simple