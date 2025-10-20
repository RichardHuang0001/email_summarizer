#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LCEL 编排流程
- 读取新邮件 -> 并行总结 -> 聚合报告 -> 归档 -> 生成通知邮件正文 -> 发送
"""
import os
import json
from typing import List, Dict, Tuple

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompts import get_email_summarizer_prompt, get_final_email_draft_prompt
from .tools import EmailReaderTool, DocumentArchiverTool, EmailSenderTool

load_dotenv()


def _extract_email_contents(reader_output: str) -> List[Dict]:
    """将读取工具的字符串输出解析为邮件字典列表"""
    try:
        data = json.loads(reader_output)
        return data.get("emails", [])
    except Exception:
        return []


def _aggregate_report(summaries: List[Tuple[str, Dict]]) -> str:
    """将 (summary_text, meta) 列表汇总为 Markdown 文本"""
    lines = ["## 今日邮件总结总览\n"]
    for i, (text, meta) in enumerate(summaries, start=1):
        header = f"### 邮件 {i}: {meta.get('subject', '(No Subject)')}\n"
        meta_block = (
            f"- 发件人: {meta.get('from', '')}\n"
            f"- 时间: {meta.get('date', '')}\n"
        )
        lines.extend([header, meta_block, text.strip(), "\n"])
    return "\n".join(lines)


def run_pipeline(limit: int, target_email: str, subject: str = "邮件每日总结", use_unseen: bool = True) -> Dict:
    """
    执行完整流程：读取 -> 总结 -> 归档 -> 撰写 -> 发送
    返回包含归档路径、收件人、发送状态等信息的字典
    """
    # 1) 读取新邮件
    reader = EmailReaderTool()
    reader_result = reader.invoke({"max_count": limit, "folder": "INBOX", "use_unseen": use_unseen})
    emails = _extract_email_contents(reader_result)

    if not emails:
        return {"status": "no_new_emails", "message": "没有新的待处理邮件"}

    # 2) 并行总结
    llm = ChatOpenAI(model_name=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0)
    summarizer_prompt = get_email_summarizer_prompt()
    summarizer_chain = summarizer_prompt | llm | StrOutputParser()

    contents = [{"email_content": e["content"]} for e in emails]
    summary_texts: List[str] = summarizer_chain.batch(contents, config={"max_concurrency": 4})

    summaries = list(zip(summary_texts, emails))
    report_text = _aggregate_report(summaries)

    # 3) 归档
    archiver = DocumentArchiverTool()
    archive_result = archiver.invoke({"report_text": report_text})
    archive_path = json.loads(archive_result).get("archive_path")

    # 4) 生成最终通知邮件正文
    final_prompt = get_final_email_draft_prompt()
    final_chain = final_prompt | llm | StrOutputParser()
    final_body = final_chain.invoke({"summary_report": report_text, "archive_path": archive_path})

    # 5) 发送邮件
    sender = EmailSenderTool()
    send_result_str = sender.invoke({
        "to": target_email,
        "subject": subject,
        "body": final_body,
        "is_html": False,
        "attachment_path": archive_path
    })
    send_result = json.loads(send_result_str)

    return {
        "status": send_result.get("status", "unknown"),
        "to": target_email,
        "subject": subject,
        "archive_path": archive_path,
        "email_count": len(emails)
    }