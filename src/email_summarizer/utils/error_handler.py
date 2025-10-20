#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误处理工具模块
提供统一的错误处理函数，用于处理LLM和邮件相关的错误
"""
from typing import Tuple


def handle_llm_error(error) -> Tuple[str, bool]:
    """
    处理LLM错误，返回错误信息和是否应该继续处理
    
    Args:
        error: 异常对象
        
    Returns:
        Tuple[str, bool]: (错误信息, 是否应该继续处理其他任务)
    """
    error_str = str(error)
    
    # 检查是否是余额不足错误
    if "402" in error_str and "Insufficient credits" in error_str:
        return "💳 LLM服务余额不足，请充值后重试", False
    
    # 检查是否是API密钥错误
    if "401" in error_str or "Unauthorized" in error_str:
        return "🔑 LLM API密钥无效或已过期", False
    
    # 检查是否是网络连接错误
    if "Connection" in error_str or "timeout" in error_str.lower():
        return "🌐 网络连接错误，请检查网络连接", True
    
    # 检查是否是模型不存在错误
    if "404" in error_str or "model" in error_str.lower():
        return "🤖 指定的LLM模型不存在或不可用", False
    
    # 检查是否是请求频率限制
    if "429" in error_str or "rate limit" in error_str.lower():
        return "⏱️ LLM请求频率过高，请稍后重试", True
    
    # 其他未知错误
    return f"❌ LLM处理错误: {error_str[:100]}...", True


def handle_email_error(error) -> str:
    """
    处理邮件相关错误，返回用户友好的错误信息
    
    Args:
        error: 异常对象
        
    Returns:
        str: 用户友好的错误信息
    """
    error_str = str(error)
    
    # IMAP连接错误
    if "IMAP" in error_str or "imap" in error_str.lower():
        if "authentication" in error_str.lower() or "login" in error_str.lower():
            return "🔐 IMAP认证失败，请检查邮箱用户名和密码"
        elif "connection" in error_str.lower() or "timeout" in error_str.lower():
            return "🌐 IMAP连接失败，请检查网络连接和服务器设置"
        else:
            return f"📧 IMAP操作失败: {error_str[:100]}..."
    
    # SMTP发送错误
    if "SMTP" in error_str or "smtp" in error_str.lower():
        if "authentication" in error_str.lower() or "login" in error_str.lower():
            return "🔐 SMTP认证失败，请检查邮箱用户名和密码"
        elif "connection" in error_str.lower() or "timeout" in error_str.lower():
            return "🌐 SMTP连接失败，请检查网络连接和服务器设置"
        elif "recipient" in error_str.lower():
            return "📮 收件人地址无效或被拒绝"
        else:
            return f"📤 邮件发送失败: {error_str[:100]}..."
    
    # 文件操作错误
    if "FileNotFoundError" in error_str or "No such file" in error_str:
        return "📁 文件不存在，请检查文件路径"
    elif "PermissionError" in error_str or "Permission denied" in error_str:
        return "🔒 文件权限不足，请检查文件访问权限"
    elif "OSError" in error_str or "IOError" in error_str:
        return f"💾 文件操作失败: {error_str[:100]}..."
    
    # JSON解析错误
    if "JSON" in error_str or "json" in error_str.lower():
        return "📄 数据格式错误，请检查配置文件格式"
    
    # 网络相关错误
    if "ConnectionError" in error_str or "requests" in error_str.lower():
        return "🌐 网络连接错误，请检查网络连接"
    
    # 其他未知错误
    return f"❌ 操作失败: {error_str[:100]}..."