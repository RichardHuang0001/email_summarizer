#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt 模块
- EmailSummarizerPrompt: 针对单封邮件生成结构化总结
- FinalEmailDraftPrompt: 针对聚合报告撰写简洁通知邮件
"""
from langchain_core.prompts import ChatPromptTemplate


def get_email_summarizer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", "你是一个高效的邮件助理。请根据邮件的主题与正文，提取核心要点、行动项、重要日期与联系人，生成结构化且简洁的中文总结。务必考虑主题的关键信息，不要遗漏。"),
        ("human", "邮件主题：{email_subject}\n\n邮件内容如下：\n{email_content}")
    ])


def get_final_email_draft_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", "你将根据今日的邮件总结报告，撰写一封通知邮件发送给指定对象。正文应简洁明了，列出要点与下一步动作，并说明附件中有详细归档。"),
        ("human", "总结报告如下：\n{summary_report}\n\n归档文件路径：{archive_path}\n\n请撰写一封简洁、专业的中文通知邮件。")
    ])