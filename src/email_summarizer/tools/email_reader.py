#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EmailReaderTool: 使用 IMAP 读取新邮件，兼容 Gmail 和 163，并支持智能附件下载
"""
import os
import json
import email
import re
from typing import Optional, Type, List, Dict, Any
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
ATTACHMENT_DIR = os.path.join(BASE_DIR, "attachments")

os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
os.makedirs(ATTACHMENT_DIR, exist_ok=True)

EMAIL_CONFIGS = json.loads(os.getenv("EMAIL_CONFIGS", "{}") or "{}")
EMAIL_SERVICE = os.getenv("EMAIL_USE", "GMAIL").upper() # 默认为 GMAIL

# --- 附件过滤配置 ---
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx'}
BLOCKED_EXTENSIONS = {'.zip', '.rar', '.7z', '.exe', '.sh', '.bat'}
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024 # 5MB


class EmailReaderInput(BaseModel):
    max_count: int = Field(20, description="读取的新邮件最大数量，1-50")
    folder: str = Field("INBOX", description="读取的文件夹，默认 INBOX")
    use_unseen: bool = Field(True, description="是否仅读取未读邮件")


class EmailReaderTool(BaseTool):
    name: str = "email_reader_tool"
    description: str = "使用 IMAP 读取邮箱中的新邮件，按 Message-ID 去重，智能下载附件，并返回结构化内容列表"
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
        if not value: return ""
        try:
            return str(make_header(decode_header(value.decode('utf-8', 'ignore'))))
        except Exception:
            return value.decode('utf-8', 'ignore') if isinstance(value, bytes) else str(value)

    def _get_parts_to_fetch(self, body_struct: Any) -> Dict[str, List[str]]:
        parts_to_fetch = {"body": [], "attachments": []}
        
        def recurse_parts(part_struct: Any, part_id: str):
            # 在imapclient 3.x中，body_struct是一个tuple或list结构
            if not isinstance(part_struct, (tuple, list)) or len(part_struct) < 7:
                return

            # BODYSTRUCTURE格式: (type, subtype, params, id, description, encoding, size, ...)
            try:
                part_type = part_struct[0].decode('utf-8', 'ignore') if isinstance(part_struct[0], bytes) else str(part_struct[0])
                part_subtype = part_struct[1].decode('utf-8', 'ignore') if isinstance(part_struct[1], bytes) else str(part_struct[1])
                part_size = part_struct[6] if len(part_struct) > 6 else 0
                
                # 检查是否是multipart
                if part_type.lower() == 'multipart':
                    # multipart的结构不同，需要递归处理子部分
                    for i, sub_part in enumerate(part_struct[:-1]):  # 最后一个元素是subtype
                        if isinstance(sub_part, (tuple, list)):
                            recurse_parts(sub_part, f"{part_id}.{i+1}" if part_id else str(i+1))
                    return
                
                # 检查disposition (通常在索引7或8)
                disposition = ""
                disposition_params = {}
                if len(part_struct) > 8 and part_struct[8]:
                    if isinstance(part_struct[8], (tuple, list)) and len(part_struct[8]) >= 2:
                        disposition = part_struct[8][0].decode('utf-8', 'ignore').lower() if part_struct[8][0] else ""
                        if len(part_struct[8]) > 1 and part_struct[8][1]:
                            # disposition参数是一个列表，格式为[key1, value1, key2, value2, ...]
                            disp_params = part_struct[8][1]
                            if isinstance(disp_params, (tuple, list)):
                                for i in range(0, len(disp_params), 2):
                                    if i + 1 < len(disp_params):
                                        key = disp_params[i].decode('utf-8', 'ignore').lower() if isinstance(disp_params[i], bytes) else str(disp_params[i]).lower()
                                        value = disp_params[i+1]
                                        disposition_params[key] = value
                
                if 'attachment' in disposition:
                    filename = ""
                    if 'filename' in disposition_params:
                        filename_bytes = disposition_params['filename']
                        filename = self._decode_header(filename_bytes) if filename_bytes else ""
                    
                    ext = os.path.splitext(filename)[1].lower()
                    size = part_size or 0

                    if ext in ALLOWED_EXTENSIONS and ext not in BLOCKED_EXTENSIONS and size <= MAX_ATTACHMENT_SIZE:
                        parts_to_fetch["attachments"].append(part_id)
                        print(f"      - 发现符合条件的附件: {filename} ({size / 1024:.1f} KB)，将下载。")
                    else:
                        print(f"      - 跳过附件: {filename} (类型: {ext}, 大小: {size / 1024:.1f} KB)")
                    return

                # 检查是否是文本内容
                mime_type = f"{part_type}/{part_subtype}"
                if mime_type in ['text/plain', 'text/html']:
                    parts_to_fetch["body"].append(part_id)
                    
            except (IndexError, AttributeError, UnicodeDecodeError) as e:
                print(f"      - 解析body structure时出错: {e}")
                return

        # 处理主体结构
        if isinstance(body_struct, (tuple, list)) and len(body_struct) > 0:
            # 检查是否是multipart
            if (isinstance(body_struct[0], (tuple, list)) or 
                (len(body_struct) > 1 and isinstance(body_struct[0], bytes) and 
                 body_struct[0].decode('utf-8', 'ignore').lower() == 'multipart')):
                
                if isinstance(body_struct[0], (tuple, list)):
                    # 这是一个multipart消息，第一个元素就是子部分
                    for i, part in enumerate(body_struct[:-1]):  # 最后一个元素通常是subtype
                        if isinstance(part, (tuple, list)):
                            recurse_parts(part, str(i+1))
                else:
                    # 这是一个multipart，但结构稍有不同
                    for i, part in enumerate(body_struct[:-2]):  # 去掉最后的subtype和其他元数据
                        if isinstance(part, (tuple, list)):
                            recurse_parts(part, str(i+1))
            else:
                # 单一部分消息
                recurse_parts(body_struct, '1')

        return parts_to_fetch

    def _run(self, max_count: int = 20, folder: str = "INBOX", use_unseen: bool = True) -> str:
        max_count = max(1, min(50, int(max_count)))
        state = self._load_state()
        processed_ids = set(state.get("processed_ids", []))
        results: List[Dict] = []
        new_ids: List[str] = []

        try:
            print(f"🔗 [1/4] 正在连接到 {self._imap_host}...")
            with IMAPClient(self._imap_host, ssl=True, timeout=30) as client:
                print(f"🔐 [2/4] 正在登录邮箱 {self._email}...")
                client.login(self._email, self._auth)

                # --- 【兼容性改造】---
                # 仅当连接到 163 服务器时，才发送特殊的 ID 握手命令
                if "163.com" in self._imap_host.lower():
                    print("  - 检测到163邮箱，正在发送ID握手...")
                    try:
                        client.id_({"name": "email-summarizer", "version": "0.5"})
                    except exceptions.IMAPClientError:
                        print("  - 警告: 163邮箱ID握手失败，但继续尝试。")
                        pass

                print(f"📁 [3/4] 正在选择文件夹 '{folder}'...")
                client.select_folder(folder, readonly=True)

                search_criteria = ["UNSEEN"] if use_unseen else ["ALL"]
                print(f"🔍 [4/4] 正在搜索邮件...")
                uids = client.search(search_criteria)
                
                if not uids:
                    print("✅ 没有找到新邮件。")
                    return json.dumps({"emails": []}, ensure_ascii=False)

                latest_uids = sorted(uids, reverse=True)[:max_count]
                print(f"📧 找到 {len(uids)} 封，准备检查最新的 {len(latest_uids)} 封。")

                print("📥 正在分步获取邮件内容...")
                envelopes_data = client.fetch(latest_uids, [b'ENVELOPE'])
                bodystructures_data = client.fetch(latest_uids, [b'BODYSTRUCTURE'])

                for i, uid in enumerate(latest_uids, 1):
                    print(f"\n--- 正在处理第 {i}/{len(latest_uids)} 封 (UID: {uid}) ---")
                    envelope = envelopes_data.get(uid, {}).get(b'ENVELOPE')
                    if not envelope: continue
                    
                    mid = self._decode_header(envelope.message_id)
                    uniq_id = mid if mid else f"uid-{uid}"

                    if uniq_id in processed_ids:
                        print(f"  - 跳过已处理邮件 (ID: {uniq_id})")
                        continue
                    
                    bodystructure = bodystructures_data.get(uid, {}).get(b'BODYSTRUCTURE')
                    if not bodystructure: continue
                    
                    parts_to_fetch = self._get_parts_to_fetch(bodystructure)
                    fetch_query = [f'BODY[{p}]'.encode() for p in (parts_to_fetch["body"] + parts_to_fetch["attachments"])]
                    
                    plain_text, html_text, saved_attachments = "", "", []
                    
                    if fetch_query:
                        print(f"  - 准备下载 {len(fetch_query)} 个邮件部分...")
                        parts_data = client.fetch([uid], fetch_query).get(uid, {})
                        
                        for part_id in parts_to_fetch["body"]:
                            part_content = parts_data.get(f'BODY[{part_id}]'.encode(), b'').decode('utf-8', 'ignore')
                            if '<html' in part_content.lower(): html_text += part_content
                            else: plain_text += part_content

                        for part_id in parts_to_fetch["attachments"]:
                            attachment_bytes = parts_data.get(f'BODY[{part_id}]'.encode())
                            part_info = bodystructure
                            try:
                                for p_index in part_id.split('.'):
                                    part_info = part_info.parts[int(p_index) - 1]
                            except (IndexError, AttributeError): continue
                            
                            filename_bytes = part_info.disposition_params.get(b'filename')
                            filename = self._decode_header(filename_bytes) if filename_bytes else f"attachment_{uid}_{part_id}.dat"
                            safe_filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
                            filepath = os.path.join(ATTACHMENT_DIR, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_filename}")
                            
                            if attachment_bytes:
                                with open(filepath, 'wb') as f: f.write(attachment_bytes)
                                saved_attachments.append(filepath)
                                print(f"      - ✅ 附件已保存到: {filepath}")

                    content = plain_text.strip() or self._h2t.handle(html_text).strip()
                    sender_info = envelope.from_[0] if envelope.from_ else None
                    sender = self._decode_header(sender_info.name) if sender_info and sender_info.name else "未知发件人"

                    results.append({
                        "id": uniq_id,
                        "from": sender,
                        "subject": self._decode_header(envelope.subject) or "(无主题)",
                        "date": str(envelope.date),
                        "content": content,
                        "attachments": saved_attachments
                    })
                    new_ids.append(uniq_id)
                
                if new_ids:
                    processed_ids.update(new_ids)
                    self._save_state({"processed_ids": list(processed_ids)})
                    print(f"\n💾 已更新状态，新增 {len(new_ids)} 个已处理ID。")

                print(f"\n✅ 流程完成，成功处理 {len(results)} 封新邮件。")
                return json.dumps({"emails": results}, ensure_ascii=False)
                
        except exceptions.LoginError:
            error_msg = "IMAP登录失败: 请检查邮箱用户名或密码/授权码是否正确。"
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        except Exception as e:
            error_msg = f"邮件读取过程中发生未知错误: {type(e).__name__} - {e}"
            return json.dumps({"error": error_msg}, ensure_ascii=False)