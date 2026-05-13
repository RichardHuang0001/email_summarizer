#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain.py
LCEL 编排流程
- 读取新邮件 -> 并行总结(生成HTML卡片) -> 组装完整HTML -> 保存归档 -> 发送邮件
"""
import os
import json
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
import webbrowser
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompts import get_email_summarizer_prompt
from .tools.email_reader import EmailReaderTool
# DocumentArchiverTool is no longer needed here, its logic is integrated below
from .tools.email_sender import EmailSenderTool
# aggregate_report_for_attachment is no longer needed
from .utils.email_utils import extract_email_contents
from .utils.html_utils import compose_final_html_body
from .utils.error_handler import handle_llm_error
from .utils.progress import ProgressTimer

load_dotenv()

MAX_LLM_EMAILS = 20


def _read_emails(limit: int, use_unseen: bool) -> List[Dict]:
    """
    读取邮件
    """
    print("📬 正在读取邮件...")
    reader = EmailReaderTool()
    reader_result = reader.invoke({"max_count": limit, "folder": "INBOX", "use_unseen": use_unseen})
    emails = extract_email_contents(reader_result)
    
    if not emails:
        print("✅ 没有新的待处理邮件")
        return []
    
    print(f"📧 接收到 {len(emails)} 封邮件，准备交给LLM处理")
    return emails


def _setup_llm_chain():
    """
    设置LLM链
    """
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    llm = ChatOpenAI(model=model_name, temperature=0, base_url=base_url) if base_url else ChatOpenAI(model=model_name, temperature=0)
    summarizer_prompt = get_email_summarizer_prompt()
    return summarizer_prompt | llm | StrOutputParser()


def _process_emails_parallel(emails: List[Dict], timer: ProgressTimer) -> List[str]:
    """
    并行处理邮件总结
    """
    summarizer_chain = _setup_llm_chain()
    contents = [{"email_subject": e.get("subject", "(No Subject)"), "email_content": e["content"]} for e in emails]
    
    max_concurrency = min(8, len(contents)) or 1
    print(f"🚀 并行发起 {max_concurrency} 个LLM请求处理邮件总结")
    
    timer.start("LLM处理邮件总结")
    
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_to_content = {
            executor.submit(summarizer_chain.invoke, content): i 
            for i, content in enumerate(contents)
        }
        
        summary_htmls = [None] * len(contents)
        completed_count = 0
        error_count = 0
        should_continue = True
        last_error_msg = ""
        
        for future in as_completed(future_to_content, timeout=60):
            if not should_continue:
                for remaining_future in future_to_content:
                    if not remaining_future.done():
                        remaining_future.cancel()
                break
                
            try:
                result = future.result()
                index = future_to_content[future]
                summary_htmls[index] = result
                completed_count += 1
                
                # 单行进度更新：每次完成都刷新一行，包含计时器与进度
                progress = completed_count / len(contents)
                elapsed = timer.get_elapsed_time()
                remaining = max(0, timer.timeout_seconds - elapsed)
                import sys
                sys.stdout.write(f"\r🔄 LLM处理 {completed_count}/{len(contents)} | 已用 {elapsed:.1f}s / 剩余 {remaining:.1f}s")
                sys.stdout.flush()
                
            except Exception as e:
                error_count += 1
                error_msg, should_continue = handle_llm_error(e)
                
                if error_msg != last_error_msg:
                    print(f"\n{error_msg}")
                    last_error_msg = error_msg
                
                if not should_continue:
                    print(f"\n🛑 检测到严重错误，停止处理剩余任务")
                    break
    
    timer.stop()
    
    success_count = len([s for s in summary_htmls if s])
    if success_count > 0:
        print(f"\n🎯 LLM处理完成！成功生成 {success_count} 个邮件总结")
        if error_count > 0:
            print(f"⚠️ 其中 {error_count} 个处理失败")
    else:
        print(f"\n❌ LLM处理失败！所有邮件总结都未能生成")
        if error_count > 0:
            print(f"💡 建议检查LLM配置和网络连接")
    
    return [s for s in summary_htmls if s]


def _save_archive_and_get_path(html_content: str) -> Optional[str]:
    """
    【新】将完整的HTML内容保存到归档文件并返回路径。
    """
    if not html_content:
        print("⚠️ 没有内容可供归档。")
        return None
    
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(os.path.dirname(current_dir)) # Project root
        archive_dir = os.path.join(base_dir, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        
        filename = f"archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.html"
        archive_path = os.path.join(archive_dir, filename)
        
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        print(f"📄 归档文件已生成: {archive_path}")
        return archive_path
    except Exception as e:
        print(f"⚠️ 归档文件生成失败: {e}")
        return None


def _send_email(target_email: str, subject: str, final_html_body: str, archive_path: Optional[str], send_attachment: bool) -> Dict:
    """
    发送邮件
    """
    print("📤 正在发送邮件...")
    try:
        sender = EmailSenderTool()
        # 【修改】附件路径现在直接使用 archive_path，但仅在 send_attachment 为 True 时传递
        attachment_to_send = archive_path if send_attachment else None
        
        send_result_str = sender.invoke({
            "to": target_email,
            "subject": subject,
            "body": final_html_body,
            "is_html": True,
            "attachment_path": attachment_to_send
        })
        result = json.loads(send_result_str)
        
        if "error" in result:
            print(f"❌ 邮件发送失败: {result['error']}")
            return {"status": "error", "error": result["error"]}
        else:
            print("✅ 邮件发送成功!")
            return result
            
    except Exception as e:
        error_msg = f"邮件发送过程中出现异常: {str(e)}"
        print(f"❌ {error_msg}")
        return {"status": "error", "error": error_msg}


def mark_emails_as_unprocessed(emails: List[Dict]):
    """将邮件标记为未处理状态"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(os.path.dirname(current_dir)) # 项目根目录
        state_file = os.path.join(base_dir, "state", "processed_emails.json")
        
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            email_ids = [str(email.get('id', '')) for email in emails if email.get('id')]
            state['processed_ids'] = [pid for pid in state.get('processed_ids', []) if pid not in email_ids]
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                
            print(f"📧 已恢复 {len(email_ids)} 封邮件为未处理状态")
    except Exception as e:
        print(f"⚠️ 恢复邮件状态失败: {e}")


def run_pipeline(limit: int, target_email: str, subject: str = "邮件每日总结", use_unseen: bool = True, send_attachment: bool = False) -> Dict:
    """
    【修改后流程】执行完整流程：读取 -> 总结 -> 组装HTML -> 保存归档 -> 发送
    """
    timer = ProgressTimer(timeout_seconds=120)
    emails = []
    
    try:
        emails = _read_emails(limit, use_unseen)
        if not emails:
            return {"status": "no_new_emails", "message": "没有新的待处理邮件"}

        if len(emails) > MAX_LLM_EMAILS:
            print(f"📊 邮件数量 ({len(emails)}) 超过单次处理上限 ({MAX_LLM_EMAILS})，仅处理最近 {MAX_LLM_EMAILS} 封")
            emails = emails[:MAX_LLM_EMAILS]

        summary_htmls = _process_emails_parallel(emails, timer)
        if not summary_htmls:
             # 如果所有总结都失败，则没有内容可发送或归档
            print("🛑 所有邮件总结均失败，流程终止。")
            mark_emails_as_unprocessed(emails)
            return {"status": "error", "message": "所有LLM总结均失败，无内容可处理。"}

        # --- 【核心逻辑修改】 ---
        # 1. 组装最终的HTML邮件正文。我们暂时不传入归档路径，因为还不知道
        print("📝 正在组装邮件内容...")
        final_html_body = compose_final_html_body(summary_htmls, None, emails)

        # 2. 将这份完整的HTML内容保存到文件，并获取路径
        archive_path = _save_archive_and_get_path(final_html_body)

        # 3. (可选) 如果需要，可以将归档路径回填到HTML中（用于邮件）
        #    这一步是可选的，因为邮件附件本身就是一种链接
        if archive_path and send_attachment:
             final_html_body = compose_final_html_body(summary_htmls, os.path.basename(archive_path), emails)

        # 4. 启动浏览器预览
        if archive_path:
            threading.Thread(target=_open_html_preview, args=(archive_path,), daemon=True).start()

        # 5. 发送邮件
        send_result = _send_email(target_email, subject, final_html_body, archive_path, send_attachment)

        if send_result.get("status") == "error":
            error_detail = send_result.get("error", "未知错误")
            print(f"⚠️ 邮件推送失败（但总结已完成）: {error_detail}")
            print(f"📄 HTML 归档文件已保存，可手动查看: {archive_path}")
            return {
                "status": "partial", "to": target_email, "subject": subject,
                "archive_path": archive_path, "email_count": len(emails),
                "warning": "邮件推送失败，但总结归档已生成",
                "send_error": error_detail
            }

        print("\n🎉 流程执行成功！")
        return {
            "status": "sent", "to": target_email, "subject": subject,
            "archive_path": archive_path, "email_count": len(emails)
        }
        
    except (TimeoutError, KeyboardInterrupt) as e:
        timer.stop()
        status, message = ("timeout", "处理超时") if isinstance(e, TimeoutError) else ("interrupted", "用户中断")
        print(f"\n⚠️ {message}！")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return { "status": status, "message": f"{message}，邮件已恢复为未处理状态", "email_count": len(emails) }
        
    except Exception as e:
        timer.stop()
        print(f"\n❌ 处理过程中出现严重错误: {e}")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return { "status": "error", "message": f"处理失败: {e}", "email_count": len(emails) }


def _open_html_preview(file_path: Optional[str]) -> None:
    """在默认浏览器中打开本地HTML预览（不阻塞主流程）"""
    if not file_path: return
    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            print(f"⚠️ 找不到归档文件: {abs_path}")
            return
        url = Path(abs_path).resolve().as_uri()
        print(f"🌐 正在打开浏览器预览: {abs_path}")
        webbrowser.open(url, new=2)
    except Exception as e:
        print(f"⚠️ 打开浏览器预览失败: {e}")
