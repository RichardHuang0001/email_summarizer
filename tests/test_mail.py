#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMAP + SMTP 连通性测试（使用 imapclient + smtplib）
- 兼容 163 和 Gmail
- 根据服务器类型，选择性发送 ID 握手
- **详细列出所有可用文件夹**
- **测试关键文件夹的可访问性**
- 选择 INBOX, 搜索 UNSEEN, 读取最新邮件
- 发送包含详细测试结果的报告邮件
"""
import os
import json
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header, make_header
from typing import Optional, List, Tuple

from dotenv import load_dotenv

load_dotenv()

# 兼容 src 布局，允许导入 email_summarizer.*
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
from email_summarizer.utils.config import get_email_service_config

try:
    from imapclient import IMAPClient
except Exception:
    print("❌ 缺少依赖 imapclient，请先安装：pip install imapclient")
    sys.exit(1)

# --- 常量 ---
# 文件夹可访问性测试列表
FOLDERS_TO_TEST = [
    "INBOX",
    "[Gmail]/Sent Mail", # Gmail 已发送 (示例)
    "[Gmail]/Spam",     # Gmail 垃圾邮件 (示例)
    "[Gmail]/Promotions",# Gmail 推广 (猜测)
    "[Gmail]/Social Updates", # Gmail 社交 (猜测)
    "Sent Messages",    # 其他邮箱 已发送 (常见)
    "Drafts",           # 草稿箱 (常见)
    "Junk",             # 垃圾邮件 (常见)
    "Deleted Messages", # 已删除 (常见)
]


def get_service_cfg():
    """返回完整服务配置（新的容错加载方式）"""
    return get_email_service_config()


def get_target_email(default_sender: str) -> str:
    return os.getenv("DEFAULT_NOTIFY_TO") or default_sender


def decode_folder_name(folder_bytes: bytes) -> str:
    """尝试解码IMAP文件夹名称 (通常是UTF7-Modified)"""
    try:
        # IMAP 文件夹名常用 UTF-7 Modified 编码处理非 ASCII 字符
        return folder_bytes.decode('imap4-utf-7')
    except Exception:
        # 解码失败，尝试 UTF-8 或返回原始表示
        try:
            return folder_bytes.decode('utf-8', 'ignore')
        except Exception:
            return str(folder_bytes)


def decode_email_subject(value: Optional[bytes]) -> str:
    """使用 make_header 正确解码邮件头部(bytes -> str)"""
    if not value: return "无标题"
    try:
        if isinstance(value, bytes): value_str = value.decode('utf-8', 'ignore')
        else: value_str = str(value)
        header = make_header(decode_header(value_str))
        return str(header)
    except Exception:
        return value.decode('utf-8', 'ignore') if isinstance(value, bytes) else str(value)


def send_smtp_mail(smtp_host: str, smtp_port: int, user: str, pwd: str, to: str, subject: str, body: str):
    """根据端口智能选择 SMTP_SSL 或 STARTTLS 发送邮件"""
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    
    server = None
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())
    finally:
        if server:
            server.quit()


if __name__ == "__main__":
    c = get_service_cfg()
    host, user, pwd = c["imap_host"], c["username"], c["password"]
    to_addr = get_target_email(user)

    print("🔎 使用 imapclient 测试 IMAP 连接:")
    print(f"--- 服务商: {c.get('service_name','UNKNOWN')}")
    print(f"--- IMAP 主机: {host}")
    print(f"--- SMTP 主机: {c.get('smtp_host')}:{c.get('smtp_port', 465)}")
    print(f"--- 用户名: {user}")
    print(f"--- 报告发送至: {to_addr}")

    logs = [
        f"服务商: {c.get('service_name','UNKNOWN')}",
        f"账户: {user}",
        f"IMAP: {host}",
        f"SMTP: {c.get('smtp_host')}:{c.get('smtp_port',465)}",
        f"时间: {datetime.now().isoformat()}",
        "--- IMAP 测试详情 ---"
    ]
    all_folders_found: List[str] = []

    try:
        with IMAPClient(host, ssl=True, timeout=20) as client:
            client.login(user, pwd)
            logs.append("[登录]: 成功")
            
            # 兼容性 ID 握手
            if "163.com" in host.lower():
                try:
                    client.id_({"name": "imap-test-script"})
                    logs.append("[ID 握手 (163)]: 成功")
                except Exception as e:
                    logs.append(f"[ID 握手 (163)]: 失败 ({e})")
            else:
                logs.append("[ID 握手]: 跳过 (非163)")

            # **【增强】列出所有文件夹**
            logs.append("\n--- 可用文件夹列表 ---")
            try:
                folders_raw: List[Tuple[Tuple[bytes, ...], bytes, bytes]] = client.list_folders()
                if folders_raw:
                    for flags, delimiter, name_bytes in folders_raw:
                        name = decode_folder_name(name_bytes)
                        all_folders_found.append(name)
                        logs.append(f"- {name} (原始: {name_bytes}, 分隔符: {delimiter}, 标志: {flags})")
                else:
                    logs.append("- 未找到任何文件夹")
                print(f"📁 找到 {len(all_folders_found)} 个文件夹 (详情见报告邮件)")
            except Exception as e:
                print(f"⚠️ 列出文件夹失败: {e}")
                logs.append(f"[错误] 列出文件夹失败: {e}")
            logs.append("--- 文件夹列表结束 ---")

            # **【新增】测试文件夹可访问性**
            logs.append("\n--- 文件夹可访问性测试 ---")
            print("\n🔬 正在测试关键文件夹的可访问性...")
            for folder_to_test in FOLDERS_TO_TEST:
                # 只测试实际存在的文件夹
                actual_name_to_test = next((f for f in all_folders_found if f.lower() == folder_to_test.lower()), None)
                if actual_name_to_test:
                    try:
                        # 尝试以只读方式选择
                        client.select_folder(actual_name_to_test, readonly=True)
                        logs.append(f"[选择测试] '{actual_name_to_test}': ✅ 可访问 (只读)")
                        print(f"  - '{actual_name_to_test}': ✅ 可访问")
                    except Exception as e:
                        logs.append(f"[选择测试] '{actual_name_to_test}': ❌ 失败 ({e})")
                        print(f"  - '{actual_name_to_test}': ❌ 失败 ({e})")
                else:
                    logs.append(f"[选择测试] '{folder_to_test}': ❓ 不存在")
                    # print(f"  - '{folder_to_test}': ❓ 不存在") # 可选：减少控制台输出
            logs.append("--- 文件夹测试结束 ---")

            # 选择 INBOX (必要步骤)
            try:
                client.select_folder("INBOX", readonly=True)
                logs.append("\n[选择 INBOX]: ✅ 成功 (只读)")
            except Exception as e:
                logs.append(f"\n[选择 INBOX]: ❌ EXAMINE 失败 ({e}), 尝试读写")
                client.select_folder("INBOX", readonly=False)
                logs.append("[选择 INBOX]: ✅ 成功 (读写)")

            # 搜索未读
            try:
                uids = client.search(["UNSEEN"])
                logs.append(f"[搜索未读]: ✅ 成功, 数量 {len(uids)}")
            except Exception as e:
                logs.append(f"[搜索未读]: ❌ 失败 ({e})")

            # 读取最近一封邮件
            logs.append("\n--- 最新邮件测试 ---")
            try:
                all_uids = client.search(["ALL"])
                if all_uids:
                    latest_uid = all_uids[-1]
                    fetch_data = client.fetch([latest_uid], [b'ENVELOPE', b'INTERNALDATE'])
                    if latest_uid in fetch_data:
                        env = fetch_data[latest_uid][b'ENVELOPE']
                        internal_date = fetch_data[latest_uid][b'INTERNALDATE']
                        subject = decode_email_subject(env.subject)
                        logs.append(f"[最新邮件]: ✅ 成功读取 (UID: {latest_uid}, 主题: '{subject}')")
                        # 可以在这里添加更多详情到日志
                    else:
                        logs.append("[最新邮件]: ❌ 获取详情失败")
                else:
                    logs.append("[最新邮件]: 邮箱为空")
            except Exception as e:
                logs.append(f"[最新邮件]: ❌ 读取失败 ({e})")

    except Exception as e:
        print(f"❌ IMAP 流程失败: {e}")
        logs.append(f"\n[严重错误] IMAP 流程失败: {e}")

    # 发送测试报告邮件
    try:
        report = "\n".join(logs)
        print("\n📤 正在发送测试报告...")
        send_smtp_mail(c["smtp_host"], c.get("smtp_port", 465), user, pwd, to_addr,
                       f"✅ IMAP/SMTP 测试报告 - {c.get('service_name','UNKNOWN')}", report)
        print("✅ 测试报告已发送。")
    except Exception as e:
        print(f"❌ 发送测试报告失败: {e}")
        logs.append(f"\n[严重错误] 发送报告失败: {e}")
        # 即使报告发送失败，也尝试打印日志
        print("\n--- 完整测试日志 ---")
        print("\n".join(logs))
        sys.exit(2)

    print("🎉 测试完成。请检查您的目标邮箱获取详细报告。")