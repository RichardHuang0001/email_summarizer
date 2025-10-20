#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LCEL 编排流程
- 读取新邮件 -> 并行总结(生成HTML卡片) -> 聚合报告 -> 归档 -> 组装完整HTML邮件 -> 发送
"""
import os
import json
import time
import sys
import threading
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompts import get_email_summarizer_prompt
from .tools.email_reader import EmailReaderTool
from .tools.document_archiver import DocumentArchiverTool
from .tools.email_sender import EmailSenderTool
from .utils.email_utils import extract_email_contents, aggregate_report_for_attachment
from .utils.html_utils import compose_final_html_body

load_dotenv()


class ProgressTimer:
    """实时进度计时器"""
    def __init__(self, timeout_seconds=60):
        self.timeout_seconds = timeout_seconds
        self.start_time = None
        self.stop_event = threading.Event()
        self.timer_thread = None
        
    def start(self, message="处理中"):
        """开始计时器"""
        self.start_time = time.time()
        self.stop_event.clear()
        self.timer_thread = threading.Thread(target=self._update_timer, args=(message,))
        self.timer_thread.daemon = True
        self.timer_thread.start()
        
    def stop(self):
        """停止计时器"""
        if self.timer_thread:
            self.stop_event.set()
            self.timer_thread.join(timeout=1)
            # 清除当前行
            sys.stdout.write('\r' + ' ' * 80 + '\r')
            sys.stdout.flush()
            
    def _update_timer(self, message):
        """更新计时器显示"""
        while not self.stop_event.is_set():
            elapsed = time.time() - self.start_time
            remaining = max(0, self.timeout_seconds - elapsed)
            
            if remaining <= 0:
                sys.stdout.write(f'\r⏰ 超时！已等待 {elapsed:.1f}s')
                sys.stdout.flush()
                break
                
            # 显示进度条
            progress = elapsed / self.timeout_seconds
            bar_length = 20
            filled_length = int(bar_length * progress)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            sys.stdout.write(f'\r🔄 {message} [{bar}] {elapsed:.1f}s/{self.timeout_seconds}s (剩余 {remaining:.1f}s)')
            sys.stdout.flush()
            time.sleep(0.5)


def mark_emails_as_unprocessed(emails: List[Dict]):
    """将邮件标记为未处理状态"""
    try:
        state_file = "state/processed_emails.json"
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # 移除这些邮件的ID
            email_ids = [str(email.get('id', '')) for email in emails if email.get('id')]
            state['processed_ids'] = [id for id in state.get('processed_ids', []) if id not in email_ids]
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                
            print(f"📧 已恢复 {len(email_ids)} 封邮件为未处理状态")
    except Exception as e:
        print(f"⚠️ 恢复邮件状态失败: {e}")


def run_pipeline(limit: int, target_email: str, subject: str = "邮件每日总结", use_unseen: bool = True, send_attachment: bool = False) -> Dict:
    """
    执行完整流程：读取 -> 总结(生成HTML卡片) -> 归档(可选) -> 组装完整HTML邮件 -> 发送
    
    Args:
        send_attachment: 是否发送归档文件作为附件，默认为False
    """
    timer = ProgressTimer(timeout_seconds=60)
    emails = []
    
    try:
        # 1) 读取新邮件
        print("📬 正在读取邮件...")
        reader = EmailReaderTool()
        reader_result = reader.invoke({"max_count": limit, "folder": "INBOX", "use_unseen": use_unseen})
        emails = extract_email_contents(reader_result)

        if not emails:
            print("✅ 没有新的待处理邮件")
            return {"status": "no_new_emails", "message": "没有新的待处理邮件"}

        # 显示接收到的邮件数量
        print(f"📧 接收到 {len(emails)} 封邮件，准备交给LLM处理")
        
        # 2) 并行总结（生成HTML卡片）
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        llm = ChatOpenAI(model=model_name, temperature=0, base_url=base_url) if base_url else ChatOpenAI(model=model_name, temperature=0)
        summarizer_prompt = get_email_summarizer_prompt()
        summarizer_chain = summarizer_prompt | llm | StrOutputParser()

        contents = [{"email_subject": e.get("subject", "(No Subject)"), "email_content": e["content"]} for e in emails]
        
        # 显示并行请求数量
        max_concurrency = min(8, len(contents)) or 1
        print(f"🚀 并行发起 {max_concurrency} 个LLM请求处理邮件总结")
        
        # 启动进度计时器
        timer.start("LLM处理邮件总结")
        
        # 使用ThreadPoolExecutor实现超时控制
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            # 提交所有任务
            future_to_content = {
                executor.submit(summarizer_chain.invoke, content): i 
                for i, content in enumerate(contents)
            }
            
            summary_htmls = [None] * len(contents)
            completed_count = 0
            
            # 等待任务完成，带超时
            for future in as_completed(future_to_content, timeout=60):
                try:
                    result = future.result()
                    index = future_to_content[future]
                    summary_htmls[index] = result
                    completed_count += 1
                    
                    # 更新进度
                    progress = completed_count / len(contents)
                    print(f"\r✅ 已完成 {completed_count}/{len(contents)} 个总结 ({progress:.1%})", end='', flush=True)
                    
                except Exception as e:
                    print(f"\n⚠️ 处理邮件总结时出错: {e}")
                    
        timer.stop()
        print(f"\n🎯 LLM处理完成！共生成 {len([s for s in summary_htmls if s])} 个邮件总结")

        # 3) 归档 (仅在需要发送附件时执行)
        archive_path = None
        if send_attachment:
            print("📁 正在生成归档文件...")
            report_text_for_attachment = aggregate_report_for_attachment(summary_htmls, emails)
            archiver = DocumentArchiverTool()
            archive_result = archiver.invoke({"report_text": report_text_for_attachment})
            try:
                archive_path = json.loads(archive_result).get("archive_path")
                if archive_path:
                    print(f"📄 归档文件已生成: {archive_path}")
            except Exception as e:
                print(f"⚠️ 归档文件生成失败: {e}")
                archive_path = None

        # 4) 组装最终的HTML邮件正文
        print("📝 正在组装邮件内容...")
        final_html_body = compose_final_html_body(summary_htmls, archive_path)

        # 5) 发送邮件
        print("📤 正在发送邮件...")
        sender = EmailSenderTool()
        send_result_str = sender.invoke({
            "to": target_email,
            "subject": subject,
            "body": final_html_body,
            "is_html": True,
            "attachment_path": archive_path if send_attachment else None
        })
        send_result = json.loads(send_result_str)

        print("🎉 邮件发送完成！")
        return {
            "status": send_result.get("status", "unknown"),
            "to": target_email,
            "subject": subject,
            "archive_path": archive_path,
            "email_count": len(emails)
        }
        
    except TimeoutError:
        timer.stop()
        print(f"\n⏰ 处理超时！已超过60秒限制")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {
            "status": "timeout",
            "message": "处理超时，邮件已恢复为未处理状态",
            "email_count": len(emails)
        }
        
    except KeyboardInterrupt:
        timer.stop()
        print(f"\n⚠️ 用户中断处理")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {
            "status": "interrupted",
            "message": "用户中断，邮件已恢复为未处理状态",
            "email_count": len(emails)
        }
        
    except Exception as e:
        timer.stop()
        print(f"\n❌ 处理过程中出现错误: {e}")
        print("🔄 正在恢复邮件为未处理状态...")
        mark_emails_as_unprocessed(emails)
        return {
            "status": "error",
            "message": f"处理失败: {e}",
            "email_count": len(emails)
        }
