#!/bin/bash
# STS2 AI Advisor — 一键启动
# 用法: ./launch.sh 或 双击运行

PYTHON="/opt/homebrew/bin/python3.12"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
API_URL="http://localhost:15526/api/v1/singleplayer"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🗡️  STS2 AI Advisor"
echo "===================="

# 1. 检查依赖
echo -n "  Python 3.12... "
if [ -x "$PYTHON" ]; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ 未找到 $PYTHON${NC}"
    exit 1
fi

echo -n "  pywebview... "
$PYTHON -c "import webview" 2>/dev/null && echo -e "${GREEN}✅${NC}" || {
    echo -e "${YELLOW}安装中...${NC}"
    $PYTHON -m pip install pywebview -q --break-system-packages
}

echo -n "  requests... "
$PYTHON -c "import requests" 2>/dev/null && echo -e "${GREEN}✅${NC}" || {
    echo -e "${YELLOW}安装中...${NC}"
    $PYTHON -m pip install requests -q
}

echo -n "  Claude CLI... "
if [ -x "/opt/homebrew/bin/claude" ]; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️  未找到 (AI分析不可用，其他功能正常)${NC}"
fi

# 2. 检查知识库
echo -n "  知识库... "
KB_COUNT=$(ls "$PROJECT_DIR/knowledge/"*.json 2>/dev/null | wc -l | tr -d ' ')
KB_SIZE=$(du -sh "$PROJECT_DIR/knowledge/" 2>/dev/null | cut -f1 | tr -d ' ')
if [ "$KB_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ ${KB_COUNT}文件 ${KB_SIZE}${NC}"
else
    echo -e "${RED}❌ 知识库为空${NC}"
    exit 1
fi

# 3. 检查mod/API
echo -n "  STS2MCP mod... "
MOD_PATH="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/MacOS/mods/STS2_MCP.dll"
if [ -f "$MOD_PATH" ]; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ 未安装${NC}"
    echo "  请将STS2_MCP.dll放入游戏mods目录"
    exit 1
fi

# 检查Harmony是否被Steam更新覆盖
echo -n "  Harmony mod版... "
ARM_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
X86_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64"
MOD_HARMONY_SIZE=2119680

ARM_SIZE=$(stat -f%z "$ARM_DIR/0Harmony.dll" 2>/dev/null || echo 0)
if [ "$ARM_SIZE" != "$MOD_HARMONY_SIZE" ] && [ -f "$ARM_DIR/0Harmony.dll.bak" ]; then
    echo -e "${YELLOW}Steam更新覆盖了，自动恢复...${NC}"
    cp "$ARM_DIR/0Harmony.dll" "$ARM_DIR/0Harmony.dll.original"
    cp "$ARM_DIR/0Harmony.dll.bak" "$ARM_DIR/0Harmony.dll"
    if [ -f "$X86_DIR/0Harmony.dll.bak.dll" ]; then
        cp "$X86_DIR/0Harmony.dll" "$X86_DIR/0Harmony.dll.original"
        cp "$X86_DIR/0Harmony.dll.bak.dll" "$X86_DIR/0Harmony.dll"
    fi
    echo -e "  ${GREEN}✅ Harmony已恢复，请重启游戏${NC}"
else
    echo -e "${GREEN}✅${NC}"
fi

echo -n "  游戏API... "
if curl -s --connect-timeout 2 --max-time 5 "$API_URL" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 已连接${NC}"
else
    echo -e "${YELLOW}⏳ 等待游戏启动...${NC}"
    echo "  请启动杀戮尖塔2（需要开启mod）"
    echo "  检测到API后自动启动overlay"
    echo ""
    while true; do
        if curl -s --connect-timeout 1 --max-time 3 "$API_URL" >/dev/null 2>&1; then
            echo -e "  ${GREEN}✅ 游戏已连接！${NC}"
            break
        fi
        sleep 2
    done
fi

# 4. 启动overlay
echo ""
echo "🚀 启动 AI Advisor..."
echo "===================="
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"
exec $PYTHON "$SCRIPT_DIR/ai_advisor_app.py"
