#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
email_sender.py. : 通过 SMTP 发送邮件，支持 HTML/附件/抄送（带重试和智能连接）
"""
import os
import json
import smtplib
from typing import Optional, Type
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.tools import BaseTool

from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EMAIL_CONFIGS = json.loads(os.getenv("EMAIL_CONFIGS", "{}") or "{}")
EMAIL_SERVICE = os.getenv("EMAIL_USE", "GMAIL").upper()


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
        # 根据服务商设置默认端口
        default_port = 465 if "163.com" in self._smtp_host else 587
        self._smtp_port = int(self._cfg.get("smtp_port", default_port))

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

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _run(self, to: str, subject: str, body: str, is_html: bool = False, attachment_path: Optional[str] = None, cc: Optional[str] = None) -> str:
        try:
            msg = self._prepare_message(to, subject, body, is_html=is_html, attachment_path=attachment_path, cc=cc)
            
            print("  - [SMTP] 正在尝试发送邮件...")
            
            # --- 【核心修改】 ---
            # 根据端口号，智能选择 SMTP_SSL (465) 或 STARTTLS (587)
            if self._smtp_port == 465:
                print(f"  - [SMTP] 使用 SMTP_SSL (端口 {self._smtp_port}) 连接...")
                with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=30) as server:
                    server.login(self._email, self._auth)
                    to_addrs = [to] + ([cc] if cc else [])
                    server.sendmail(self._email, to_addrs, msg.as_string())
            else:
                print(f"  - [SMTP] 使用 STARTTLS (端口 {self._smtp_port}) 连接...")
                with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30) as server:
                    server.starttls()
                    server.login(self._email, self._auth)
                    to_addrs = [to] + ([cc] if cc else [])
                    server.sendmail(self._email, to_addrs, msg.as_string())
            
            print("  - [SMTP] 邮件发送成功！")
            return json.dumps({"status": "sent", "to": to, "subject": subject}, ensure_ascii=False)
        
        except Exception as e:
            print(f"  - [SMTP] 邮件发送失败，准备重试... 错误: {e}")
            raise e


