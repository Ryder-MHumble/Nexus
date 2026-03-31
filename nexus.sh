#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
FRONTEND_DIR="$PROJECT_DIR/frontend"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/.pids"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"

BACKEND_PORT="${NEXUS_BACKEND_PORT:-43817}"
FRONTEND_PORT="${NEXUS_FRONTEND_PORT:-43819}"

FOLLOW_LOGS=false
TAIL_LINES=80

R='\033[0;31m'
G='\033[0;32m'
Y='\033[0;33m'
C='\033[0;36m'
D='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m'

ok() { printf " ${G}✓${NC} %b\n" "$*"; }
warn() { printf " ${Y}!${NC} %b\n" "$*"; }
fail() { printf " ${R}✗${NC} %b\n" "$*"; }
note() { printf " ${D}%b${NC}\n" "$*"; }
hr() { printf "${D}"; printf '─%.0s' $(seq 1 64); printf "${NC}\n"; }

banner() {
    printf "\n"
    printf " ${C}${BOLD}Nexus Unified Service Runner${NC}\n"
    hr
    printf " ${D}API${NC}      http://localhost:%s\n" "$BACKEND_PORT"
    printf " ${D}Docs${NC}     http://localhost:%s/docs\n" "$BACKEND_PORT"
    printf " ${D}Swagger${NC}  http://localhost:%s/swagger\n" "$BACKEND_PORT"
    printf " ${D}Frontend${NC} http://localhost:%s\n" "$FRONTEND_PORT"
    printf " ${D}Logs${NC}     %s\n" "$LOG_DIR"
    hr
}

ensure_dirs() {
    mkdir -p "$LOG_DIR" "$PID_DIR"
}

pid_is_running() {
    local pid="$1"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
    local pid_file="$1"
    if [[ -f "$pid_file" ]]; then
        cat "$pid_file"
    fi
}

port_listener_pid() {
    local port="$1"
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

warn_unmanaged_listener() {
    local pid_file="$1"
    local name="$2"
    local port="$3"
    local pid listener_pid
    pid="$(read_pid "$pid_file")"
    listener_pid="$(port_listener_pid "$port")"

    if [[ -n "$listener_pid" ]] && [[ "$listener_pid" != "$pid" ]]; then
        warn "$name port $port is still occupied by unmanaged PID $listener_pid; leaving it untouched"
    fi
}

ensure_backend_env() {
    if [[ ! -f "$VENV_DIR/bin/python" ]]; then
        note "Creating backend virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    if ! "$VENV_DIR/bin/python" -c "import fastapi, uvicorn, multipart" >/dev/null 2>&1; then
        note "Installing backend dependencies..."
        "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
        "$VENV_DIR/bin/pip" install -e ".[dev]" >/dev/null
        "$VENV_DIR/bin/pip" install python-multipart >/dev/null
    fi
}

ensure_frontend_env() {
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        note "Installing frontend dependencies..."
        (cd "$FRONTEND_DIR" && npm install >/dev/null)
    fi
}

stop_pid_file() {
    local pid_file="$1"
    local name="$2"
    local pid
    pid="$(read_pid "$pid_file")"

    if [[ -z "$pid" ]]; then
        return 0
    fi

    if pid_is_running "$pid"; then
        kill "$pid" 2>/dev/null || true
        sleep 1
        if pid_is_running "$pid"; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        ok "$name stopped (PID $pid)"
    fi
    rm -f "$pid_file"
}

start_backend() {
    local existing_pid pid_on_port
    existing_pid="$(read_pid "$BACKEND_PID_FILE")"
    if [[ -n "$existing_pid" ]] && pid_is_running "$existing_pid"; then
        ok "Backend already running (PID $existing_pid)"
        return 0
    fi
    rm -f "$BACKEND_PID_FILE"

    pid_on_port="$(port_listener_pid "$BACKEND_PORT")"
    if [[ -n "$pid_on_port" ]]; then
        warn "Backend port $BACKEND_PORT is already in use (PID $pid_on_port), skip starting backend"
        return 0
    fi

    ensure_backend_env
    (
        cd "$PROJECT_DIR"
        nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app \
            --host 0.0.0.0 --port "$BACKEND_PORT" --reload >> "$BACKEND_LOG_FILE" 2>&1 &
        echo $! > "$BACKEND_PID_FILE"
    )
    sleep 2

    local pid
    pid="$(read_pid "$BACKEND_PID_FILE")"
    if [[ -n "$pid" ]] && pid_is_running "$pid"; then
        ok "Backend started (PID $pid)"
    else
        fail "Backend failed to start. Check: $BACKEND_LOG_FILE"
        return 1
    fi
}

start_frontend() {
    local existing_pid pid_on_port
    existing_pid="$(read_pid "$FRONTEND_PID_FILE")"
    if [[ -n "$existing_pid" ]] && pid_is_running "$existing_pid"; then
        ok "Frontend already running (PID $existing_pid)"
        return 0
    fi
    rm -f "$FRONTEND_PID_FILE"

    pid_on_port="$(port_listener_pid "$FRONTEND_PORT")"
    if [[ -n "$pid_on_port" ]]; then
        warn "Frontend port $FRONTEND_PORT is already in use (PID $pid_on_port), skip starting frontend"
        return 0
    fi

    ensure_frontend_env
    (
        cd "$FRONTEND_DIR"
        NEXT_PUBLIC_API_BASE_URL="http://localhost:$BACKEND_PORT/api/v1" \
        PORT="$FRONTEND_PORT" \
        nohup npm run dev >> "$FRONTEND_LOG_FILE" 2>&1 &
        echo $! > "$FRONTEND_PID_FILE"
    )
    sleep 2

    local pid
    pid="$(read_pid "$FRONTEND_PID_FILE")"
    if [[ -n "$pid" ]] && pid_is_running "$pid"; then
        ok "Frontend started (PID $pid)"
    else
        fail "Frontend failed to start. Check: $FRONTEND_LOG_FILE"
        return 1
    fi
}

start_all() {
    banner
    ensure_dirs
    start_backend
    start_frontend
    printf "\n"
    status_all
}

stop_backend() {
    stop_pid_file "$BACKEND_PID_FILE" "Backend"
    warn_unmanaged_listener "$BACKEND_PID_FILE" "Backend" "$BACKEND_PORT"
}

stop_frontend() {
    stop_pid_file "$FRONTEND_PID_FILE" "Frontend"
    warn_unmanaged_listener "$FRONTEND_PID_FILE" "Frontend" "$FRONTEND_PORT"
}

stop_all() {
    banner
    stop_frontend
    stop_backend
    ok "Tracked Nexus services stopped"
}

status_line() {
    local name="$1"
    local pid_file="$2"
    local port="$3"
    local url="$4"
    local pid port_pid
    pid="$(read_pid "$pid_file")"
    port_pid="$(port_listener_pid "$port")"
    if [[ -n "$pid" ]] && pid_is_running "$pid"; then
        printf " %-10s ${G}RUNNING${NC}  pid=%s  port=%s  %s\n" "$name" "$pid" "$port" "$url"
    elif [[ -n "$port_pid" ]]; then
        printf " %-10s ${Y}PORT-IN-USE${NC} pid=%s  port=%s  %s\n" "$name" "$port_pid" "$port" "$url"
    else
        printf " %-10s ${R}STOPPED${NC}  pid=-      port=%s  %s\n" "$name" "$port" "$url"
    fi
}

status_all() {
    banner
    status_line "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT" "http://localhost:$BACKEND_PORT/docs"
    status_line "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT" "http://localhost:$FRONTEND_PORT"
}

logs_backend() {
    if [[ ! -f "$BACKEND_LOG_FILE" ]]; then
        warn "No backend log file at $BACKEND_LOG_FILE"
        return 0
    fi
    if [[ "$FOLLOW_LOGS" == "true" ]]; then
        tail -n "$TAIL_LINES" -f "$BACKEND_LOG_FILE"
    else
        tail -n "$TAIL_LINES" "$BACKEND_LOG_FILE"
    fi
}

logs_frontend() {
    if [[ ! -f "$FRONTEND_LOG_FILE" ]]; then
        warn "No frontend log file at $FRONTEND_LOG_FILE"
        return 0
    fi
    if [[ "$FOLLOW_LOGS" == "true" ]]; then
        tail -n "$TAIL_LINES" -f "$FRONTEND_LOG_FILE"
    else
        tail -n "$TAIL_LINES" "$FRONTEND_LOG_FILE"
    fi
}

logs_all() {
    note "Backend log: $BACKEND_LOG_FILE"
    logs_backend
    printf "\n"
    note "Frontend log: $FRONTEND_LOG_FILE"
    logs_frontend
}

show_help() {
    banner
    cat <<EOF
Usage:
  ./nexus.sh [command] [target] [options]

Commands:
  start [all|backend|frontend]    Start services (default: all)
  stop [all|backend|frontend]     Stop services
  restart [all|backend|frontend]  Restart services
  status                           Show service status
  logs [all|backend|frontend]      Show logs
  help                             Show this help

Options:
  -f, --follow   Follow logs (for logs command)
  --tail N       Show last N lines in logs (default: 80)

Examples:
  ./nexus.sh
  ./nexus.sh start
  ./nexus.sh restart all
  ./nexus.sh stop frontend
  ./nexus.sh logs backend -f
EOF
}

COMMAND="${1:-start}"
TARGET="${2:-all}"
shift $(( $# > 0 ? 1 : 0 )) || true
if [[ $# -gt 0 ]]; then
    shift $(( $# > 0 ? 1 : 0 )) || true
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--follow) FOLLOW_LOGS=true; shift ;;
        --tail) TAIL_LINES="${2:-80}"; shift 2 ;;
        *) warn "Unknown option: $1"; show_help; exit 1 ;;
    esac
done

case "$COMMAND" in
    start)
        case "$TARGET" in
            all) start_all ;;
            backend) banner; ensure_dirs; start_backend ;;
            frontend) banner; ensure_dirs; start_frontend ;;
            *) fail "Unknown target: $TARGET"; exit 1 ;;
        esac
        ;;
    stop)
        case "$TARGET" in
            all) stop_all ;;
            backend) banner; stop_backend ;;
            frontend) banner; stop_frontend ;;
            *) fail "Unknown target: $TARGET"; exit 1 ;;
        esac
        ;;
    restart)
        case "$TARGET" in
            all) stop_all; start_all ;;
            backend) banner; stop_backend; start_backend ;;
            frontend) banner; stop_frontend; start_frontend ;;
            *) fail "Unknown target: $TARGET"; exit 1 ;;
        esac
        ;;
    status)
        status_all
        ;;
    logs)
        case "$TARGET" in
            all) logs_all ;;
            backend) logs_backend ;;
            frontend) logs_frontend ;;
            *) fail "Unknown target: $TARGET"; exit 1 ;;
        esac
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        fail "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac
