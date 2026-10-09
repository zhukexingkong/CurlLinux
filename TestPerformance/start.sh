#!/bin/bash
# TestPerformance 启动脚本
#
# 用法:
#   ./start.sh              # 默认启动，端口 5000
#   ./start.sh 8080         # 指定端口 8080
#   ./start.sh 8080 -d      # 指定端口 8080，调试模式
#   ./start.sh stop         # 停止服务

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.server.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 停止服务函数
stop_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}Stopping TestPerformance server (PID: $PID)...${NC}"
            kill "$PID"
            sleep 2
            if kill -0 "$PID" 2>/dev/null; then
                echo -e "${RED}Force killing server...${NC}"
                kill -9 "$PID"
            fi
            rm -f "$PID_FILE"
            echo -e "${GREEN}Server stopped.${NC}"
        else
            echo -e "${YELLOW}Server is not running (stale PID file).${NC}"
            rm -f "$PID_FILE"
        fi
    else
        echo -e "${YELLOW}No PID file found. Server may not be running.${NC}"
    fi
    exit 0
}

# 处理 stop 参数
if [ "$1" = "stop" ]; then
    stop_server
fi

# 检查 Python 环境
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    exit 1
fi

# 安装依赖
if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip3 install -r "$SCRIPT_DIR/requirements.txt"
fi

# 解析参数
PORT=${1:-5000}
DEBUG_FLAG=""
if [ "$2" = "-d" ] || [ "$2" = "--debug" ]; then
    DEBUG_FLAG="--debug"
fi

# 如果已有服务在运行，先停止
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "${YELLOW}Stopping existing server (PID: $OLD_PID)...${NC}"
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# 启动服务
echo -e "${GREEN}Starting TestPerformance server on port $PORT...${NC}"
cd "$SCRIPT_DIR"
nohup python3 app.py -p "$PORT" $DEBUG_FLAG > "$SCRIPT_DIR/server.log" 2>&1 &
echo $! > "$PID_FILE"

sleep 2
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo -e "${GREEN}Server started successfully (PID: $(cat "$PID_FILE"))${NC}"
    echo -e "  Log file: $SCRIPT_DIR/server.log"
    echo -e "  Stop:     $0 stop"
    echo -e ""
    echo -e "${GREEN}Quick test:${NC}"
    echo -e "  curl http://localhost:$PORT/api/status"
    echo -e "  curl http://localhost:$PORT/api/ufs/usage"
    echo -e "  curl http://localhost:$PORT/api/dram/usage"
else
    echo -e "${RED}Server failed to start. Check $SCRIPT_DIR/server.log${NC}"
    rm -f "$PID_FILE"
    exit 1
fi
