#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置向导 - 帮助用户快速设置邮件总结工具
"""

import os
import json
import getpass

def setup_config():
    """配置向导"""
    print("🔧 邮件总结工具配置向导")
    print("="*50)
    
    config_data = {}
    
    # 1. OpenAI API Key
    print("\n1️⃣ OpenAI API 配置")
    print("   需要 OpenAI API Key 来进行邮件内容分析")
    openai_key = getpass.getpass("   请输入你的 OpenAI API Key: ").strip()
    if not openai_key:
        print("❌ OpenAI API Key 不能为空！")
        return False
    config_data['OPENAI_API_KEY'] = openai_key
    
    # 2. 邮箱服务选择
    print("\n2️⃣ 邮箱服务选择")
    print("   支持的邮箱服务：")
    print("   1. QQ邮箱")
    print("   2. 163邮箱") 
    print("   3. 阿里云邮箱")
    
    while True:
        choice = input("   请选择邮箱服务 (1-3): ").strip()
        if choice == "1":
            email_service = "QQ"
            smtp_host = "smtp.qq.com"
            imap_host = "imap.qq.com"
            break
        elif choice == "2":
            email_service = "163"
            smtp_host = "smtp.163.com"
            imap_host = "imap.163.com"
            break
        elif choice == "3":
            email_service = "ALIYUN"
            smtp_host = "smtp.aliyun.com"
            imap_host = "imap.aliyun.com"
            break
        else:
            print("   ❌ 请输入 1、2 或 3")
    
    config_data['EMAIL_USE'] = email_service
    
    # 3. 邮箱账号配置
    print(f"\n3️⃣ {email_service} 邮箱配置")
    email_username = input(f"   请输入你的{email_service}邮箱地址: ").strip()
    if not email_username:
        print("❌ 邮箱地址不能为空！")
        return False
    
    print(f"\n   ⚠️  重要提示：")
    if email_service == "QQ":
        print("   - QQ邮箱需要使用授权码，不是QQ密码")
        print("   - 请到 QQ邮箱设置 -> 账户 -> 开启IMAP/SMTP服务 获取授权码")
    elif email_service == "163":
        print("   - 163邮箱需要使用授权码，不是登录密码")
        print("   - 请到 163邮箱设置 -> POP3/SMTP/IMAP -> 开启服务 获取授权码")
    else:
        print("   - 阿里云邮箱需要使用授权码，不是登录密码")
        print("   - 请到邮箱设置中开启IMAP/SMTP服务获取授权码")
    
    email_password = getpass.getpass("   请输入邮箱授权码: ").strip()
    if not email_password:
        print("❌ 邮箱授权码不能为空！")
        return False
    
    # 4. 构建邮箱配置
    email_configs = {
        email_service: {
            "smtp_host": smtp_host,
            "smtp_port": 465,
            "imap_host": imap_host,
            "username": email_username,
            "password": email_password
        }
    }
    config_data['EMAIL_CONFIGS'] = json.dumps(email_configs, ensure_ascii=False)
    
    # 5. 代理设置（可选）
    print("\n4️⃣ 网络代理设置（可选）")
    use_proxy = input("   是否需要使用代理访问OpenAI API？(y/N): ").strip().lower()
    if use_proxy in ['y', 'yes']:
        proxy_url = input("   请输入代理地址 (如: http://127.0.0.1:7890): ").strip()
        if proxy_url:
            config_data['HTTP_PROXY'] = proxy_url
            config_data['HTTPS_PROXY'] = proxy_url
    
    # 6. 写入配置文件
    print("\n5️⃣ 保存配置")
    env_content = f"""# OpenAI API Key
OPENAI_API_KEY="{config_data['OPENAI_API_KEY']}"

# 邮件服务选择
EMAIL_USE="{config_data['EMAIL_USE']}"

# 邮件服务配置
EMAIL_CONFIGS='{config_data['EMAIL_CONFIGS']}'
"""
    
    if 'HTTP_PROXY' in config_data:
        env_content += f"""
# 网络代理设置
HTTP_PROXY="{config_data['HTTP_PROXY']}"
HTTPS_PROXY="{config_data['HTTPS_PROXY']}"
"""
    
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("✅ 配置文件已保存到 .env")
        return True
    except Exception as e:
        print(f"❌ 保存配置文件失败：{str(e)}")
        return False

def main():
    """主函数"""
    print("欢迎使用邮件总结工具！")
    print("此向导将帮助你快速配置工具所需的参数。\n")
    
    if setup_config():
        print("\n🎉 配置完成！")
        print("\n接下来你可以：")
        print("1. 运行 'python main.py --to <目标邮箱>' 开始自动化流程")
        print("2. 或者在 Python 中调用 core.chain.run_pipeline(limit=20, target_email=\"<目标邮箱>\")")
        print("\n💡 提示：如果遇到连接问题，请检查：")
        print("   - 邮箱授权码是否正确")
        print("   - 网络连接是否正常")
        print("   - 是否需要配置代理")
    else:
        print("\n❌ 配置失败，请重新运行此脚本。")

if __name__ == "__main__":
    main()