#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LCEL 编排流程
- 读取新邮件 -> 并行总结(生成HTML卡片) -> 聚合报告 -> 归档 -> 组装完整HTML邮件 -> 发送
"""
import os
import json
from typing import List, Dict, Tuple, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompts import get_email_summarizer_prompt
from .tools import EmailReaderTool, DocumentArchiverTool, EmailSenderTool

load_dotenv()


def _extract_email_contents(reader_output: str) -> List[Dict]:
    """将读取工具的字符串输出解析为邮件字典列表"""
    try:
        data = json.loads(reader_output)
        return data.get("emails", [])
    except Exception:
        return []


def _aggregate_report_for_attachment(summaries_html: List[str], emails_meta: List[Dict]) -> str:
    """将HTML总结和元数据汇总为 Markdown 文本，用于附件。"""
    # 注意：这个函数现在只为附件服务，邮件正文将是纯HTML。
    lines = ["## 今日邮件总结总览\n"]
    # 简单地从HTML中提取一些文本作为附件的摘要，或者直接放入HTML
    for i, (html, meta) in enumerate(zip(summaries_html, emails_meta), start=1):
        header = f"### 邮件 {i}: {meta.get('subject', '(No Subject)')}\n"
        meta_block = (
            f"- 发件人: {meta.get('from', '')}\n"
            f"- 时间: {meta.get('date', '')}\n"
        )
        # 附件中可以简单包含HTML原文
        summary_block = f"```html\n{html.strip()}\n```\n"
        lines.extend([header, meta_block, summary_block, "\n---\n"])
    return "\n".join(lines)


def _compose_final_html_body(summary_htmls: List[str], archive_path: Optional[str]) -> str:
    """
    【新】将每封邮件的HTML卡片，组装成一封完整的、适合手机阅读的HTML邮件。
    这个函数不再需要LLM，而是通过代码模板完成，更稳定高效。
    """
    # 将所有HTML卡片片段连接起来
    all_email_cards = "\n".join(summary_htmls)

    # 完整的HTML邮件模板
    html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>今日邮件摘要</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      margin: 0;
      padding: 0;
      background-color: #f4f7f6;
    }}
    .container {{
      max-width: 600px;
      margin: 20px auto;
      background-color: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    }}
    .header {{
      padding: 24px;
      background-color: #4A90E2; /* A nice blue header */
      text-align: center;
    }}
    .header h1 {{
      margin: 0;
      font-size: 24px;
      color: #ffffff;
    }}
    .summary-list {{
      padding: 10px 24px 24px 24px;
    }}
    .footer {{
      padding: 20px;
      text-align: center;
      font-size: 12px;
      color: #888888;
      background-color: #fafafa;
      border-top: 1px solid #eeeeee;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>今日邮件摘要</h1>
    </div>
    <div class="summary-list">
      {all_email_cards}
    </div>
    <div class="footer">
      {'详细归档文档见附件。' if archive_path else '本次未生成归档文件。'}
    </div>
  </div>
</body>
</html>
"""
    return html_template


def run_pipeline(limit: int, target_email: str, subject: str = "邮件每日总结", use_unseen: bool = True, send_attachment: bool = False) -> Dict:
    """
    执行完整流程：读取 -> 总结(生成HTML卡片) -> 归档(可选) -> 组装完整HTML邮件 -> 发送
    
    Args:
        send_attachment: 是否发送归档文件作为附件，默认为False
    """
    # 1) 读取新邮件
    reader = EmailReaderTool()
    reader_result = reader.invoke({"max_count": limit, "folder": "INBOX", "use_unseen": use_unseen})
    emails = _extract_email_contents(reader_result)

    if not emails:
        return {"status": "no_new_emails", "message": "没有新的待处理邮件"}

    # 2) 并行总结（生成HTML卡片）
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    llm = ChatOpenAI(model=model_name, temperature=0, base_url=base_url) if base_url else ChatOpenAI(model=model_name, temperature=0)
    summarizer_prompt = get_email_summarizer_prompt()
    summarizer_chain = summarizer_prompt | llm | StrOutputParser()

    contents = [{"email_subject": e.get("subject", "(No Subject)"), "email_content": e["content"]} for e in emails]
    summary_htmls: List[str] = summarizer_chain.batch(contents, config={"max_concurrency": min(8, len(contents)) or 1})

    # 3) 归档 (仅在需要发送附件时执行)
    archive_path = None
    if send_attachment:
        report_text_for_attachment = _aggregate_report_for_attachment(summary_htmls, emails)
        archiver = DocumentArchiverTool()
        archive_result = archiver.invoke({"report_text": report_text_for_attachment})
        try:
            archive_path = json.loads(archive_result).get("archive_path")
        except Exception:
            archive_path = None

    # 4) 【新】使用代码模板组装最终的HTML邮件正文
    final_html_body = _compose_final_html_body(summary_htmls, archive_path)

    # 5) 发送邮件【关键改动】
    sender = EmailSenderTool()
    send_result_str = sender.invoke({
        "to": target_email,
        "subject": subject,
        "body": final_html_body, # <-- 传入HTML正文
        "is_html": True,         # <-- 标记为HTML邮件
        "attachment_path": archive_path if send_attachment else None
    })
    send_result = json.loads(send_result_str)

    return {
        "status": send_result.get("status", "unknown"),
        "to": target_email,
        "subject": subject,
        "archive_path": archive_path,
        "email_count": len(emails)
    }
