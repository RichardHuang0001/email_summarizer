#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件处理工具函数
"""
import json
from typing import List, Dict


def extract_email_contents(reader_output: str) -> List[Dict]:
    """将读取工具的字符串输出解析为邮件字典列表"""
    try:
        data = json.loads(reader_output)
        return data.get("emails", [])
    except Exception:
        return []


def aggregate_report_for_attachment(summaries_html: List[str], emails_meta: List[Dict]) -> str:
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