#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt 模块
- EmailSummarizerPrompt: 针对单封邮件生成一个结构化的HTML卡片
"""
from langchain_core.prompts import ChatPromptTemplate


def get_email_summarizer_prompt() -> ChatPromptTemplate:
    """
    一个优化的Prompt，用于学生邮箱场景。
    它不再输出纯文本，而是输出一个简洁的、适合邮件客户端渲染的 HTML <div> 卡片。
    """
    
    system_message = """你是一个高效的HTML邮件助手。请快速完成三项任务：

1.  **分类**：从 [学术/校园, 招聘/求职, 个人/社交, 广告/推广] 中选择一个。
2.  **评级**：给出1-5星的重要性 (例如：★★★★☆)。
3.  **总结**：生成30-50字的中文核心内容。

请严格使用以下HTML格式回复，这只是一个卡片片段，绝对不要包含 <html> 或 <body> 标签。
请使用 <table> 来确保“分类”和“评级”在手机上也能完美对齐。

<div style="border-bottom: 1px solid #eeeeee; padding: 12px 0px;">
    <p style="margin: 0; padding: 0; font-size: 15px; font-weight: 600; color: #000000;">{email_subject}</p>
    <table style="width: 100%; margin-top: 8px; font-size: 14px; border-collapse: collapse;">
        <tr>
            <td style="width: 50px; color: #555555; padding: 2px 0;">分类:</td>
            <td style="color: #111111; padding: 2px 0;">[此处填写分类]</td>
        </tr>
        <tr>
            <td style="color: #555555; padding: 2px 0;">评级:</td>
            <td style="color: #f39c12; font-size: 18px; font-weight: bold; padding: 2px 0;">[此处填写星星]</td>
        </tr>
    </table>
    <p style="margin: 8px 0 0 0; padding: 0; font-size: 14px; color: #333333; line-height: 1.6;">
        [此处填写总结]
    </p>
</div>"""

    return ChatPromptTemplate.from_messages([
        ("system", system_message),
        ("human", "邮件主题：{email_subject}\n\n邮件内容如下：\n{email_content}")
    ])
