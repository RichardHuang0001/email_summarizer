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
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from email_summarizer.chain import run_pipeline
from email_summarizer.utils.config import get_email_service_config
from email_summarizer.utils.console import Console

load_dotenv()

REQUIRED_VARS = ["OPENAI_API_KEY", "EMAIL_USE"]


def check_config() -> bool:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        Console.fail("配置检查失败 - 缺少以下环境变量：")
        for v in missing:
            Console.step_info(f"  {v}")
        Console.blank()
        Console.info("请在 .env 文件中填充必要配置后重试")
        return False

    try:
        cfg = get_email_service_config()
        email_use = os.getenv("EMAIL_USE", "GMAIL").upper()
        Console.ok("配置检查通过")
        Console.stat_line([("服务", email_use), ("发件人", cfg['username'])])
        return True
    except Exception as e:
        Console.fail(f"邮箱配置无效: {e}")
        Console.info("请在 .env 中填写 EMAIL_USERNAME 和 EMAIL_PASSWORD（或 EMAIL_USER/EMAIL_AUTH_CODE），并设置 EMAIL_USE")
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="LLM 邮件自动化")
    parser.add_argument("--limit", type=int, default=20, help="读取新邮件最大数量 (1-50)")
    parser.add_argument("--to", type=str, default=os.getenv("DEFAULT_NOTIFY_TO"), help="总结通知的目标邮箱地址")
    parser.add_argument("--subject", type=str, default="今日邮件摘要", help="通知邮件主题")
    parser.add_argument("--all", action="store_true", help="读取所有邮件而非仅未读")
    parser.add_argument("--send-attachment", action="store_true", help="是否发送归档文件作为附件")
    return parser.parse_args()


def main():
    Console.banner("📧  LLM 邮件自动化")

    if not check_config():
        return

    args = parse_args()
    if not args.to:
        Console.fail("未指定收件人 - 请使用 --to 参数或在 .env 中设置 DEFAULT_NOTIFY_TO")
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
