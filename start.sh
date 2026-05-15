#!/usr/bin/env bash
# =====================================================
# 邮件总结工具 - 一键配置脚本
# 用法：bash start.sh
# =====================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}   邮件总结工具 - 一键配置${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# ---- 检查 Python ----
PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "错误：未找到 Python，请先安装 Python 3.9+"
    echo "下载地址：https://www.python.org/downloads/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python: $($PYTHON_BIN --version)"

# ---- 安装依赖 ----
echo ""
echo -e "${CYAN}→${NC} 安装 Python 依赖..."
$PYTHON_BIN -m pip install -r requirements.txt --quiet
echo -e "${GREEN}✓${NC} 依赖安装完成"

# ---- 复制配置模板 ----
echo ""
echo -e "${CYAN}→${NC} 创建配置文件..."

if [ ! -f config.yaml ]; then
    cp config_example/config.example.yaml config.yaml
    echo -e "${GREEN}✓${NC} 已创建 config.yaml"
else
    echo -e "${YELLOW}○${NC} config.yaml 已存在，跳过"
fi

if [ ! -f .env ]; then
    cp config_example/.env.example .env
    echo -e "${GREEN}✓${NC} 已创建 .env"
else
    echo -e "${YELLOW}○${NC} .env 已存在，跳过"
fi

# ---- 指引下一步 ----
echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}   配置文件已就绪！接下来请手动完成：${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""
echo -e "  ${BOLD}①${NC} 编辑 ${BOLD}config.yaml${NC}，修改 3 个值："
echo "     email.service   → 邮箱类型：GMAIL / QQ / 163 / OUTLOOK"
echo "     email.username  → 你的邮箱地址"
echo "     email.notify_to → 接收报告的目标邮箱"
echo ""
echo -e "  ${BOLD}②${NC} 编辑 ${BOLD}.env${NC}，修改 2 个值："
echo "     OPENAI_API_KEY  → AI 模型 API Key"
echo "     EMAIL_PASSWORD  → 邮箱授权码（非登录密码）"
echo ""
echo -e "  ${BOLD}详细步骤和 API Key / 授权码获取方法请参考 README.md${NC}"
echo ""
echo -e "  配置完成后运行: ${BOLD}python main.py${NC}"
echo ""
