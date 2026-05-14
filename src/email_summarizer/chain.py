#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain.py
LCEL 编排流程
- 读取新邮件 -> 并行总结(生成HTML卡片) -> 组装完整HTML -> 保存归档 -> 发送邮件
"""
import os
import json
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
import webbrowser
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompts import get_email_summarizer_prompt
from .tools.email_reader import EmailReaderTool
from .tools.email_sender import EmailSenderTool
from .utils.email_utils import extract_email_contents
from .utils.html_utils import compose_final_html_body
from .utils.error_handler import handle_llm_error
from .utils.console import Console

load_dotenv()

MAX_LLM_EMAILS = 20


def _read_emails(limit: int, use_unseen: bool) -> List[Dict]:
    reader = EmailReaderTool()
    reader_result = reader.invoke({"max_count": limit, "folder": "INBOX", "use_unseen": use_unseen})
    emails = extract_email_contents(reader_result)

    if not emails:
        Console.ok("没有新的待处理邮件")
        return []

    Console.count_badge(len(emails), "封新邮件")
    return emails


def _setup_llm_chain():
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    llm = ChatOpenAI(model=model_name, temperature=0, base_url=base_url) if base_url else ChatOpenAI(model=model_name, temperature=0)
    summarizer_prompt = get_email_summarizer_prompt()
    return summarizer_prompt | llm | StrOutputParser()


def _process_emails_parallel(emails: List[Dict]) -> List[str]:
    summarizer_chain = _setup_llm_chain()
    contents = [{"email_subject": e.get("subject", "(No Subject)"), "email_content": e["content"]} for e in emails]

    max_concurrency = min(8, len(contents)) or 1
    Console.step_info(f"并行处理 {len(contents)} 封邮件 (最多 {max_concurrency} 个并发请求)")

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_to_content = {
            executor.submit(summarizer_chain.invoke, content): i
            for i, content in enumerate(contents)
        }

        summary_htmls = [None] * len(contents)
        completed_count = 0
        error_count = 0
        should_continue = True
        last_error_msg = ""
        total = len(contents)

        for future in as_completed(future_to_content, timeout=60):
            if not should_continue:
                for remaining_future in future_to_content:
                    if not remaining_future.done():
                        remaining_future.cancel()
                break

            try:
                result = future.result()
                index = future_to_content[future]
                summary_htmls[index] = result
                completed_count += 1

                elapsed = time.time() - start_time
                Console.progress_bar(completed_count, total, elapsed, prefix="处理中")

            except Exception as e:
                error_count += 1
                error_msg, should_continue = handle_llm_error(e)

                if error_msg != last_error_msg:
                    Console.progress_clear()
                    Console.inline_error(error_msg)
                    last_error_msg = error_msg

                if not should_continue:
                    Console.progress_clear()
                    Console.fail("检测到严重错误，已停止剩余任务")
                    break

    elapsed = time.time() - start_time
    success_count = len([s for s in summary_htmls if s])

    if success_count > 0:
        Console.progress_done(success_count, total, elapsed)
        if error_count > 0:
            Console.step_warn(f"{error_count} 封邮件总结失败")
    else:
        Console.progress_clear()
        Console.fail(f"所有 {total} 封邮件总结均失败")
        if error_count > 0:
            Console.step_info("建议检查 LLM 配置和网络连接")

    return [s for s in summary_htmls if s]


def _save_archive_and_get_path(html_content: str) -> Optional[str]:
    if not html_content:
        Console.warn("没有内容可供归档")
        return None

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(os.path.dirname(current_dir))
        archive_dir = os.path.join(base_dir, "archive")
        os.makedirs(archive_dir, exist_ok=True)

        filename = f"archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.html"
        archive_path = os.path.join(archive_dir, filename)

        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        Console.step_ok(f"归档已保存: {archive_path}")
        return archive_path
    except Exception as e:
        Console.step_fail(f"归档保存失败: {e}")
        return None


def _send_email(target_email: str, subject: str, final_html_body: str, archive_path: Optional[str], send_attachment: bool) -> Dict:
    try:
        sender = EmailSenderTool()
        attachment_to_send = archive_path if send_attachment else None

        send_result_str = sender.invoke({
            "to": target_email,
            "subject": subject,
            "body": final_html_body,
            "is_html": True,
            "attachment_path": attachment_to_send
        })
        result = json.loads(send_result_str)

        if "error" in result:
            Console.step_fail(f"邮件发送失败: {result['error']}")
            return {"status": "error", "error": result["error"]}
        else:
            Console.step_ok("邮件发送成功")
            return result

    except Exception as e:
        error_msg = f"邮件发送异常: {str(e)}"
        Console.step_fail(error_msg)
        return {"status": "error", "error": error_msg}


def mark_emails_as_unprocessed(emails: List[Dict]):
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(os.path.dirname(current_dir))
        state_file = os.path.join(base_dir, "state", "processed_emails.json")

        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            email_ids = [str(email.get('id', '')) for email in emails if email.get('id')]
            state['processed_ids'] = [pid for pid in state.get('processed_ids', []) if pid not in email_ids]

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            Console.ok(f"已恢复 {len(email_ids)} 封邮件为未处理状态")
    except Exception as e:
        Console.warn(f"恢复邮件状态失败: {e}")


def _open_html_preview(file_path: Optional[str]) -> None:
    if not file_path:
        return
    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            Console.step_warn(f"找不到归档文件: {abs_path}")
            return
        url = Path(abs_path).resolve().as_uri()
        Console.step_info("打开浏览器预览...")
        webbrowser.open(url, new=2)
    except Exception as e:
        Console.step_warn(f"打开浏览器预览失败: {e}")


def run_pipeline(limit: int, target_email: str, subject: str = "邮件每日总结", use_unseen: bool = True, send_attachment: bool = False) -> Dict:
    emails = []

    try:
        # ---- Step 1: 读取邮件 ----
        Console.step_header("STEP 1/5  读取邮件")
        emails = _read_emails(limit, use_unseen)
        if not emails:
            return {"status": "no_new_emails", "message": "没有新的待处理邮件"}

        if len(emails) > MAX_LLM_EMAILS:
            Console.info(f"邮件数量 ({len(emails)}) 超过单次处理上限 ({MAX_LLM_EMAILS})，仅处理最近 {MAX_LLM_EMAILS} 封")
            emails = emails[:MAX_LLM_EMAILS]

        # ---- Step 2: LLM 智能总结 ----
        Console.step_header("STEP 2/5  LLM 智能总结")
        summary_htmls = _process_emails_parallel(emails)
        if not summary_htmls:
            Console.fail("所有邮件总结均失败，流程终止")
            mark_emails_as_unprocessed(emails)
            return {"status": "error", "message": "所有LLM总结均失败，无内容可处理。"}

        # ---- Step 3: 组装报告 ----
        Console.step_header("STEP 3/5  组装报告")
        Console.step_info("正在生成 HTML 邮件正文...")
        final_html_body = compose_final_html_body(summary_htmls, None, emails)
        Console.step_ok("报告组装完成")

        # ---- Step 4: 保存归档 & 预览 ----
        Console.step_header("STEP 4/5  保存归档 & 预览")
        archive_path = _save_archive_and_get_path(final_html_body)

        if archive_path and send_attachment:
            final_html_body = compose_final_html_body(summary_htmls, os.path.basename(archive_path), emails)

        if archive_path:
            threading.Thread(target=_open_html_preview, args=(archive_path,), daemon=True).start()

        # ---- Step 5: 发送邮件 ----
        Console.step_header("STEP 5/5  发送邮件")
        send_result = _send_email(target_email, subject, final_html_body, archive_path, send_attachment)

        if send_result.get("status") == "error":
            error_detail = send_result.get("error", "未知错误")
            Console.warn(f"邮件推送失败，但总结归档已保存")
            Console.step_info(f"可手动查看归档: {archive_path}")
            return {
                "status": "partial", "to": target_email, "subject": subject,
                "archive_path": archive_path, "email_count": len(emails),
                "warning": "邮件推送失败，但总结归档已生成",
                "send_error": error_detail
            }

        return {
            "status": "sent", "to": target_email, "subject": subject,
            "archive_path": archive_path, "email_count": len(emails)
        }

    except (TimeoutError, KeyboardInterrupt) as e:
        status, message = ("timeout", "处理超时") if isinstance(e, TimeoutError) else ("interrupted", "用户中断")
        Console.blank()
        Console.warn(message)
        Console.step_info("正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {"status": status, "message": f"{message}，邮件已恢复为未处理状态", "email_count": len(emails)}

    except Exception as e:
        Console.blank()
        Console.fail(f"处理过程中出现严重错误: {e}")
        Console.step_info("正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {"status": "error", "message": f"处理失败: {e}", "email_count": len(emails)}
