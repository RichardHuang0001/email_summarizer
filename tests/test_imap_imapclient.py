#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMAP + SMTP 连通性测试（使用 imapclient + smtplib）
- 发送 ID 握手
- 选择 INBOX
- 搜索 UNSEEN 并读取摘要
- 可选 APPEND 一封自测邮件
- 完成测试后，仅发送一封“IMAP 配置验证结果”到默认目标邮箱
"""
import os
import json
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

from dotenv import load_dotenv

load_dotenv()

try:
    from imapclient import IMAPClient
except Exception:
    print("❌ 缺少依赖 imapclient，请先安装：pip install imapclient")
    sys.exit(1)


def get_service_cfg():
    """返回完整服务配置（包含 IMAP/SMTP/用户名/授权码）"""
    cfg = json.loads(os.getenv("EMAIL_CONFIGS", "{}") or "{}")
    svc = os.getenv("EMAIL_USE", "QQ").upper()
    if svc in cfg:
        c = cfg[svc]
        c["service_name"] = svc
        return c
    # 兼容示例中的环境变量
    return {
        "imap_host": os.getenv("IMAP_HOST", "imap.163.com"),
        "smtp_host": os.getenv("SMTP_HOST", "smtp.163.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "465")),
        "username": os.getenv("EMAIL_USER") or os.getenv("EMAIL_USERNAME"),
        "password": os.getenv("EMAIL_AUTH_CODE") or os.getenv("EMAIL_PASSWORD"),
        "service_name": os.getenv("EMAIL_USE", "UNKNOWN").upper(),
    }


def get_target_email(default_sender: str) -> str:
    return os.getenv("DEFAULT_NOTIFY_TO") or default_sender


def decode_email_subject(subject):
    """解码邮件标题，处理各种编码格式"""
    if subject is None:
        return "无标题"
    
    # 如果是bytes类型，先转换为字符串
    if isinstance(subject, bytes):
        subject = subject.decode('utf-8', errors='ignore')
    
    # 转换为字符串
    subject_str = str(subject)
    
    # 处理编码的标题（如 =?UTF-8?B?...?= 格式）
    try:
        decoded_parts = decode_header(subject_str)
        decoded_subject = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    try:
                        decoded_subject += part.decode(encoding, errors='ignore')
                    except (UnicodeDecodeError, LookupError):
                        # 如果指定编码失败，尝试UTF-8
                        decoded_subject += part.decode('utf-8', errors='ignore')
                else:
                    # 没有指定编码，尝试UTF-8
                    decoded_subject += part.decode('utf-8', errors='ignore')
            else:
                decoded_subject += str(part)
        return decoded_subject.strip()
    except Exception as e:
        # 如果解码失败，返回原始字符串
        return subject_str


def make_test_message(fr: str, to: str) -> bytes:
    msg = MIMEMultipart()
    msg["From"] = fr
    msg["To"] = to
    msg["Subject"] = "IMAPClient 自测邮件"
    msg.attach(MIMEText(f"这是IMAPClient的APPEND自测内容，时间 {datetime.now().isoformat()}", "plain", "utf-8"))
    return msg.as_bytes()


def send_smtp_mail(smtp_host: str, smtp_port: int, user: str, pwd: str, to: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    server = smtplib.SMTP_SSL(smtp_host, smtp_port)
    server.login(user, pwd)
    server.sendmail(user, [to], msg.as_string())
    server.quit()


if __name__ == "__main__":
    c = get_service_cfg()
    host, user, pwd = c["imap_host"], c["username"], c["password"]
    to_addr = get_target_email(user)

    print("🔎 使用 imapclient 测试 IMAP 连接:")
    print(f"- host: {host}")
    print(f"- user: {user}")
    print(f"- to:   {to_addr}")

    # 汇总日志
    logs = []

    try:
        with IMAPClient(host, ssl=True) as client:
            client.login(user, pwd)
            # 发送 ID 握手（imapclient 原生支持）
            try:
                id_data = {"name": "email-summarizer", "version": "0.1", "vendor": "TraeAI", "os": "macOS"}
                resp = client.id_(id_data)
                print("✅ ID 握手成功:", resp)
                logs.append("[IMAP] ID 握手：成功")
            except Exception as e:
                print("⚠️ ID 握手失败:", e)
                logs.append(f"[IMAP] ID 握手：失败（{e}）")

            # 列出文件夹
            try:
                folders = client.list_folders()
                folder_names = [f[2] for f in folders]
                print("📁 文件夹:", folder_names)
                logs.append(f"[IMAP] 文件夹：{folder_names}")
            except Exception as e:
                print("⚠️ 列出文件夹失败:", e)
                logs.append(f"[IMAP] 列出文件夹：失败（{e}）")

            # 选择 INBOX（优先只读）
            try:
                client.select_folder("INBOX", readonly=True)
                print("✅ 已选择 INBOX (readonly)")
                logs.append("[IMAP] 选择 INBOX：只读成功")
            except Exception as e:
                print("⚠️ EXAMINE 失败，尝试 SELECT:", e)
                logs.append(f"[IMAP] EXAMINE 失败（{e}），改为读写")
                client.select_folder("INBOX", readonly=False)
                print("✅ 已选择 INBOX (readwrite)")
                logs.append("[IMAP] 选择 INBOX：读写成功")

            # 搜索未读
            try:
                uids = client.search(["UNSEEN"])  # 使用 UID 模式
                print(f"📬 未读UID数量: {len(uids)}")
                logs.append(f"[IMAP] 未读数量：{len(uids)}")
                if uids:
                    # 读取少量摘要字段
                    fetch_data = client.fetch(uids[:5], [b'ENVELOPE'])
                    for uid, data in fetch_data.items():
                        env = data.get(b'ENVELOPE')
                        subject = decode_email_subject(env.subject)
                        print(f"  - UID={uid} subject={subject}")
            except Exception as e:
                print("❌ 搜索/读取失败:", e)
                logs.append(f"[IMAP] 搜索/读取：失败（{e}）")

            # 读取最近一封邮件并打印标题
            try:
                print("\n📧 正在读取最近一封邮件...")
                # 搜索所有邮件，按日期排序获取最新的
                all_uids = client.search(["ALL"])
                if all_uids:
                    # 获取最后一个UID（最新的邮件）
                    latest_uid = all_uids[-1]
                    print(f"📮 最新邮件UID: {latest_uid}")
                    
                    # 获取邮件的ENVELOPE信息（包含标题、发件人、日期等）
                    fetch_data = client.fetch([latest_uid], [b'ENVELOPE', b'INTERNALDATE'])
                    
                    if latest_uid in fetch_data:
                        data = fetch_data[latest_uid]
                        env = data.get(b'ENVELOPE')
                        internal_date = data.get(b'INTERNALDATE')
                        
                        # 解码并打印邮件信息
                        subject = decode_email_subject(env.subject)
                        sender = env.from_[0] if env.from_ else None
                        sender_name = decode_email_subject(sender.name) if sender and sender.name else "未知发件人"
                        sender_email = sender.mailbox.decode() + "@" + sender.host.decode() if sender else "未知邮箱"
                        
                        print(f"✅ 最新邮件信息:")
                        print(f"   📝 标题: {subject}")
                        print(f"   👤 发件人: {sender_name} <{sender_email}>")
                        print(f"   📅 日期: {internal_date}")
                        
                        logs.append(f"[IMAP] 最新邮件读取：成功，标题='{subject}'")
                    else:
                        print("⚠️ 无法获取最新邮件详情")
                        logs.append("[IMAP] 最新邮件读取：获取详情失败")
                else:
                    print("📭 邮箱中没有邮件")
                    logs.append("[IMAP] 最新邮件读取：邮箱为空")
            except Exception as e:
                print(f"❌ 读取最新邮件失败: {e}")
                logs.append(f"[IMAP] 最新邮件读取：失败（{e}）")

            # 附加一封测试邮件（不会对外发送，仅验证 APPEND）
            try:
                payload = make_test_message(user, user)
                client.append("INBOX", payload, flags=[b'\\Seen'])
                print("➕ 已追加一封自测邮件到 INBOX")
                logs.append("[IMAP] APPEND 自测：成功")
            except Exception as e:
                print("⚠️ 追加失败:", e)
                logs.append(f"[IMAP] APPEND 自测：失败（{e}）")
    except Exception as e:
        print(f"❌ 登录或操作失败: {e}")
        logs.append(f"[IMAP] 登录/操作：失败（{e}）")
        # 仍然推送结论，便于用户知晓

    # 发送唯一的“IMAP 配置验证结果”邮件
    try:
        header = (
            "如果你收到了这封邮件，说明当前 IMAP 邮箱配置已可用。\n"
            f"服务商: {c.get('service_name','UNKNOWN')}\n"
            f"账户: {user}\n"
            f"IMAP: {c.get('imap_host')}  SMTP: {c.get('smtp_host')}:{c.get('smtp_port',465)}\n"
        )
        report = header + "\nIMAP 测试结论如下：\n" + "\n".join(logs) + f"\n\n时间：{datetime.now().isoformat()}"
        send_smtp_mail(c["smtp_host"], c.get("smtp_port", 465), user, pwd, to_addr,
                       "IMAP 配置验证结果", report)
        print("📤 已发送 IMAP 配置验证结果到目标邮箱")
    except Exception as e:
        print("❌ 发送验证结果失败:", e)
        sys.exit(2)

    print("✅ 测试完成。")