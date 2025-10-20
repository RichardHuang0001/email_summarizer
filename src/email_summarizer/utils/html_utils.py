#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML模板工具函数
"""
from typing import List, Optional


def compose_final_html_body(summary_htmls: List[str], archive_path: Optional[str]) -> str:
    """
    将每封邮件的HTML卡片，组装成一封完整的、适合手机阅读的HTML邮件。
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