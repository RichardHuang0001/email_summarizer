#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.abspath('.'))

from src.email_summarizer.utils.html_utils import compose_final_html_body

cards = [
    '<div style="border-bottom: 1px solid #eeeeee; padding: 12px 0px;"><p style="margin: 0; padding: 0; font-size: 15px; font-weight: 600; color: #000000;">示例标题 A</p><table style="width: 100%; margin-top: 8px; font-size: 14px; border-collapse: collapse;"><tr><td style="width: 50px; color: #555555; padding: 2px 0;">分类:</td><td style="color: #111111; padding: 2px 0;">通知</td></tr><tr><td style="color: #555555; padding: 2px 0;">评级:</td><td style="color: #f39c12; font-size: 18px; font-weight: bold; padding: 2px 0;">★★★☆☆</td></tr></table><p style="margin: 8px 0 0 0; padding: 0; font-size: 14px; color: #333333; line-height: 1.6;">这是一段示例摘要。</p></div>',
    '<div style="border-bottom: 1px solid #eeeeee; padding: 12px 0px;"><p style="margin: 0; padding: 0; font-size: 15px; font-weight: 600; color: #000000;">示例标题 B</p><table style="width: 100%; margin-top: 8px; font-size: 14px; border-collapse: collapse;"><tr><td style="width: 50px; color: #555555; padding: 2px 0;">分类:</td><td style="color: #111111; padding: 2px 0;">任务</td></tr><tr><td style="color: #555555; padding: 2px 0;">评级:</td><td style="color: #f39c12; font-size: 18px; font-weight: bold; padding: 2px 0;">★★★★★</td></tr></table><p style="margin: 8px 0 0 0; padding: 0; font-size: 14px; color: #333333; line-height: 1.6;">这是一段示例摘要，五颗星。</p></div>',
]

emails_meta = [
    {"date": "2025-10-21 09:26", "from": "系统 <sys@example.com>"},
    {"date": "2025-10-21 08:15", "from": "运营通知 <ops@example.com>"},
]

html = compose_final_html_body(cards, archive_path=None, emails_meta=emails_meta)

out_dir = os.path.join(os.getcwd(), "archive")
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, "preview_injection_test.html")
with open(out_file, "w", encoding="utf-8") as f:
    f.write(html)
print(out_file)