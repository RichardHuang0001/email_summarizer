#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py
为邮箱服务提供容错的配置加载：
- 优先读取 config.yaml 中对应服务；缺失项自动回填默认值
- 为电脑小白优化：只需要在 config.yaml 填 email.service、email.username，
  在 .env 填 EMAIL_PASSWORD 即可
"""
from typing import Dict

from .config_loader import get_config


def get_email_service_config() -> Dict:
    """
    统一加载邮箱服务配置（容错）：
    - 从 config.yaml 读取 email 节和服务商默认值
    - 校验用户名/密码是否存在
    """
    cfg = get_config()

    email_cfg = cfg.get('email', {})
    service_defaults = cfg.get('service_defaults', {})

    svc = (email_cfg.get('service') or 'GMAIL').upper()
    if svc not in service_defaults:
        raise ValueError(
            f"不支持的邮箱服务类型「{svc}」\n"
            f"请在 config.yaml 中修改 email.service 为以下之一：\n"
            f"  GMAIL / QQ / 163 / OUTLOOK\n"
            f"当前填写的值: {svc}"
        )

    defaults = service_defaults[svc]

    username = email_cfg.get('username', '')
    password = email_cfg.get('password', '')  # 由 config_loader 从 .env 合并

    imap_host = email_cfg.get('imap_host') or defaults['imap_host']
    smtp_host = email_cfg.get('smtp_host') or defaults['smtp_host']
    smtp_port_raw = email_cfg.get('smtp_port')
    smtp_port = int(smtp_port_raw) if smtp_port_raw else int(defaults['smtp_port'])

    result = {
        'service_name': svc,
        'imap_host': imap_host,
        'smtp_host': smtp_host,
        'smtp_port': smtp_port,
        'username': username,
        'password': password,
    }

    if not result['username'] or not result['password']:
        raise ValueError(
            "邮箱账号或授权码未填写：\n"
            "  - 在 config.yaml 中设置 email.username（你的邮箱地址）\n"
            "  - 在 .env 文件中设置 EMAIL_PASSWORD（邮箱授权码，非登录密码）\n"
            "\n"
            "获取授权码的方法：\n"
            "  Gmail: 账户设置 → 安全性 → 两步验证 → 应用专用密码\n"
            "  QQ邮箱: 设置 → 账户 → POP3/SMTP服务 → 生成授权码\n"
            "  163邮箱: 设置 → POP3/SMTP/IMAP → 新增授权码"
        )

    return result
