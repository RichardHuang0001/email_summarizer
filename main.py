#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 邮件自动化主入口
用法示例：
    python main.py --limit 20 --to someone@example.com --subject "每日邮件总结"
"""
import os
import sys
import json
import argparse
from dotenv import load_dotenv

# Add src directory to Python path for src layout
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from email_summarizer.chain import run_pipeline
from email_summarizer.utils.config import get_email_service_config

load_dotenv()

REQUIRED_VARS = ["OPENAI_API_KEY", "EMAIL_USE"]


def check_config() -> bool:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print("❌ 配置检查失败！缺少以下环境变量：")
        for v in missing:
            print(f"   - {v}")
        print("请先在 .env 中填充必要配置。\n")
        return False

    # 新的容错配置检查：支持简易变量或 JSON 两种方式
    try:
        cfg = get_email_service_config()
        email_use = os.getenv("EMAIL_USE", "GMAIL").upper()
        print(f"✅ 配置检查通过！服务: {email_use}，发件人: {cfg['username']}")
        return True
    except Exception as e:
        print(f"❌ 邮箱配置无效：{e}")
        print("💡 请在 .env 中填写 EMAIL_USERNAME 和 EMAIL_PASSWORD（或 EMAIL_USER/EMAIL_AUTH_CODE），并设置 EMAIL_USE 为 GMAIL/163/QQ/OUTLOOK 之一。")
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="LLM 邮件自动化")
    parser.add_argument("--limit", type=int, default=20, help="读取新邮件最大数量 (1-50)")
    parser.add_argument("--to", type=str, default=os.getenv("DEFAULT_NOTIFY_TO"), help="总结通知的目标邮箱地址（默认读取环境变量 DEFAULT_NOTIFY_TO）")
    parser.add_argument("--subject", type=str, default="今日邮件摘要", help="通知邮件主题")
    parser.add_argument("--all", action="store_true", help="读取所有邮件而非仅未读")
    parser.add_argument("--send-attachment", action="store_true", help="是否发送归档文件作为附件（默认不发送）")
    return parser.parse_args()


def main():
    print("📧 LLM 邮件自动化")
    print("=" * 50)

    if not check_config():
        return

    args = parse_args()
    if not args.to:
        print("❌ 未指定收件人。请使用 --to 或在 .env 中设置 DEFAULT_NOTIFY_TO。")
        return

    result = run_pipeline(limit=args.limit, target_email=args.to, subject=args.subject, use_unseen=(not args.all), send_attachment=args.send_attachment)

    if result.get("status") in ("sent", "partial"):
        if result["status"] == "sent":
            print("\n🎉 总结邮件已发送！")
        else:
            print(f"\n✅ 邮件总结已完成！（{result.get('warning', '')}）")
            if result.get("send_error"):
                print(f"⚠️ 发送失败原因: {result['send_error']}")
        print(f"- 收件人: {result['to']}")
        print(f"- 主题: {result['subject']}")
        print(f"- 归档文件: {result['archive_path']}")
        print(f"- 处理邮件数量: {result['email_count']}")
    elif result.get("status") == "no_new_emails":
        print("\nℹ️ 没有新的待处理邮件。")
    else:
        print("\n⚠️ 发送状态异常：", result)


if __name__ == "__main__":
    main()