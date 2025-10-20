# LLM 邮件自动化

一个基于 LangChain 的邮件自动化工具：每次运行时读取你的邮箱新邮件（基于 Message-ID 去重），调用大模型进行总结，将汇总内容归档为 Markdown 文档，并将简洁通知邮件（附带归档）发送到目标邮箱。

## 功能特点
- 🔄 去重读取：基于 `Message-ID` 记录状态，避免重复处理
- 🧠 LLM 总结：对每封邮件并行生成结构化总结，聚合为报告
- 🗂️ 自动归档：将聚合报告持久化到 `archive/` 下的 Markdown 文档
- ✉️ 邮件发送：自动撰写通知邮件并发送到指定邮箱，支持附件
- ⚙️ 清晰架构：工具模块化（Reader/Archiver/Sender）+ LCEL 编排

## 目录结构
```
email_summarizer/
├── archive/                 # 归档文档输出目录
│   └── .gitkeep
├── src/                     # 源代码目录
│   ├── email_summarizer/    # 主要业务逻辑
│   │   ├── __init__.py
│   │   ├── chain.py         # LCEL 主流程
│   │   ├── prompts.py       # Prompt 模板
│   │   ├── tools/           # EmailReader/Archiver/Sender 工具
│   │   └── utils/           # 工具函数
│   └── state/               # 已处理邮件状态
│       └── processed_emails.json
├── core/                    # 核心逻辑（旧版本，保留兼容）
│   ├── __init__.py
│   ├── chain.py
│   ├── prompts.py
│   └── tools.py
├── scripts/
│   └── setup_config.py      # 配置向导（生成 .env）
├── docs/
│   └── 邮件总结工具使用指南.md
├── config/
│   └── .env.example
├── requirements.txt
├── main.py                  # 命令行入口
└── README.md
```

## 快速开始
### 1. 安装依赖
```bash
cd email_summarizer
pip install -r requirements.txt
```

### 2. 生成配置（.env）
```bash
python scripts/setup_config.py
```
- 必填：`OPENAI_API_KEY`、`EMAIL_USE`、`EMAIL_CONFIGS`
- 可选：`HTTP_PROXY`/`HTTPS_PROXY`

### 3. 运行主流程
```bash
python main.py --limit 20 --to someone@example.com --subject "每日邮件总结"
```
- `--limit`：读取的新邮件最大数量（默认 20, 范围 1-50）
- `--to`：通知邮件收件人（必填）
- `--subject`：通知邮件主题（默认 “邮件每日总结”）
- `--all`：读取全部邮件（默认仅未读）

## 配置说明
- `EMAIL_USE` 支持：`QQ`、`163`、`ALIYUN`
- `EMAIL_CONFIGS` 示例（由向导生成）：
```json
{
  "QQ": {
    "smtp_host": "smtp.qq.com",
    "smtp_port": 465,
    "imap_host": "imap.qq.com",
    "username": "your@qq.com",
    "password": "授权码"
  }
}
```

## 工作流概览
1. 读取新邮件：`EmailReaderTool` 通过 IMAP 获取未读邮件；使用 `state/processed_emails.json` 记录已处理 ID
2. 并行总结：`Prompt -> ChatOpenAI -> StrOutputParser` 对每封邮件并发生成摘要
3. 聚合与归档：整合为 Markdown 报告，`DocumentArchiverTool` 写入 `archive/`
4. 撰写通知邮件：用聚合报告和归档路径生成简洁正文
5. 发送邮件：`EmailSenderTool` 通过 SMTP 发送，并附上归档文档

## 注意事项
- 首次运行请确保 `.env` 已配置且邮箱 IMAP/SMTP 已开启
- `Message-ID` 缺失的邮件将用 (发件人|主题|时间|内容片段) 构造兜底 ID

## 后续优化
- Prompt 细化与风格控制
- 归档文件命名策略与分组格式
- 错误告警与重试机制

## OpenRouter网站的免费api模型可以在这个网页查询
https://openrouter.ai/models/?q=free