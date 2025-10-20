#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.abspath('.'))
from src.email_summarizer.tools.document_archiver import DocumentArchiverTool

s = """## 今日邮件总结总览
### 邮件 1: 预览示例
- 发件人: 系统
- 时间: 2025-10-21
```html
<div style=\"border-bottom:1px solid #eee;padding:12px 0;\"><p style=\"margin:0;font-size:15px;font-weight:600;\">这是归档HTML渲染示例</p></div>
```
"""

tool = DocumentArchiverTool()
print(tool.invoke({"report_text": s, "file_name": "preview_test.html", "append": False}))