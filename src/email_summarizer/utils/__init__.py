#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utils模块：包含邮件处理和HTML生成的工具函数
"""

from .email_utils import extract_email_contents, aggregate_report_for_attachment
from .html_utils import compose_final_html_body

__all__ = [
    "extract_email_contents",
    "aggregate_report_for_attachment", 
    "compose_final_html_body"
]