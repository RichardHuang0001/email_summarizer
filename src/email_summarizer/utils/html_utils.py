#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML模板工具函数
"""
import re # 添加 re 模块导入
from typing import List, Optional, Dict


# --- 【新增】提取星级评分的辅助函数 ---
def _extract_rating_from_html(html_snippet: str) -> int:
    """
    从HTML卡片片段中提取星级评分 (★ 的数量)。
    如果找不到或解析失败，返回 0。
    """
    if not isinstance(html_snippet, str):
        return 0
    try:
        # 查找包含星号的<td>标签内容 (假设样式与 prompts.py 中一致)
        match = re.search(r'<td[^>]*color:\s*#f39c12[^>]*>([^<]+)<\/td>', html_snippet, re.IGNORECASE)
        if match:
            stars_text = match.group(1).strip()
            return stars_text.count('★') # 计算实心星 '★' 的数量
        else:
            # 备用查找：如果精确匹配失败，尝试查找包含星号的行
            lines = html_snippet.split('\n')
            for line in lines:
                if '★' in line or '☆' in line:
                    return line.count('★')
            return 0 # 实在找不到
    except Exception:
        return 0 # 解析出错
# --- 提取星级函数结束 ---

# --- 【新增】在卡片标题下插入时间行 ---
def _inject_timestamp_into_card(card_html: str, timestamp: Optional[str]) -> str:
    if not card_html or not timestamp:
        return card_html
    # 避免重复插入
    if '时间:' in card_html:
        return card_html
    time_line = f'<p style="margin: 4px 0 0 0; padding: 0; font-size: 13px; color: #666666;">时间: {timestamp}</p>'
    try:
        # 将时间行插入到卡片的第一个 </p>（标题段落）之后
        return re.sub(r'(</p>)', r'\1' + time_line, card_html, count=1)
    except Exception:
        return card_html


def compose_final_html_body(summary_htmls: List[str], archive_path: Optional[str], emails_meta: Optional[List[Dict]] = None) -> str:
    """
    【修改】将每封邮件的HTML卡片按星级排序后，组装成一封完整的、适合手机阅读的HTML邮件。
    现在支持在卡片标题下方插入原邮件时间（不依赖LLM）。
    """
    # --- 【新增：时间插入】 ---
    working_cards: List[str]
    if emails_meta:
        injected_cards: List[str] = []
        for card, meta in zip(summary_htmls, emails_meta):
            injected_cards.append(_inject_timestamp_into_card(card, (meta or {}).get('date')))
        # 处理长度不匹配的剩余卡片
        if len(summary_htmls) > len(injected_cards):
            injected_cards.extend(summary_htmls[len(injected_cards):])
        working_cards = injected_cards
    else:
        working_cards = summary_htmls

    # --- 【排序逻辑】 ---
    try:
        valid_summaries = [s for s in working_cards if s] # 过滤掉可能的 None 值
        sorted_summary_htmls = sorted(
            valid_summaries,
            key=_extract_rating_from_html,
            reverse=True
        )
    except Exception as e:
        print(f"⚠️ 邮件摘要排序失败: {e}。将按原顺序显示。")
        sorted_summary_htmls = [s for s in working_cards if s] # 出错时恢复原顺序
    # --- 排序逻辑结束 ---

    # 将排序后的HTML卡片片段连接起来
    all_email_cards = "\n".join(sorted_summary_htmls)

    # --- 【样式恢复】 ---
    # 使用您提供的原始 HTML 模板和 CSS 样式
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
      padding: 0; /* 恢复 padding: 0 */
      background-color: #f4f7f6;
    }}
    .container {{
      max-width: 600px;
      margin: 20px auto; /* 恢复 margin: 20px auto */
      background-color: #ffffff;
      border-radius: 12px; /* 恢复 border-radius: 12px */
      overflow: hidden;
      box-shadow: 0 4px 15px rgba(0,0,0,0.08); /* 恢复 box-shadow */
    }}
    .header {{
      padding: 24px; /* 恢复 padding: 24px */
      background-color: #4A90E2; /* 恢复蓝色背景 */
      text-align: center; /* 恢复 text-align: center */
    }}
    .header h1 {{
      margin: 0;
      font-size: 24px; /* 恢复 font-size: 24px */
      color: #ffffff; /* 恢复白色字体 */
    }}
    .summary-list {{
      padding: 10px 24px 24px 24px; /* 恢复原 padding */
    }}
    /* 卡片样式由 prompts.py 生成的 HTML 片段自带，此处不添加 */
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
      <!-- 排序后的卡片将插入这里 -->
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

