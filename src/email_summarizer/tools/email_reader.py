#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EmailReaderTool: 使用 IMAP 读取新邮件，基于 Message-ID 去重并返回内容列表 (修正版)
"""
import os
import json
import email
from typing import Optional, Type, List, Dict
from email.header import decode_header, make_header

import html2text
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.tools import BaseTool
from imapclient import IMAPClient, exceptions

load_dotenv()

# --- 配置常量 ---
CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(CORE_DIR)
STATE_PATH = os.path.join(BASE_DIR, "state", "processed_emails.json")

os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

EMAIL_CONFIGS = json.loads(os.getenv("EMAIL_CONFIGS", "{}") or "{}")
EMAIL_SERVICE = os.getenv("EMAIL_USE", "QQ").upper()


class EmailReaderInput(BaseModel):
    max_count: int = Field(20, description="读取的新邮件最大数量，1-50")
    folder: str = Field("INBOX", description="读取的文件夹，默认 INBOX")
    use_unseen: bool = Field(True, description="是否仅读取未读邮件")


class EmailReaderTool(BaseTool):
    name: str = "email_reader_tool"
    description: str = "使用 IMAP 读取邮箱中的新邮件，按 Message-ID 去重，返回结构化内容列表"
    args_schema: Type[BaseModel] = EmailReaderInput

    def __init__(self, **data):
        super().__init__(**data)
        if EMAIL_SERVICE not in EMAIL_CONFIGS:
            raise ValueError(f"错误: 在 .env 中未找到邮箱服务 '{EMAIL_SERVICE}' 的配置")
        self._cfg = EMAIL_CONFIGS[EMAIL_SERVICE]
        self._email = self._cfg["username"]
        self._auth = self._cfg["password"]
        self._imap_host = self._cfg["imap_host"]
        self._h2t = html2text.HTML2Text()
        self._h2t.ignore_links = True
        self._h2t.ignore_images = True
        self._h2t.body_width = 0

    @staticmethod
    def _load_state() -> Dict[str, List[str]]:
        if not os.path.exists(STATE_PATH):
            return {"processed_ids": []}
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"processed_ids": []}

    @staticmethod
    def _save_state(state: Dict[str, List[str]]):
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _decode_header(value: Optional[bytes]) -> str:
        """【优化】使用 make_header 正确解码邮件头部(bytes -> str)"""
        if not value:
            return ""
        try:
            # imapclient 返回的 envelope 字段是 bytes
            return str(make_header(decode_header(value.decode('utf-8', 'ignore'))))
        except Exception:
            try:
                return value.decode('utf-8', 'ignore')
            except Exception:
                return str(value)

    def _run(self, max_count: int = 20, folder: str = "INBOX", use_unseen: bool = True) -> str:
        max_count = max(1, min(50, int(max_count)))
        state = self._load_state()
        processed_ids = set(state.get("processed_ids", []))
        results: List[Dict] = []
        new_ids: List[str] = []

        try:
            print(f"🔗 [1/5] 正在连接到 {self._imap_host}...")
            # 【修正】为慢速网络连接增加超时时间
            with IMAPClient(self._imap_host, ssl=True, timeout=30) as client:
                print(f"🔐 [2/5] 正在登录邮箱 {self._email}...")
                client.login(self._email, self._auth)
                
                try:
                    client.id_({"name": "email-summarizer", "version": "0.3"})
                except exceptions.IMAPClientError:
                    pass

                print(f"📁 [3/5] 正在选择文件夹 '{folder}'...")
                client.select_folder(folder, readonly=True)

                search_criteria = ["UNSEEN"] if use_unseen else ["ALL"]
                print(f"🔍 [4/5] 正在搜索'{'未读' if use_unseen else '所有'}'邮件...")
                uids = client.search(search_criteria)
                
                if not uids:
                    print("✅ 没有找到新邮件。")
                    return json.dumps({"emails": []}, ensure_ascii=False)

                latest_uids = sorted(uids, reverse=True)[:max_count]
                print(f"📧 找到 {len(uids)} 封，准备处理最新的 {len(latest_uids)} 封。")

                print(f"📥 [5/5] 正在高效获取邮件内容（无附件）...")
                
                # 【核心优化】不再获取RFC822，只获取需要的部分
                fetch_data = client.fetch(latest_uids, [b'ENVELOPE', b'BODY[TEXT]'])
                
                for i, uid in enumerate(latest_uids, 1):
                    print(f"  - 正在处理第 {i}/{len(latest_uids)} 封 (UID: {uid})...")
                    data = fetch_data.get(uid)
                    if not data or b'ENVELOPE' not in data:
                        continue
                    
                    envelope = data[b'ENVELOPE']
                    mid = self._decode_header(envelope.message_id)
                    uniq_id = mid if mid else f"uid-{uid}"

                    if uniq_id in processed_ids:
                        print(f"    - 跳过已处理邮件 (ID: {uniq_id})")
                        continue

                    # 从 ENVELOPE 中解析发件人
                    sender_info = envelope.from_[0] if envelope.from_ else None
                    if sender_info:
                        sender_name = self._decode_header(sender_info.name)
                        sender_email = f"{sender_info.mailbox.decode('utf-8', 'ignore')}@{sender_info.host.decode('utf-8', 'ignore')}"
                        sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email
                    else:
                        sender = "未知发件人"

                    # 从 BODY[TEXT] 中获取正文，并转换为纯文本
                    body_bytes = data.get(b'BODY[TEXT]', b'')
                    body_str = body_bytes.decode('utf-8', 'ignore')
                    content = self._h2t.handle(body_str).strip()

                    results.append({
                        "id": uniq_id,
                        "from": sender,
                        "subject": self._decode_header(envelope.subject) or "(无主题)",
                        "date": str(envelope.date),
                        "content": content
                    })
                    new_ids.append(uniq_id)
                
                if new_ids:
                    processed_ids.update(new_ids)
                    self._save_state({"processed_ids": list(processed_ids)})
                    print(f"💾 已更新状态，新增 {len(new_ids)} 个已处理ID。")

                print(f"✅ 流程完成，成功处理 {len(results)} 封新邮件。")
                return json.dumps({"emails": results}, ensure_ascii=False)
                
        except exceptions.LoginError:
            error_msg = "IMAP登录失败: 请检查邮箱用户名或授权码是否正确。"
            print(f"❌ {error_msg}")
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        except exceptions.IMAPClientError as e:
            error_msg = f"IMAP操作失败: {str(e)}"
            print(f"❌ {error_msg}")
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        except Exception as e:
            error_msg = f"邮件读取过程中发生未知错误: {str(e)}"
            print(f"❌ {error_msg}")
            return json.dumps({"error": error_msg}, ensure_ascii=False)

