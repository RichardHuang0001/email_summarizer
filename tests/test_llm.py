#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单 LLM 连通性测试：
- 从环境变量读取模型配置（OPENAI_MODEL、OPENAI_BASE_URL/OPENAI_API_BASE、OPENAI_API_KEY）
- 发起一条简单请求
- 在终端提示检测成功或失败
"""
import os
import sys
from dotenv import load_dotenv

# 兼容 src 布局（与主程序一致），不影响测试逻辑
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))


def main():
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ 未检测到 OPENAI_API_KEY 环境变量。请在 .env 或系统环境中配置。")
        sys.exit(1)

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")

    try:
        from langchain_openai import ChatOpenAI
        # 构造 LLM 客户端（兼容自定义 base_url）
        llm = ChatOpenAI(model=model_name, temperature=0, base_url=base_url) if base_url else ChatOpenAI(model=model_name, temperature=0)

        prompt = "用简洁的一句中文问候，包含'你好'二字。"
        resp = llm.invoke(prompt)
        content = getattr(resp, "content", None) or str(resp)

        if isinstance(content, str) and content.strip():
            print("✅ LLM 请求成功。")
            print(f"- 模型: {model_name}")
            if base_url:
                print(f"- Base URL: {base_url}")
            print(f"- 响应: {content.strip()[:120]}{'...' if len(content.strip())>120 else ''}")
            sys.exit(0)
        else:
            print("⚠️ LLM 请求返回内容为空或类型异常。")
            sys.exit(2)

    except Exception as e:
        print(f"❌ LLM 请求失败: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()