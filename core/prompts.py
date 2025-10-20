#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt 模块
- EmailSummarizerPrompt: 针对单封邮件生成结构化总结
- FinalEmailDraftPrompt: 针对聚合报告撰写简洁通知邮件
"""
from langchain_core.prompts import ChatPromptTemplate


def get_email_summarizer_prompt() -> ChatPromptTemplate:
    """
    一个优化的Prompt，用于学生邮箱场景。
    1. 判断类别
    2. 评估重要性 (1-5星)
    3. 简短总结
    4. 严格限制纯文本输出 (无Markdown)
    """
    
    system_message = """你是一个高效的学生邮件助手。请快速完成三项任务：

1.  **分类**：从 [学术/校园, 招聘/求职, 个人/社交, 广告/推广] 中选择一个。
2.  **评级**：给出1-5星的重要性评级 (5星最重要)。
3.  **总结**：生成30-50字的中文核心内容。

请严格使用以下纯文本格式回复，绝对不要使用Markdown (如 ** 或 ##)：
分类：[此处填写分类]
评级：[此处生成对应数量的星号]
总结：[此处填写总结]"""

    return ChatPromptTemplate.from_messages([
        ("system", system_message),
        ("human", "邮件主题：{email_subject}\n\n邮件内容如下：\n{email_content}")
    ])

