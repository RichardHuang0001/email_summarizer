#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
email_reader.py
EmailReaderTool: 使用 IMAP 读取新邮件，兼容 Gmail (多分类) 和 163，并支持智能附件下载
"""
import os
import json
import email
import re
from typing import Optional, Type, List, Dict, Any
from email.header import decode_header, make_header
from datetime import datetime

import html2text
from pydantic import BaseModel, Field
from langchain.tools import BaseTool
from imapclient import IMAPClient, exceptions

from ..utils.config import get_email_service_config
from ..utils.config_loader import get_config, get_project_root
from ..utils.console import Console

# --- 从统一配置加载 ---
_cfg = get_config()
_net_cfg = _cfg.get('network', {})
_att_cfg = _cfg.get('attachment', {})
_adv_cfg = _cfg.get('advanced', {})
_parse_cfg = _cfg.get('parsing', {})

PROJECT_ROOT = get_project_root()
STATE_PATH = os.path.join(PROJECT_ROOT, _adv_cfg.get('state_file', 'state/processed_emails.json'))
ATTACHMENT_DIR = os.path.join(PROJECT_ROOT, _adv_cfg.get('attachment_dir', 'attachments'))

os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
os.makedirs(ATTACHMENT_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = set(_att_cfg.get('allowed_extensions', ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx']))
BLOCKED_EXTENSIONS = set(_att_cfg.get('blocked_extensions', ['.zip', '.rar', '.7z', '.exe', '.sh', '.bat']))
MAX_ATTACHMENT_SIZE = _att_cfg.get('max_size_mb', 5) * 1024 * 1024
IMAP_TIMEOUT = _net_cfg.get('imap_timeout', 30)

class EmailReaderInput(BaseModel):
    max_count: int = Field(20, description="每个文件夹读取的新邮件最大数量，1-50")
    folder: str = Field("INBOX", description="要读取的 IMAP 文件夹。Gmail 默认会自动检测 [Gmail]/All Mail 和垃圾邮件文件夹")
    use_unseen: bool = Field(True, description="是否仅读取未读邮件")


class EmailReaderTool(BaseTool):
    name: str = "email_reader_tool"
    description: str = "使用 IMAP 读取邮箱中的新邮件，按 Message-ID 去重，智能下载附件，并返回结构化内容列表"
    args_schema: Type[BaseModel] = EmailReaderInput

    def __init__(self, **data):
        super().__init__(**data)
        cfg = get_email_service_config()
        self._email = cfg["username"]
        self._auth = cfg["password"]
        self._imap_host = cfg["imap_host"]
        self._service = (cfg.get("service_name") or "GMAIL").upper()
        self._h2t = html2text.HTML2Text()
        self._h2t.ignore_links = _parse_cfg.get('ignore_links', True)
        self._h2t.ignore_images = _parse_cfg.get('ignore_images', True)
        self._h2t.body_width = _parse_cfg.get('body_width', 0)

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
    def decode_folder_name(folder_bytes: bytes) -> str:
        try:
            return folder_bytes.decode('imap4-utf-7')
        except Exception:
            try:
                return folder_bytes.decode('utf-8', 'ignore')
            except Exception:
                return str(folder_bytes)

    @staticmethod
    def _resolve_gmail_folders(available_folders: dict) -> list:
        """
        Auto-detect Gmail All Mail and Spam folders regardless of account language.
        Uses [Gmail]/All Mail (所有邮件) to cover inbox + archived emails across all categories.
        Returns list of decoded folder names.
        """
        all_mail_patterns = [
            '[gmail]/all mail', '[gmail]/所有邮件',
            '[google mail]/all mail', '[google mail]/所有邮件',
        ]
        spam_patterns = [
            '[gmail]/spam', '[gmail]/垃圾邮件',
            '[google mail]/spam', '[google mail]/垃圾邮件',
        ]

        folder_lower = {name.lower(): name for name in available_folders}
        resolved = []

        for pattern in all_mail_patterns:
            if pattern in folder_lower:
                resolved.append(folder_lower[pattern])
                break

        for pattern in spam_patterns:
            if pattern in folder_lower:
                resolved.append(folder_lower[pattern])
                break

        if not resolved:
            resolved.append('INBOX')

        return resolved

    @staticmethod
    def _decode_header(value: Optional[bytes]) -> str:
        if not value: return ""
        try:
            if isinstance(value, bytes): value_str = value.decode('utf-8', 'ignore')
            else: value_str = str(value)
            header = make_header(decode_header(value_str))
            return str(header)
        except Exception:
            return value.decode('utf-8', 'ignore') if isinstance(value, bytes) else str(value)

    def _get_parts_to_fetch(self, body_struct: Any) -> Dict[str, List[Dict]]:
        parts_to_fetch = {"body": [], "attachments": []}

        def recurse_parts(part_struct: Any, part_id: str):
            is_obj = hasattr(part_struct, 'type')

            try:
                if is_obj:
                    part_type = getattr(part_struct, 'type', b'').decode('utf-8', 'ignore').lower()
                    part_subtype = getattr(part_struct, 'subtype', b'').decode('utf-8', 'ignore').lower()
                    part_size = getattr(part_struct, 'size', 0) or 0
                    disposition_tuple = getattr(part_struct, 'disposition', None)
                    disposition = disposition_tuple[0].decode('utf-8', 'ignore').lower() if disposition_tuple else ""
                    disp_params_bytes = disposition_tuple[1] if disposition_tuple and len(disposition_tuple) > 1 else {}
                    disp_params_bytes = {k.encode() if isinstance(k, str) else k: v for k, v in disp_params_bytes.items()}

                elif isinstance(part_struct, (tuple, list)) and len(part_struct) >= 7:
                    part_type = part_struct[0].decode('utf-8', 'ignore').lower() if isinstance(part_struct[0], bytes) else str(part_struct[0]).lower()
                    part_subtype = part_struct[1].decode('utf-8', 'ignore').lower() if isinstance(part_struct[1], bytes) else str(part_struct[1]).lower()
                    part_size = part_struct[6] if isinstance(part_struct[6], int) else 0
                    disposition = ""
                    disp_params_bytes = {}
                    if len(part_struct) > 8 and part_struct[8] and isinstance(part_struct[8], (tuple, list)) and len(part_struct[8]) >= 1:
                        disposition = part_struct[8][0].decode('utf-8', 'ignore').lower() if part_struct[8][0] else ""
                        if len(part_struct[8]) > 1 and part_struct[8][1] and isinstance(part_struct[8][1], (tuple, list)):
                            v2_params = part_struct[8][1]
                            disp_params_bytes = {v2_params[i]: v2_params[i+1] for i in range(0, len(v2_params), 2)}
                else:
                    return

                sub_parts = getattr(part_struct, 'parts', None) if is_obj else (part_struct[0] if part_type == 'multipart' and isinstance(part_struct[0], (list, tuple)) else None)
                if part_type == 'multipart' and sub_parts:
                    for i, sub_part in enumerate(sub_parts):
                         recurse_parts(sub_part, f"{part_id}.{i+1}" if part_id else str(i+1))
                    return

                filename_bytes = disp_params_bytes.get(b'filename') or disp_params_bytes.get(b'filename*')
                filename = self._decode_header(filename_bytes) if filename_bytes else ""
                is_attachment = bool(filename) or 'attachment' in disposition

                if is_attachment:
                    ext = os.path.splitext(filename)[1].lower() if filename else ""
                    size = part_size or 0

                    if ext in ALLOWED_EXTENSIONS and ext not in BLOCKED_EXTENSIONS and size <= MAX_ATTACHMENT_SIZE:
                        parts_to_fetch["attachments"].append({'id': part_id, 'filename': filename, 'size': size})
                    return

                mime_type = f"{part_type}/{part_subtype}"
                if mime_type in ['text/plain', 'text/html']:
                    parts_to_fetch["body"].append(part_id)

            except Exception:
                pass

        if hasattr(body_struct, 'type'):
            recurse_parts(body_struct, '1' if not getattr(body_struct, 'parts', None) else "")
        elif isinstance(body_struct, (tuple, list)):
             is_multi = isinstance(body_struct[0], (list, tuple)) or \
                        (len(body_struct) > 1 and isinstance(body_struct[0], bytes) and \
                         body_struct[0].decode('utf-8', 'ignore').lower() == 'multipart')
             recurse_parts(body_struct, "" if is_multi else "1")
        else:
            Console.step_warn("Unexpected BODYSTRUCTURE format")

        for part_list_key in ["body", "attachments"]:
            corrected_list = []
            for item in parts_to_fetch[part_list_key]:
                if isinstance(item, str):
                     corrected_list.append(item.lstrip('.'))
                elif isinstance(item, dict) and 'id' in item:
                    item['id'] = item['id'].lstrip('.')
                    corrected_list.append(item)
            parts_to_fetch[part_list_key] = corrected_list

        return parts_to_fetch

    @staticmethod
    def _fetch_with_fallback(client: IMAPClient, uids: List[int], data_items: List[bytes], context: str) -> Dict[int, Dict[bytes, Any]]:
        if not uids or not data_items:
            return {}

        try:
            return client.fetch(uids, data_items)
        except AssertionError as e:
            msg = str(e)
            is_marked_section_error = "unknown status keyword" in msg and "marked section" in msg
            if not is_marked_section_error:
                raise

            Console.step_warn(f"IMAP 兼容性问题 ({context})，降级为逐封拉取")
            recovered: Dict[int, Dict[bytes, Any]] = {}

            for uid in uids:
                try:
                    single = client.fetch([uid], data_items)
                    if uid in single:
                        recovered[uid] = single[uid]
                except AssertionError as single_e:
                    single_msg = str(single_e)
                    if "unknown status keyword" in single_msg and "marked section" in single_msg:
                        Console.step_warn(f"跳过无法解析的邮件 UID={uid} ({context})")
                        continue
                    raise

            return recovered

    def _run(self, max_count: int = 20, folder: str = "INBOX", use_unseen: bool = True) -> str:
        max_count = max(1, min(50, int(max_count)))
        state = self._load_state()
        processed_ids = set(state.get("processed_ids", []))
        results: List[Dict] = []
        new_ids: List[str] = []

        folders_to_read = []
        is_gmail_default = self._service == "GMAIL" and folder == "INBOX"
        if not is_gmail_default:
            folders_to_read = [folder]
            Console.step_info(f"读取文件夹: {folder}")

        try:
            Console.step_info(f"连接 IMAP 服务器 {self._imap_host}...")
            with IMAPClient(self._imap_host, ssl=True, timeout=IMAP_TIMEOUT) as client:
                Console.step_info(f"登录邮箱 {self._email}...")
                client.login(self._email, self._auth)
                Console.step_ok("登录成功")

                if "163.com" in self._imap_host.lower():
                    Console.step_info("163 邮箱 - 发送 ID 握手...")
                    try: client.id_({"name": "email-summarizer", "version": "0.6"})
                    except exceptions.IMAPClientError: pass

                processed_uids_in_session = set()
                all_available_folders_raw = client.list_folders()
                all_available_folders = {self.decode_folder_name(f[2]): f[2] for f in all_available_folders_raw}

                if is_gmail_default:
                    folders_to_read = self._resolve_gmail_folders(all_available_folders)
                    Console.step_info(f"Gmail 自动检测文件夹: {folders_to_read}")

                for folder_name_to_try in folders_to_read:
                    actual_folder_name_decoded = next((name for name in all_available_folders if name.lower() == folder_name_to_try.lower()), None)

                    if not actual_folder_name_decoded:
                        if is_gmail_default and folder_name_to_try != "INBOX":
                             Console.step_info(f"文件夹 '{folder_name_to_try}' 不存在，跳过")
                        elif not is_gmail_default:
                             raise exceptions.IMAPClientError(f"指定的文件夹 '{folder_name_to_try}' 不存在。")
                        continue

                    actual_folder_name_bytes = all_available_folders[actual_folder_name_decoded]

                    try:
                        Console.step_info(f"选择文件夹 '{actual_folder_name_decoded}'")
                        client.select_folder(actual_folder_name_bytes, readonly=True)

                        search_criteria = ["UNSEEN"] if use_unseen else ["ALL"]
                        search_label = "未读" if use_unseen else "所有"
                        Console.step_info(f"搜索 {search_label} 邮件...")
                        uids = client.search(search_criteria)

                        if not uids:
                            Console.step_ok(f"'{actual_folder_name_decoded}' 中没有新邮件")
                            continue

                        latest_uids_in_folder = sorted(uids, reverse=True)[:max_count]

                        uids_to_process = [uid for uid in latest_uids_in_folder if uid not in processed_uids_in_session]
                        if not uids_to_process:
                            Console.step_info(f"'{actual_folder_name_decoded}' 中邮件已在其他文件夹处理过")
                            continue

                        Console.step_info(f"获取 {len(uids_to_process)} 封邮件内容...")

                        envelopes_data = self._fetch_with_fallback(client, uids_to_process, [b'ENVELOPE'], f"{actual_folder_name_decoded}/ENVELOPE")
                        bodystructures_data = self._fetch_with_fallback(client, uids_to_process, [b'BODYSTRUCTURE'], f"{actual_folder_name_decoded}/BODYSTRUCTURE")

                        for i, uid in enumerate(uids_to_process, 1):
                            envelope = envelopes_data.get(uid, {}).get(b'ENVELOPE')
                            bodystructure_raw = bodystructures_data.get(uid, {}).get(b'BODYSTRUCTURE')

                            if not envelope or not bodystructure_raw:
                                Console.step_warn("无法获取邮件元数据，跳过")
                                continue

                            mid = self._decode_header(envelope.message_id)
                            uniq_id = mid if mid else f"uid-{uid}-{actual_folder_name_decoded}"

                            if uniq_id in processed_ids:
                                continue

                            parts_to_fetch = self._get_parts_to_fetch(bodystructure_raw)
                            fetch_query = [f'BODY[{p}]'.encode() for p in parts_to_fetch["body"]]
                            fetch_query.extend([f'BODY[{att["id"]}]'.encode() for att in parts_to_fetch["attachments"]])

                            plain_text, html_text, saved_attachments = "", "", []

                            if fetch_query:
                                parts_data = self._fetch_with_fallback(client, [uid], fetch_query, f"{actual_folder_name_decoded}/BODY uid={uid}").get(uid, {})

                                for part_id in parts_to_fetch["body"]:
                                    part_content = parts_data.get(f'BODY[{part_id}]'.encode(), b'').decode('utf-8', 'ignore')
                                    if '<html' in part_content.lower(): html_text += part_content
                                    else: plain_text += part_content

                                for att_info in parts_to_fetch["attachments"]:
                                    part_id = att_info['id']
                                    filename = att_info['filename']
                                    attachment_bytes = parts_data.get(f'BODY[{part_id}]'.encode())

                                    safe_filename = re.sub(r'[\\/*?:"<>|]', "_", filename) if filename else f"attachment_{uid}_{part_id}.dat"
                                    filepath = os.path.join(ATTACHMENT_DIR, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_filename}")

                                    if attachment_bytes:
                                        with open(filepath, 'wb') as f: f.write(attachment_bytes)
                                        saved_attachments.append(filepath)

                            content = plain_text.strip() or self._safe_html_to_text(html_text)
                            sender_info = envelope.from_[0] if envelope.from_ else None
                            sender = "未知发件人"
                            if sender_info and sender_info.mailbox and sender_info.host:
                                sender_name = self._decode_header(sender_info.name)
                                sender_email = f"{sender_info.mailbox.decode('utf-8', 'ignore')}@{sender_info.host.decode('utf-8', 'ignore')}"
                                sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email

                            results.append({
                                "id": uniq_id,
                                "from": sender,
                                "subject": self._decode_header(envelope.subject) or "(无主题)",
                                "date": str(envelope.date),
                                "content": content,
                                "attachments": saved_attachments,
                                "folder": actual_folder_name_decoded
                            })
                            new_ids.append(uniq_id)
                            processed_uids_in_session.add(uid)

                    except exceptions.IMAPClientError as e:
                        Console.step_warn(f"处理文件夹 '{actual_folder_name_decoded}' 时出错: {e}")
                        continue

                if new_ids:
                    processed_ids.update(new_ids)
                    self._save_state({"processed_ids": list(processed_ids)})
                    Console.step_info(f"状态已更新，新增 {len(new_ids)} 条记录")

                Console.step_ok(f"流程完成，共处理 {len(results)} 封新邮件")
                return json.dumps({"emails": results}, ensure_ascii=False)

        except exceptions.LoginError:
            error_msg = "IMAP 登录失败 - 请检查邮箱用户名或密码/授权码"
            Console.step_fail(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        except Exception as e:
            error_msg = f"邮件读取错误: {type(e).__name__} - {e}"
            Console.step_fail(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)

    def _safe_html_to_text(self, html_text: str) -> str:
        if not html_text:
            return ""

        try:
            return self._h2t.handle(html_text).strip()
        except AssertionError:
            cleaned = re.sub(r"<!--\[if.*?<!\[endif\]-->", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
            cleaned = re.sub(r"<!\[[^\]]*\]>", " ", cleaned)
            try:
                return self._h2t.handle(cleaned).strip()
            except Exception:
                plain_fallback = re.sub(r"<[^>]+>", " ", cleaned)
                return re.sub(r"\s+", " ", plain_fallback).strip()
