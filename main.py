#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 邮件自动化主入口
用法示例：
    python main.py --limit 20 --to someone@example.com --subject "每日邮件总结"
"""
import os
import json
import argparse
from dotenv import load_dotenv

from core.chain import run_pipeline

load_dotenv()

REQUIRED_VARS = ["OPENAI_API_KEY", "EMAIL_USE", "EMAIL_CONFIGS"]


def check_config() -> bool:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print("❌ 配置检查失败！缺少以下环境变量：")
        for v in missing:
            print(f"   - {v}")
        print("请先运行 scripts/setup_config.py 或在 .env 中填充必要配置。\n")
        return False

    try:
        email_configs = json.loads(os.getenv("EMAIL_CONFIGS"))
        email_use = os.getenv("EMAIL_USE", "QQ").upper()
        if email_use not in email_configs:
            print(f"❌ EMAIL_USE={email_use} 不在 EMAIL_CONFIGS 中，请检查配置。")
            return False
    except Exception:
        print("❌ EMAIL_CONFIGS 不是有效的 JSON，请检查 .env 配置。")
        return False

    print("✅ 配置检查通过！")
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="LLM 邮件自动化")
    parser.add_argument("--limit", type=int, default=20, help="读取新邮件最大数量 (1-50)")
    parser.add_argument("--to", type=str, required=True, help="总结通知的目标邮箱地址")
    parser.add_argument("--subject", type=str, default="邮件每日总结", help="通知邮件主题")
    parser.add_argument("--all", action="store_true", help="读取所有邮件而非仅未读")
    return parser.parse_args()


def main():
    print("📧 LLM 邮件自动化")
    print("=" * 50)

    if not check_config():
        return

    args = parse_args()

    result = run_pipeline(limit=args.limit, target_email=args.to, subject=args.subject, use_unseen=(not args.all))

    if result.get("status") == "sent":
        print("\n🎉 总结邮件已发送！")
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