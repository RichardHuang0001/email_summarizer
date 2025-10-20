#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DocumentArchiverTool: 将总结内容归档到本地 Markdown 文档
"""
import os
import json
from datetime import datetime
from typing import Optional, Type, List

from pydantic import BaseModel, Field
from langchain.tools import BaseTool

# 计算项目根路径
CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(CORE_DIR)
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")

# 确保基础目录存在
os.makedirs(ARCHIVE_DIR, exist_ok=True)


class ArchiverInput(BaseModel):
    report_text: str = Field(..., description="需要归档的汇总报告文本（Markdown）")
    file_name: Optional[str] = Field(None, description="自定义归档文件名，例如 archive_2025-10-19.html")
    append: bool = Field(True, description="是否以追加模式写入（HTML文档中追加新 section）")


class DocumentArchiverTool(BaseTool):
    name: str = "document_archiver_tool"
    description: str = "将总结文本保存为本地 HTML 归档文档，并返回文件路径"
    args_schema: Type[BaseModel] = ArchiverInput

    def _md_to_html(self, md: str) -> str:
        import html as _html
        lines = md.splitlines()
        buf: List[str] = []
        in_ul = False
        for line in lines:
            if line.startswith("### "):
                if in_ul:
                    buf.append("</ul>")
                    in_ul = False
                buf.append(f"<h3>{_html.escape(line[4:].strip())}</h3>")
            elif line.startswith("## "):
                if in_ul:
                    buf.append("</ul>")
                    in_ul = False
                buf.append(f"<h2>{_html.escape(line[3:].strip())}</h2>")
            elif line.startswith("- "):
                if not in_ul:
                    buf.append("<ul>")
                    in_ul = True
                buf.append(f"<li>{_html.escape(line[2:].strip())}</li>")
            elif line.strip() == "":
                if in_ul:
                    buf.append("</ul>")
                    in_ul = False
                buf.append("<br/>")
            else:
                buf.append(f"<p>{_html.escape(line.strip())}</p>")
        if in_ul:
            buf.append("</ul>")
        return "\n".join(buf)

    def _build_section(self, report_text: str) -> str:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        header = f"<h2 class='meta'>邮件总结归档 - {ts}</h2>"
        body = self._md_to_html(report_text)
        return f"<section class='section'>\n{header}\n{body}\n</section>\n"

    def _compose_document(self, section_html: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>邮件总结归档</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;line-height:1.6;padding:24px;color:#222;}}
h1,h2,h3{{margin:0.2em 0;}}
ul{{margin:0.2em 0 0.8em 1.2em;}}
li{{margin:0.2em 0;}}
.section{{margin-bottom:1.2em;padding-bottom:0.8em;border-bottom:1px solid #eee;}}
.meta{{color:#666;font-size:0.95em;}}
</style>
</head>
<body>
<h1>邮件总结归档</h1>
{section_html}
</body>
</html>
"""

    def _run(self, report_text: str, file_name: Optional[str] = None, append: bool = True) -> str:
        if not file_name:
            file_name = f"archive_{datetime.now().strftime('%Y-%m-%d')}.html"
        path = os.path.join(ARCHIVE_DIR, file_name)
        section_html = self._build_section(report_text)
        try:
            if append and os.path.exists(path):
                # 在已有 HTML 文档内追加新的 section（插入到 </body> 前）
                with open(path, "r+", encoding="utf-8") as f:
                    existing = f.read()
                    insert_pos = existing.rfind("</body>")
                    if insert_pos == -1:
                        # 非有效 HTML，重写完整文档
                        doc = self._compose_document(section_html)
                        f.seek(0)
                        f.write(doc)
                        f.truncate()
                    else:
                        new_content = existing[:insert_pos] + section_html + existing[insert_pos:]
                        f.seek(0)
                        f.write(new_content)
                        f.truncate()
            else:
                doc = self._compose_document(section_html)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(doc)
            return json.dumps({"archive_path": path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Failed to write archive: {str(e)}"}, ensure_ascii=False)