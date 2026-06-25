#!/usr/bin/env bash
# 本地开发启动脚本：同时启动前后端
# 用法：
#   ./dev.sh          启动前后端
#   ./dev.sh backend  只启后端
#   ./dev.sh frontend 只启前端
#   ./dev.sh stop     停止
#   ./dev.sh restart  重启
#   ./dev.sh docker   用 Docker 启动
#   ./dev.sh status   查看运行状态
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOG_DIR="$ROOT/.dev-logs"
mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[dev]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    warn "未找到命令：$1"
    return 1
  fi
  return 0
}

start_backend() {
  log "启动后端（FastAPI :8000）..."
  cd "$BACKEND"

  if [ ! -d "venv" ]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv venv
  fi

  source venv/bin/activate
  pip install -q -r requirements.txt 2>/dev/null || warn "依赖安装失败，请手动检查 backend/venv"

  nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$LOG_DIR/backend.pid"
  log "后端已启动（PID: $(cat "$LOG_DIR/backend.pid")）日志：$LOG_DIR/backend.log"
  deactivate 2>/dev/null || true
}

start_frontend() {
  log "启动前端（Nuxt :3000）..."
  cd "$FRONTEND"

  if [ ! -d "node_modules" ]; then
    log "安装前端依赖..."
    npm install --no-audit --no-fund
  fi

  nohup npm run dev -- --host 0.0.0.0 --port 3000 > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$LOG_DIR/frontend.pid"
  log "前端已启动（PID: $(cat "$LOG_DIR/frontend.pid")）日志：$LOG_DIR/frontend.log"
}

stop_all() {
  for name in backend frontend; do
    pidfile="$LOG_DIR/$name.pid"
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        log "已停止 $name（PID: $pid）"
      fi
      rm -f "$pidfile"
    fi
  done
  for port in 8000 3000; do
    pids=$(lsof -ti :$port 2>/dev/null) || true
    if [ -n "$pids" ]; then
      echo "$pids" | xargs kill 2>/dev/null || true
      sleep 1
      lsof -ti :$port 2>/dev/null | xargs kill -9 2>/dev/null || true
    fi
  done
  log "已清理"
}

start_docker() {
  log "用 Docker Compose 启动..."
  cd "$ROOT"
  docker compose up -d --build
  log "前端: http://localhost:3000"
  log "后端: http://localhost:8000  文档: http://localhost:8000/docs"
}

show_status() {
  for name in backend frontend; do
    pidfile="$LOG_DIR/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      log "$name 运行中（PID: $(cat "$pidfile")）"
    else
      warn "$name 未运行"
    fi
  done
}

case "${1:-all}" in
  backend)
    check_cmd python3 || exit 1
    start_backend
    log "后端: http://localhost:8000  文档: http://localhost:8000/docs"
    ;;
  frontend)
    check_cmd npm || { warn "需要 npm"; exit 1; }
    start_frontend
    log "前端: http://localhost:3000"
    ;;
  all|"")
    check_cmd python3 || exit 1
    check_cmd npm || exit 1
    start_backend
    sleep 2
    start_frontend
    echo ""
    log "========================================="
    log " 前端: ${CYAN}http://localhost:3000${NC}"
    log " 后端: ${CYAN}http://localhost:8000${NC}"
    log " 文档: ${CYAN}http://localhost:8000/docs${NC}"
    log " 日志: $LOG_DIR/{backend,frontend}.log"
    log " 停止: ./dev.sh stop"
    log "========================================="
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    sleep 1
    check_cmd python3 || exit 1
    check_cmd npm || exit 1
    start_backend
    sleep 2
    start_frontend
    log "前端: http://localhost:3000  后端: http://localhost:8000"
    ;;
  docker)
    check_cmd docker || { warn "需要 docker"; exit 1; }
    start_docker
    ;;
  status)
    show_status
    ;;
  *)
    echo "用法: ./dev.sh [backend|frontend|all|stop|docker|status]"
    echo "  无参数 / all      同时启动前后端"
    echo "  backend          只启动后端"
    echo "  frontend         只启动前端"
    echo "  stop             停止所有"
    echo "  docker           用 Docker Compose 启动"
    echo "  status           查看运行状态"
    exit 1
    ;;
esac
