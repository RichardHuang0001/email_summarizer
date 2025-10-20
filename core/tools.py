#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心工具模块
- EmailReaderTool: 使用 IMAP 读取新邮件，基于 Message-ID 去重并返回内容列表
- DocumentArchiverTool: 将总结内容归档到本地 Markdown 文档
- EmailSenderTool: 使用 SMTP 发送带附件的邮件
"""
import os
import json
import imaplib
import email
import smtplib
from datetime import datetime
from typing import Optional, Type, List, Dict
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

import html2text
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.tools import BaseTool
from imapclient import IMAPClient

load_dotenv()

# 计算项目根路径
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CORE_DIR)
STATE_PATH = os.path.join(BASE_DIR, "state", "processed_emails.json")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")

# 确保基础目录存在
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

# 加载邮箱配置
EMAIL_CONFIGS = json.loads(os.getenv("EMAIL_CONFIGS", "{}") or "{}")
EMAIL_SERVICE = os.getenv("EMAIL_USE", "QQ").upper()

# 解析代理设置（可选）
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")
if HTTP_PROXY:
    os.environ["HTTP_PROXY"] = HTTP_PROXY
if HTTPS_PROXY:
    os.environ["HTTPS_PROXY"] = HTTPS_PROXY


# ======== 工具：读取邮件 ========
class EmailReaderInput(BaseModel):
    max_count: int = Field(20, description="读取的新邮件最大数量，1-50")
    folder: str = Field("INBOX", description="读取的文件夹，默认 INBOX")
    use_unseen: bool = Field(True, description="是否仅读取未读邮件")


class EmailReaderTool(BaseTool):
    name: str = "email_reader_tool"
    description: str = (
        "使用 IMAP 读取邮箱中的新邮件，按 Message-ID 去重，返回结构化内容列表"
    )
    args_schema: Type[BaseModel] = EmailReaderInput

    def __init__(self, **data):
        super().__init__(**data)
        if EMAIL_SERVICE not in EMAIL_CONFIGS:
            raise ValueError(f"Unsupported email service: {EMAIL_SERVICE}")
        self._cfg = EMAIL_CONFIGS[EMAIL_SERVICE]
        self._email = self._cfg["username"]
        self._auth = self._cfg["password"]
        self._imap_host = self._cfg["imap_host"]
        self._h2t = html2text.HTML2Text()
        self._h2t.ignore_links = True

    @staticmethod
    def _load_state() -> Dict[str, List[str]]:
        if not os.path.exists(STATE_PATH):
            return {"processed_ids": []}
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"processed_ids": []}

    @staticmethod
    def _save_state(state: Dict[str, List[str]]):
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _decode_header(value: Optional[str]) -> str:
        if not value:
            return ""
        decoded = decode_header(value)
        out = ""
        for s, enc in decoded:
            if isinstance(s, bytes):
                try:
                    out += s.decode(enc or "utf-8", errors="ignore")
                except Exception:
                    out += s.decode("utf-8", errors="ignore")
            else:
                out += str(s)
        return out

    def _extract_content(self, msg: email.message.Message) -> str:
        content = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    try:
                        content = part.get_payload(decode=True).decode()
                    except Exception:
                        content = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
                elif ctype == "text/html":
                    try:
                        html = part.get_payload(decode=True).decode()
                    except Exception:
                        html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    content = self._h2t.handle(html)
                    break
        else:
            try:
                content = msg.get_payload(decode=True).decode()
            except Exception:
                content = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        content = content.strip()
        content = " ".join(content.split())
        return content

    def _run(self, max_count: int = 20, folder: str = "INBOX", use_unseen: bool = True) -> str:
        # 返回 JSON 字符串，包含新邮件的结构化数据
        max_count = max(1, min(50, int(max_count)))
        state = self._load_state()
        processed_ids = set(state.get("processed_ids", []))
        results: List[Dict] = []

        try:
            with IMAPClient(self._imap_host, ssl=True) as client:
                client.login(self._email, self._auth)
                # 163/Coremail 等服务的 ID 握手（若不支持则忽略错误）
                try:
                    client.id_({"name": "email-summarizer", "version": "0.1", "vendor": "TraeAI", "os": "macOS"})
                except Exception:
                    pass

                # 优先只读选择，失败则读写
                try:
                    client.select_folder(folder, readonly=True)
                except Exception:
                    client.select_folder(folder, readonly=False)

                criteria = ["UNSEEN"] if use_unseen else ["ALL"]
                uids = client.search(criteria)
                if not uids:
                    return json.dumps({"emails": []}, ensure_ascii=False)

                uids = sorted(uids)
                latest_uids = uids[-max_count:]

                new_ids: List[str] = []
                fetch_data = client.fetch(latest_uids, [b'RFC822'])
                for uid in reversed(latest_uids):
                    data = fetch_data.get(uid)
                    if not data:
                        continue
                    raw = data[b'RFC822']
                    msg = email.message_from_bytes(raw)

                    mid = (msg.get("Message-ID") or "").strip()
                    subject = self._decode_header(msg.get("Subject"))
                    sender = self._decode_header(msg.get("From"))
                    date = self._decode_header(msg.get("Date"))
                    content = self._extract_content(msg)

                    fallback_id = f"{uid}|{sender}|{subject}|{date}|{content[:64]}"
                    uniq_id = mid or str(uid) or fallback_id

                    if uniq_id in processed_ids:
                        continue

                    results.append({
                        "id": uniq_id,
                        "message_id": mid or None,
                        "from": sender,
                        "subject": subject or "(No Subject)",
                        "date": date,
                        "content": content
                    })
                    new_ids.append(uniq_id)

                if new_ids:
                    processed_ids.update(new_ids)
                    self._save_state({"processed_ids": list(processed_ids)})

                return json.dumps({"emails": results}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Failed to read emails: {str(e)}"}, ensure_ascii=False)


# ======== 工具：归档文档 ========
class ArchiverInput(BaseModel):
    report_text: str = Field(..., description="需要归档的汇总报告文本（Markdown）")
    file_name: Optional[str] = Field(None, description="自定义归档文件名，例如 archive_2025-10-19.html")
    append: bool = Field(True, description="是否以追加模式写入（HTML文档中追加新 section）")


class DocumentArchiverTool(BaseTool):
    name: str = "document_archiver_tool"
    description: str = "将总结文本保存为本地 HTML 归档文档，并返回文件路径"
    args_schema: Type[BaseModel] = ArchiverInput

    def _md_to_html(self, md: str) -> str:
        import html as _html
        lines = md.splitlines()
        buf: List[str] = []
        in_ul = False
        for line in lines:
            if line.startswith("### "):
                if in_ul:
                    buf.append("</ul>")
                    in_ul = False
                buf.append(f"<h3>{_html.escape(line[4:].strip())}</h3>")
            elif line.startswith("## "):
                if in_ul:
                    buf.append("</ul>")
                    in_ul = False
                buf.append(f"<h2>{_html.escape(line[3:].strip())}</h2>")
            elif line.startswith("- "):
                if not in_ul:
                    buf.append("<ul>")
                    in_ul = True
                buf.append(f"<li>{_html.escape(line[2:].strip())}</li>")
            elif line.strip() == "":
                if in_ul:
                    buf.append("</ul>")
                    in_ul = False
                buf.append("<br/>")
            else:
                buf.append(f"<p>{_html.escape(line.strip())}</p>")
        if in_ul:
            buf.append("</ul>")
        return "\n".join(buf)

    def _build_section(self, report_text: str) -> str:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        header = f"<h2 class='meta'>邮件总结归档 - {ts}</h2>"
        body = self._md_to_html(report_text)
        return f"<section class='section'>\n{header}\n{body}\n</section>\n"

    def _compose_document(self, section_html: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>邮件总结归档</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;line-height:1.6;padding:24px;color:#222;}}
h1,h2,h3{{margin:0.2em 0;}}
ul{{margin:0.2em 0 0.8em 1.2em;}}
li{{margin:0.2em 0;}}
.section{{margin-bottom:1.2em;padding-bottom:0.8em;border-bottom:1px solid #eee;}}
.meta{{color:#666;font-size:0.95em;}}
</style>
</head>
<body>
<h1>邮件总结归档</h1>
{section_html}
</body>
</html>
"""

    def _run(self, report_text: str, file_name: Optional[str] = None, append: bool = True) -> str:
        if not file_name:
            file_name = f"archive_{datetime.now().strftime('%Y-%m-%d')}.html"
        path = os.path.join(ARCHIVE_DIR, file_name)
        section_html = self._build_section(report_text)
        try:
            if append and os.path.exists(path):
                # 在已有 HTML 文档内追加新的 section（插入到 </body> 前）
                with open(path, "r+", encoding="utf-8") as f:
                    existing = f.read()
                    insert_pos = existing.rfind("</body>")
                    if insert_pos == -1:
                        # 非有效 HTML，重写完整文档
                        doc = self._compose_document(section_html)
                        f.seek(0)
                        f.write(doc)
                        f.truncate()
                    else:
                        new_content = existing[:insert_pos] + section_html + existing[insert_pos:]
                        f.seek(0)
                        f.write(new_content)
                        f.truncate()
            else:
                doc = self._compose_document(section_html)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(doc)
            return json.dumps({"archive_path": path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Failed to write archive: {str(e)}"}, ensure_ascii=False)


# ======== 工具：发送邮件 ========
class SenderInput(BaseModel):
    to: str = Field(..., description="目标邮箱地址")
    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件正文（纯文本或HTML）")
    is_html: bool = Field(False, description="正文是否为 HTML 格式")
    attachment_path: Optional[str] = Field(None, description="附件路径，可选")
    cc: Optional[str] = Field(None, description="抄送邮箱地址，可选")


class EmailSenderTool(BaseTool):
    name: str = "email_sender_tool"
    description: str = "通过 SMTP 发送邮件，支持 HTML/附件/抄送"
    args_schema: Type[BaseModel] = SenderInput

    def __init__(self, **data):
        super().__init__(**data)
        if EMAIL_SERVICE not in EMAIL_CONFIGS:
            raise ValueError(f"Unsupported email service: {EMAIL_SERVICE}")
        self._cfg = EMAIL_CONFIGS[EMAIL_SERVICE]
        self._email = self._cfg["username"]
        self._auth = self._cfg["password"]
        self._smtp_host = self._cfg["smtp_host"]
        self._smtp_port = int(self._cfg["smtp_port"]) if isinstance(self._cfg["smtp_port"], (str, int)) else 465

    def _prepare_message(self, to: str, subject: str, body: str, is_html: bool = False,
                          attachment_path: Optional[str] = None, cc: Optional[str] = None) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["From"] = self._email
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject

        mime_text = MIMEText(body, "html", "utf-8") if is_html else MIMEText(body, "plain", "utf-8")
        msg.attach(mime_text)

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read())
                filename = os.path.basename(attachment_path)
                part.add_header('Content-Disposition', 'attachment', filename=filename)
                msg.attach(part)
        return msg

    def _run(self, to: str, subject: str, body: str, is_html: bool = False, attachment_path: Optional[str] = None, cc: Optional[str] = None) -> str:
        try:
            msg = self._prepare_message(to, subject, body, is_html=is_html, attachment_path=attachment_path, cc=cc)
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port) as server:
                server.login(self._email, self._auth)
                to_addrs = [to] + ([cc] if cc else [])
                server.sendmail(self._email, to_addrs, msg.as_string())
            return json.dumps({"status": "sent", "to": to, "subject": subject}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Failed to send email: {str(e)}"}, ensure_ascii=False)