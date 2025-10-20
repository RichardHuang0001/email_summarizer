#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain.py
LCEL 编排流程
- 读取新邮件 -> 并行总结(生成HTML卡片) -> 聚合报告 -> 归档 -> 组装完整HTML邮件 -> 发送
"""
import os
import json
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
import webbrowser
import threading
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompts import get_email_summarizer_prompt
from .tools.email_reader import EmailReaderTool
from .tools.document_archiver import DocumentArchiverTool
from .tools.email_sender import EmailSenderTool
from .utils.email_utils import extract_email_contents, aggregate_report_for_attachment
from .utils.html_utils import compose_final_html_body
from .utils.error_handler import handle_llm_error
from .utils.progress import ProgressTimer

load_dotenv()


def _read_emails(limit: int, use_unseen: bool) -> List[Dict]:
    """
    读取邮件
    
    Args:
        limit: 最大邮件数量
        use_unseen: 是否只读取未读邮件
        
    Returns:
        List[Dict]: 邮件列表
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
    
    Returns:
        LLM链对象
    """
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    llm = ChatOpenAI(model=model_name, temperature=0, base_url=base_url) if base_url else ChatOpenAI(model=model_name, temperature=0)
    summarizer_prompt = get_email_summarizer_prompt()
    return summarizer_prompt | llm | StrOutputParser()


def _process_emails_parallel(emails: List[Dict], timer: ProgressTimer) -> List[str]:
    """
    并行处理邮件总结
    
    Args:
        emails: 邮件列表
        timer: 进度计时器
        
    Returns:
        List[str]: 邮件总结HTML列表
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
                
                if completed_count % 2 == 0 or completed_count == len(contents):
                    progress = completed_count / len(contents)
                    print(f"\r✅ 已完成 {completed_count}/{len(contents)} 个总结 ({progress:.0%})", end='', flush=True)
                
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
    
    return summary_htmls


def _generate_and_save_archive(summary_htmls: List[str], emails: List[Dict]) -> Optional[str]:
    """
    【修改】总是生成并保存归档文件
    
    Args:
        summary_htmls: 邮件总结HTML列表
        emails: 邮件列表
        
    Returns:
        Optional[str]: 归档文件路径，如果生成失败则返回None
    """
    print("📁 正在生成归档文件...")
    # 确保即使部分总结失败，也能生成报告
    valid_summaries = [s for s in summary_htmls if s]
    if not valid_summaries:
        print("⚠️ 没有有效的总结内容，无法生成归档文件。")
        return None
        
    report_text_for_attachment = aggregate_report_for_attachment(summary_htmls, emails)
    archiver = DocumentArchiverTool()
    archive_result = archiver.invoke({"report_text": report_text_for_attachment})
    
    try:
        archive_path = json.loads(archive_result).get("archive_path")
        if archive_path:
            print(f"📄 归档文件已生成: {archive_path}")
            return archive_path
    except Exception as e:
        print(f"⚠️ 归档文件生成失败: {e}")
    
    return None


def _send_email(target_email: str, subject: str, final_html_body: str, archive_path: Optional[str], send_attachment: bool) -> Dict:
    """
    发送邮件
    
    Args:
        target_email: 目标邮箱
        subject: 邮件主题
        final_html_body: 邮件HTML正文
        archive_path: 归档文件路径
        send_attachment: 是否发送附件
        
    Returns:
        Dict: 发送结果
    """
    print("📤 正在发送邮件...")
    try:
        sender = EmailSenderTool()
        send_result_str = sender.invoke({
            "to": target_email,
            "subject": subject,
            "body": final_html_body,
            "is_html": True,
            # 【修改】这里的逻辑现在是正确的：仅当 send_attachment 为 True 时才传递路径
            "attachment_path": archive_path if send_attachment else None
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
    执行完整流程：读取 -> 总结 -> 归档 -> 组装邮件 -> 发送
    
    Args:
        limit: 最大邮件数量
        target_email: 目标邮箱地址
        subject: 邮件主题
        use_unseen: 是否只读取未读邮件
        send_attachment: 是否将归档文件作为附件发送
        
    Returns:
        Dict: 处理结果
    """
    timer = ProgressTimer(timeout_seconds=120) # 增加超时时间
    emails = []
    
    try:
        emails = _read_emails(limit, use_unseen)
        if not emails:
            return {"status": "no_new_emails", "message": "没有新的待处理邮件"}

        summary_htmls = _process_emails_parallel(emails, timer)

        # 【修改】总是生成归档文件，不再依赖 send_attachment 参数
        archive_path = _generate_and_save_archive(summary_htmls, emails)

        print("📝 正在组装邮件内容...")
        final_html_body = compose_final_html_body(summary_htmls, archive_path)

        # 并行启动浏览器预览，不影响后续邮件发送
        if archive_path:
            threading.Thread(target=_open_html_preview, args=(archive_path,), daemon=True).start()

        send_result = _send_email(target_email, subject, final_html_body, archive_path, send_attachment)

        if send_result.get("status") == "error":
            print(f"❌ 邮件发送失败: {send_result.get('error', '未知错误')}")
            print("🔄 正在恢复邮件为未处理状态...")
            mark_emails_as_unprocessed(emails)
            return {
                "status": "send_failed",
                "error": send_result.get("error", "邮件发送失败"),
                "email_count": len(emails)
            }
        
        print("\n🎉 流程执行成功！")
        return {
            "status": send_result.get("status", "sent"),
            "to": target_email,
            "subject": subject,
            "archive_path": archive_path, # 现在这里总会有一个路径 (如果成功)
            "email_count": len(emails)
        }
        
    except (TimeoutError, KeyboardInterrupt) as e:
        timer.stop()
        status = "timeout" if isinstance(e, TimeoutError) else "interrupted"
        message = "处理超时" if status == "timeout" else "用户中断"
        print(f"\n⚠️ {message}！")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {
            "status": status,
            "message": f"{message}，邮件已恢复为未处理状态",
            "email_count": len(emails)
        }
        
    except Exception as e:
        timer.stop()
        print(f"\n❌ 处理过程中出现严重错误: {e}")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {
            "status": "error",
            "message": f"处理失败: {e}",
            "email_count": len(emails)
        }


def _open_html_preview(file_path: Optional[str]) -> None:
    """在默认浏览器中打开本地HTML预览（不阻塞主流程）"""
    if not file_path:
        return
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

