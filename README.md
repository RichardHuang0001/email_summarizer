# LLM 邮件总结器

由 LLM 驱动的自动化邮件总结工具：获取未读邮件 → AI 生成摘要 → 发送到指定邮箱。

本教程以 **Gmail + DeepSeek** 为例。

## 环境要求

- Python 3.9+
- 一个 Gmail 邮箱（需开启 IMAP）
- 一个 DeepSeek API Key

## 安装与配置

以下流程以 **Gmail + DeepSeek** 为例。克隆项目后只需三步：运行脚本 → 获取密钥 → 填写配置。

### 第 1 步：一键安装

```bash
cd ~
git clone https://github.com/RichardHuang0001/email_summarizer.git
cd email_summarizer
bash start.sh
```

`start.sh` 会自动完成两件事：
- 安装 Python 依赖（`pip install -r requirements.txt`）
- 从模板创建 `config.yaml` 和 `.env`（已存在的不会覆盖）

### 第 2 步：获取密钥

**DeepSeek API Key：**

1. 打开 https://platform.deepseek.com/ 注册并登录
2. 右上角「API Keys」→「创建 API Key」
3. 复制 key（格式 `sk-xxxxxxxx`），稍后填入 `.env`

**Gmail 应用专用密码：**

> Gmail 不允许直接用登录密码连接第三方工具，必须生成「应用专用密码」。

1. 打开 https://myaccount.google.com/ 并登录
2. 进入「安全性」→ 先开启「两步验证」（已开启则跳过）
3. 在「安全性」页面搜索「应用专用密码」
4. 选择应用 = `邮件`，设备 = `其他（自定义名称）`，输入 `Email Summarizer`
5. 点击「生成」，复制 16 位密码（空格不需要删除），稍后填入 `.env`

> QQ / 163 / Outlook 用户：在邮箱设置中开启 IMAP/SMTP 获取授权码，然后改 `config.yaml` 的 `email.service`。

### 第 3 步：填写配置（5 个值）

打开 `config.yaml`，修改这 3 项：

```yaml
email:
  service: "GMAIL"                    # GMAIL / QQ / 163 / OUTLOOK
  username: "your_email@gmail.com"    # 改为你的邮箱地址
  notify_to: "your_email@example.com" # 接收总结报告的邮箱
```

打开 `.env`，修改这 2 项：

```bash
OPENAI_API_KEY="sk-xxxxxxxx"              # DeepSeek API Key
EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"      # Gmail 应用专用密码
```

### 配置检查清单

| 项目 | 位置 | 填了吗 |
|------|------|--------|
| 邮箱类型 | `config.yaml` → `email.service` | ☐ |
| 邮箱地址 | `config.yaml` → `email.username` | ☐ |
| 接收报告的邮箱 | `config.yaml` → `email.notify_to` | ☐ |
| API Key | `.env` → `OPENAI_API_KEY` | ☐ |
| 邮箱授权码 | `.env` → `EMAIL_PASSWORD` | ☐ |

## 运行

```bash
python main.py
```

运行时程序会自动检查配置，缺少任何必填项都会给出明确提示。

### 可选测试

```bash
python tests/test_llm.py    # 测试 LLM 连接是否正常
python tests/test_mail.py   # 测试邮箱连接是否正常
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--limit N` | 处理邮件数量上限 | config.yaml 中 `max_emails_per_run`（默认 20） |
| `--to` | 接收报告的邮箱（覆盖 config.yaml） | `email.notify_to` |
| `--subject` | 邮件标题 | `email.subject`（默认"今日邮件摘要"） |
| `--all` | 读取所有邮件而非仅未读 | 仅未读 |
| `--send-attachment` | 发送归档文件作为附件 | false |

### 配置终端快捷命令（MacOS / Linux）

配置之后，在终端任意位置输入 `email` 即可运行，无需每次 `cd` 到项目目录。

**原理**：在 shell 配置文件（`~/.zshrc`）中添加一行 alias（别名），将 `email` 映射为 `python ~/email_summarizer/main.py`。因为用了绝对路径，所以从任何目录都能找到脚本。命令行参数也会自动透传。

**设置方法**（复制整行到终端执行）：

```bash
echo 'alias email="python ~/email_summarizer/main.py"' >> ~/.zshrc && source ~/.zshrc
```

执行后立即生效。关闭终端重新打开也依然有效（因为写入了 `~/.zshrc`）。

**验证**：

```bash
email --help          # 应显示帮助信息
```

**使用示例**：

```bash
email                          # 使用默认配置运行
email --limit 5                # 只处理 5 封
email --subject "上午邮件速览"  # 自定义标题
email --all                    # 处理所有邮件（而非仅未读）
```

**移除**（如果以后不需要了）：

```bash
# 编辑 ~/.zshrc，删除包含 "alias email=" 的那一行，然后：
source ~/.zshrc
```

## 常见问题

**Q: 运行后提示「缺少 OPENAI_API_KEY」**

检查 `.env` 文件是否在项目根目录，内容格式：`OPENAI_API_KEY="sk-xxxx"`（带引号）。

**Q: 提示邮箱登录失败**

- Gmail：确认用了应用专用密码而非登录密码，确认已开启两步验证
- QQ/163：确认已在邮箱设置中开启 IMAP/SMTP 服务并获取了授权码

## 项目结构

```
├── start.sh                    # 一键安装脚本
├── main.py                     # 程序入口
├── config.yaml                 # 你的本地配置（不提交到 Git）
├── config_example/             # 配置文件模板
│   ├── config.example.yaml
│   └── .env.example
├── src/email_summarizer/       # 核心代码
│   ├── chain.py                # 邮件处理流程编排
│   ├── tools/                  # 邮箱读写工具
│   └── utils/                  # 配置加载、HTML 生成等
├── archive/                    # 归档文件
└── tests/                      # 测试脚本
```
