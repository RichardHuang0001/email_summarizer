#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 邮件自动化主入口
用法示例：
    python main.py --limit 20 --to someone@example.com --subject "每日邮件总结"
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from email_summarizer.chain import run_pipeline
from email_summarizer.utils.config import get_email_service_config
from email_summarizer.utils.config_loader import get_config
from email_summarizer.utils.console import Console

_cfg = get_config()
_llm_cfg = _cfg.get('llm', {})
_email_cfg = _cfg.get('email', {})
_adv_cfg = _cfg.get('advanced', {})


def check_config() -> bool:
    llm_cfg = _cfg.get('llm', {})
    email_cfg = _email_cfg

    missing = []
    still_default = []

    if not llm_cfg.get('api_key'):
        missing.append(('OPENAI_API_KEY', '.env 文件'))
    if not email_cfg.get('service'):
        missing.append(('email.service', 'config.yaml'))
    if not email_cfg.get('username'):
        missing.append(('email.username', 'config.yaml'))
    else:
        # 检查是否还在使用模板占位符
        username = email_cfg.get('username', '')
        if username in ('your_email@gmail.com', 'your_email@example.com', ''):
            still_default.append(('email.username', 'config.yaml', '你的真实邮箱地址'))
    if not email_cfg.get('password'):
        missing.append(('EMAIL_PASSWORD', '.env 文件'))

    # 检查 notify_to 是否还是占位符
    notify_to = email_cfg.get('notify_to', '')
    if notify_to in ('your_email@example.com', ''):
        still_default.append(('email.notify_to', 'config.yaml', '接收总结报告的邮箱'))

    if missing:
        Console.fail("配置检查失败 - 以下必填项未设置：")
        for name, location in missing:
            Console.step_info(f"  ✗  {name} → 请在 {location} 中填写")
        Console.blank()

    if still_default:
        Console.warn("以下配置项仍为模板默认值，请改为你自己的信息：")
        for name, location, hint in still_default:
            Console.step_info(f"  ✗  {name} → 改为 {hint}")
        Console.blank()

    if missing or still_default:
        Console.info("需要帮助？打开以下文件按注释修改即可：")
        Console.step_info("  config.yaml — 邮箱类型、地址、收件人")
        Console.step_info("  .env        — API 密钥、邮箱授权码")
        return False

    try:
        svc_cfg = get_email_service_config()
        email_use = email_cfg.get('service', 'GMAIL').upper()
        Console.ok("配置检查通过")
        Console.stat_line([("服务", email_use), ("发件人", svc_cfg['username'])])
        return True
    except Exception as e:
        Console.fail(f"邮箱配置无效: {e}")
        Console.info("请在 config.yaml 中检查 email 相关配置，在 .env 中设置 EMAIL_PASSWORD")
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="LLM 邮件自动化")
    parser.add_argument("--limit", type=int, default=_llm_cfg.get('max_emails_per_run', 20), help="读取新邮件最大数量 (1-50)")
    parser.add_argument("--to", type=str, default=_email_cfg.get('notify_to'), help="总结通知的目标邮箱地址")
    parser.add_argument("--subject", type=str, default=_email_cfg.get('subject', '今日邮件摘要'), help="通知邮件主题")
    parser.add_argument("--all", action="store_true", help="读取所有邮件而非仅未读")
    parser.add_argument("--send-attachment", action="store_true", default=_adv_cfg.get('send_attachment', False), help="是否发送归档文件作为附件")
    return parser.parse_args()


def main():
    Console.banner("📧  LLM 邮件自动化")

    if not check_config():
        return

    args = parse_args()
    if not args.to:
        Console.fail("未指定收件人 - 请使用 --to 参数或在 config.yaml 中设置 email.notify_to")
        return

    result = run_pipeline(
        limit=args.limit,
        target_email=args.to,
        subject=args.subject,
        use_unseen=(not args.all),
        send_attachment=args.send_attachment,
    )

    status = result.get("status")

    if status in ("sent", "partial"):
        lines = [
            f"收件人  {result['to']}",
            f"主  题  {result['subject']}",
            f"处理量  {result['email_count']} 封邮件",
        ]
        if result.get("archive_path"):
            lines.append(f"归  档  {result['archive_path']}")
        if result.get("warning"):
            lines.append(f"备  注  {result['warning']}")

        if status == "sent":
            Console.result_box("✅  任务完成", lines)
        else:
            Console.result_box("✅  总结完成（发送失败）", lines)
            if result.get("send_error"):
                Console.inline_warning(f"发送失败原因: {result['send_error']}")

    elif status == "no_new_emails":
        Console.info("没有新的待处理邮件，无需操作")
    else:
        Console.error_box("处理异常", [str(result)])


if __name__ == "__main__":
    main()
