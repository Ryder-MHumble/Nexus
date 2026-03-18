#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Information Crawler — Deploy & Manage
#  Usage:  ./deploy.sh [command] [options]
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PID_FILE="$PROJECT_DIR/.service.pid"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/server.log"
VERSION=$(grep '^version' "$PROJECT_DIR/pyproject.toml" 2>/dev/null \
    | head -1 | sed 's/.*"\(.*\)".*/\1/' || echo "0.0.0")

PORT=${NEXUS_PORT:-8001}
HOST=${NEXUS_HOST:-localhost}
WORKERS=1
TAIL_LINES=50
FOLLOW=false
PRODUCTION=false

# ── ANSI ──────────────────────────────────────────────────────
R='\033[0;31m';   G='\033[0;32m';  Y='\033[0;33m'
B='\033[0;34m';   M='\033[0;35m';  C='\033[0;36m'
W='\033[0;37m';   D='\033[0;90m';  BOLD='\033[1m'
BW='\033[1;97m';  BC='\033[1;36m'
BG_G='\033[42;30m'; BG_R='\033[41;37m'; BG_Y='\033[43;30m'; BG_B='\033[44;37m'
NC='\033[0m'
# 256-color gradient (violet → cyan)
P1='\033[38;5;57m'; P2='\033[38;5;63m'; P3='\033[38;5;69m'
P4='\033[38;5;75m'; P5='\033[38;5;81m'; P6='\033[38;5;87m'

# ── Utilities ─────────────────────────────────────────────────
_hr()  { printf "${D}"; printf '─%.0s' $(seq 1 60); printf "${NC}\n"; }
_pad() { printf "%-${1}s" "$2"; }

ok()   { printf " ${G}✓${NC}  %b\n" "$*"; }
warn() { printf " ${Y}!${NC}  %b\n" "$*"; }
fail() { printf " ${R}✗${NC}  %b\n" "$*"; }
dim()  { printf " ${D}%b${NC}\n" "$*"; }

spinner() {
    local pid=$1 msg="$2"
    local chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r ${C}%s${NC} %s" "${chars:i%10:1}" "$msg"
        i=$((i + 1))
        sleep 0.1
    done
    printf "\r\033[2K"
}

# ── Header ────────────────────────────────────────────────────
show_banner() {
    printf "\n"
    printf "  ${P1}${BOLD}██████╗ ███████╗ █████╗ ███╗   ██╗${NC}\n"
    printf "  ${P2}${BOLD}██╔══██╗██╔════╝██╔══██╗████╗  ██║${NC}\n"
    printf "  ${P3}${BOLD}██║  ██║█████╗  ███████║██╔██╗ ██║${NC}\n"
    printf "  ${P4}${BOLD}██║  ██║██╔══╝  ██╔══██║██║╚██╗██║${NC}\n"
    printf "  ${P5}${BOLD}██████╔╝███████╗██║  ██║██║ ╚████║${NC}\n"
    printf "  ${P6}${BOLD}╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝${NC}\n"
    printf "\n"
    printf "  ${P3}%s${NC}\n" "$(printf '%.0s═' {1..56})"
    printf "  ${P2}${BOLD}Nexus${NC} ${D}·${NC} ${D}Data Intelligence Platform — Backend Service${NC}\n"
    printf "  ${P3}%s${NC}\n" "$(printf '%.0s═' {1..56})"
    printf "\n"
    local _branch _py _time
    _branch=$(git branch --show-current 2>/dev/null || echo 'unknown')
    _py=$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo 'N/A')
    _time=$(date '+%Y-%m-%d  %H:%M:%S')
    printf "  ${D}TIME${NC}   ${BW}%s${NC}    ${D}PORT${NC}   ${BC}${BOLD}:%s${NC}\n" "$_time" "$PORT"
    printf "  ${D}BRANCH${NC} ${Y}%s${NC}          ${D}PYTHON${NC} ${G}%s${NC}\n" "$_branch" "$_py"
    printf "  ${D}HOST${NC}   ${D}${HOST}${NC}    ${D}v%s${NC}\n" "$VERSION"
    printf "\n"
    _hr
}

# ── Environment ───────────────────────────────────────────────
validate_python() {
    python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null
}

get_python_ver() {
    python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "?"
}

ensure_venv() {
    local create="${1:-false}"
    # Already active
    [[ -n "${VIRTUAL_ENV:-}" && "$VIRTUAL_ENV" == "$VENV_DIR" ]] && return 0
    # Exists — activate
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
        return 0
    fi
    # Create
    if [[ "$create" == "true" ]]; then
        python3 -m venv "$VENV_DIR" 2>/dev/null
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip -q 2>/dev/null
        return 0
    fi
    return 1
}

validate_env_file() {
    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        [[ -f "$PROJECT_DIR/.env.example" ]] && cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        return 0
    fi
    # Clean garbage from bad vim exits
    if grep -qE '^(exit\(\)|q|:q|:wq|:x)\s*$' "$PROJECT_DIR/.env" 2>/dev/null; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' '/^exit()$/d; /^q$/d; /^:q$/d; /^:wq$/d; /^:x$/d' "$PROJECT_DIR/.env"
        else
            sed -i '/^exit()$/d; /^q$/d; /^:q$/d; /^:wq$/d; /^:x$/d' "$PROJECT_DIR/.env"
        fi
    fi
}

has_env_key() { grep -q "${1}=.\+" "$PROJECT_DIR/.env" 2>/dev/null; }

install_deps() {
    cd "$PROJECT_DIR"
    pip install -e ".[dev]" -q 2>&1 | tail -1 &
    local pid=$!
    spinner $pid "Installing Python dependencies..."
    wait $pid 2>/dev/null
    return ${PIPESTATUS[0]:-0}
}

check_playwright() {
    python3 -c "
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
try:
    b = pw.chromium.launch(headless=True); b.close()
finally:
    pw.stop()
" 2>/dev/null
}

install_playwright() {
    playwright install chromium --with-deps 2>/dev/null &
    local pid=$!
    spinner $pid "Installing Playwright Chromium..."
    wait $pid 2>/dev/null || {
        playwright install chromium 2>/dev/null &
        pid=$!
        spinner $pid "Retrying Playwright install..."
        wait $pid 2>/dev/null
    }
}

ensure_dirs() {
    for d in data/raw \
        data/processed/{policy_intel,personnel_intel,tech_frontier,university_eco,daily_briefing} \
        data/state data/logs logs; do
        mkdir -p "$PROJECT_DIR/$d"
    done
}

# ── Git ───────────────────────────────────────────────────────
do_git_pull() {
    cd "$PROJECT_DIR"
    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        warn "Not a git repo — skipping pull"
        return 0
    fi
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    local before
    before=$(git rev-parse HEAD 2>/dev/null)

    printf " ${C}⟳${NC}  Pulling latest code ${D}(%s)${NC}..." "$branch"
    if git pull --ff-only -q 2>/dev/null; then
        local after
        after=$(git rev-parse HEAD 2>/dev/null)
        if [[ "$before" == "$after" ]]; then
            printf "\r ${G}✓${NC}  Code is up-to-date ${D}(%s)${NC}        \n" "$branch"
        else
            local count
            count=$(git rev-list "$before".."$after" --count 2>/dev/null || echo "?")
            printf "\r ${G}✓${NC}  Pulled ${BOLD}%s${NC} new commit(s) ${D}(%s)${NC}       \n" "$count" "$branch"
        fi
    else
        printf "\r ${Y}!${NC}  Pull failed — continuing with local code\n"
    fi
}

# ── Service ───────────────────────────────────────────────────
_is_running() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid; pid=$(cat "$PID_FILE")
    kill -0 "$pid" 2>/dev/null && return 0
    rm -f "$PID_FILE"
    return 1
}

_get_pid() { cat "$PID_FILE" 2>/dev/null || echo ""; }

_pids_on_port() { lsof -ti "tcp:$PORT" 2>/dev/null || true; }

_free_port() {
    local pids; pids=$(_pids_on_port)
    [[ -z "$pids" ]] && return 0
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 2
    pids=$(_pids_on_port)
    [[ -n "$pids" ]] && { echo "$pids" | xargs kill -9 2>/dev/null || true; sleep 1; }
    pids=$(_pids_on_port)
    [[ -n "$pids" ]] && { fail "Cannot free port $PORT"; return 1; }
    return 0
}

_stop_service() {
    if ! _is_running; then
        _free_port 2>/dev/null || true
        return 0
    fi
    local pid; pid=$(_get_pid)
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    local w=0
    while kill -0 "$pid" 2>/dev/null && [[ $w -lt 10 ]]; do sleep 1; w=$((w+1)); done
    kill -0 "$pid" 2>/dev/null && { kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true; }
    rm -f "$PID_FILE"
    _free_port 2>/dev/null || true
}

_start_service() {
    mkdir -p "$LOG_DIR"
    _free_port || return 1
    rm -f "$PID_FILE"

    local extra_args=()
    [[ "$PRODUCTION" != "true" && "$WORKERS" -eq 1 ]] && extra_args+=(--reload)

    cd "$PROJECT_DIR"
    nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app \
        --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" \
        ${extra_args[@]+"${extra_args[@]}"} >> "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    sleep 2
    kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_wait_health() {
    local max=30 i=0
    local chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    printf " ${C}⟳${NC} Waiting for health check..."
    while [[ $i -lt $max ]]; do
        if curl -sf "http://${HOST}:$PORT/api/v1/health/" >/dev/null 2>&1; then
            printf "\r ${G}✓${NC}  Health check passed           \n"
            return 0
        fi
        printf "\r ${C}%s${NC} Waiting for health check..." "${chars:i%10:1}"
        sleep 1
        i=$((i+1))
    done
    printf "\r ${Y}!${NC}  Health check timeout (%ss)     \n" "$max"
    return 1
}

# ── Dashboard ─────────────────────────────────────────────────
show_dashboard() {
    local pid etime cpu mem_kb mem_mb conns log_size
    printf "\n"
    printf " ${BOLD}${C}◆ Dashboard${NC}\n"
    _hr

    if _is_running; then
        pid=$(_get_pid)
        etime=$(ps -p "$pid" -o etime= 2>/dev/null | xargs || echo "-")
        cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | xargs || echo "-")
        mem_kb=$(ps -p "$pid" -o rss= 2>/dev/null | xargs || echo "0")
        mem_mb=$(echo "$mem_kb" | awk '{printf "%.1f", $1/1024}')
        conns=$(lsof -i "tcp:$PORT" 2>/dev/null | grep -c ESTABLISHED || echo "0")

        printf "\n"
        printf "   ${BOLD}SERVICE${NC}\n"
        printf "   %-18s ${G}● Running${NC}\n" "Status"
        printf "   %-18s %s\n" "PID" "$pid"
        printf "   %-18s %s\n" "Port" "$PORT"
        printf "   %-18s %s\n" "Uptime" "$etime"
        printf "\n"
        printf "   ${BOLD}RESOURCES${NC}\n"
        printf "   %-18s %s%%\n" "CPU" "$cpu"
        printf "   %-18s %s MB\n" "Memory" "$mem_mb"
        printf "   %-18s %s\n" "Connections" "$conns"

        if [[ -f "$LOG_FILE" ]]; then
            log_size=$(du -h "$LOG_FILE" | cut -f1 | xargs)
            printf "   %-18s %s\n" "Log size" "$log_size"
        fi

        # Pipeline status
        local pipe_json
        pipe_json=$(curl -sf "http://${HOST}:$PORT/api/v1/health/pipeline-status" 2>/dev/null) || pipe_json=""
        if [[ -n "$pipe_json" ]]; then
            printf "\n"
            printf "   ${BOLD}PIPELINE${NC}\n"
            echo "$pipe_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
st = d.get('status', 'unknown')
color = '32' if st == 'success' else ('33' if st == 'never_run' else '31')
icon = '●' if st == 'success' else ('○' if st == 'never_run' else '✗')
print(f'   Status             \033[{color}m{icon} {st}\033[0m')
dur = d.get('duration_seconds')
if dur: print(f'   Duration            {dur:.0f}s')
stages = d.get('stages', [])
if stages:
    ok = sum(1 for s in stages if s.get('status') == 'success')
    total = len(stages)
    print(f'   Stages              {ok}/{total} passed')
    for s in stages:
        si = '✓' if s['status'] == 'success' else ('⊘' if s['status'] == 'skipped' else '✗')
        sc = '32' if s['status'] == 'success' else ('90' if s['status'] == 'skipped' else '31')
        print(f'   \033[{sc}m{si}\033[0m {s[\"name\"]}')
" 2>/dev/null || dim "   (could not parse pipeline status)"
        fi

        # Processed data
        printf "\n"
        printf "   ${BOLD}DATA${NC}\n"
        local modules=("policy_intel:政策智能" "personnel_intel:人事情报" "tech_frontier:科技前沿" "university_eco:高校生态" "daily_briefing:每日简报")
        for entry in "${modules[@]}"; do
            local dname="${entry%%:*}" label="${entry##*:}"
            local dir="$PROJECT_DIR/data/processed/$dname"
            local cnt=0
            [[ -d "$dir" ]] && cnt=$(find "$dir" -name "*.json" -not -name "_*" 2>/dev/null | wc -l | tr -d ' ')
            if [[ $cnt -gt 0 ]]; then
                printf "   ${G}●${NC} %-14s %s files\n" "$label" "$cnt"
            else
                printf "   ${D}○${NC} %-14s ${D}empty${NC}\n" "$label"
            fi
        done

        # Endpoints
        printf "\n"
        printf "   ${BOLD}ENDPOINTS${NC}\n"
        printf "   ${D}Docs${NC}     http://${HOST}:%s/docs\n" "$PORT"
        printf "   ${D}Health${NC}   http://${HOST}:%s/api/v1/health/\n" "$PORT"
        printf "   ${D}Pipeline${NC} http://${HOST}:%s/api/v1/health/pipeline-status\n" "$PORT"
    else
        printf "\n"
        printf "   ${BOLD}SERVICE${NC}\n"
        printf "   %-18s ${R}● Stopped${NC}\n" "Status"
        if [[ -f "$LOG_FILE" ]]; then
            log_size=$(du -h "$LOG_FILE" | cut -f1 | xargs)
            printf "   %-18s %s\n" "Log size" "$log_size"
        fi
    fi

    printf "\n"
    _hr
}

# ── Pipeline Hint ─────────────────────────────────────────────
_check_pipeline_hint() {
    # Check if processed data is missing or stale (>24h)
    local feed="$PROJECT_DIR/data/processed/policy_intel/feed.json"
    if [[ ! -f "$feed" ]]; then
        printf "\n"
        warn "Processed data missing — Pipeline will auto-trigger on startup"
        dim "   Or trigger manually: curl -X POST http://${HOST}:$PORT/api/v1/health/pipeline-trigger"
        return
    fi

    # Check freshness: if feed.json is older than 24 hours
    local now file_ts age_hours
    now=$(date +%s)
    if [[ "$(uname)" == "Darwin" ]]; then
        file_ts=$(stat -f %m "$feed" 2>/dev/null || echo "$now")
    else
        file_ts=$(stat -c %Y "$feed" 2>/dev/null || echo "$now")
    fi
    age_hours=$(( (now - file_ts) / 3600 ))
    if [[ $age_hours -gt 24 ]]; then
        printf "\n"
        warn "Pipeline data is ${BOLD}${age_hours}h${NC}${Y} old — consider re-running:${NC}"
        dim "   curl -X POST http://${HOST}:$PORT/api/v1/health/pipeline-trigger"
    fi
}

# ── Commands ──────────────────────────────────────────────────
cmd_deploy() {
    PRODUCTION=true
    show_banner

    printf "\n ${BOLD}${C}◆ Deploy${NC}\n"
    _hr
    printf "\n"

    # 1. Git pull
    do_git_pull

    # 2. Python
    if validate_python; then
        ok "Python $(get_python_ver)"
    else
        fail "Python >= 3.11 required (found $(get_python_ver))"
        return 1
    fi

    # 3. Venv
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        ensure_venv true
        ok "Virtual environment ${D}.venv${NC}"
    else
        ensure_venv true
        ok "Virtual environment ${D}.venv (created)${NC}"
    fi

    # 4. .env
    validate_env_file
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        ok "Environment file ${D}.env${NC}"
        if has_env_key "OPENROUTER_API_KEY"; then
            dim "   OPENROUTER_API_KEY configured"
        else
            warn "OPENROUTER_API_KEY not set — LLM enrichment disabled"
        fi
        if has_env_key "TWITTER_API_KEY"; then
            dim "   TWITTER_API_KEY configured"
        else
            warn "TWITTER_API_KEY not set — Twitter sources disabled"
        fi
    else
        fail "No .env file"
        return 1
    fi

    # 5. Dependencies
    local t0; t0=$(date +%s)
    if install_deps; then
        ok "Dependencies installed ${D}$(($(date +%s) - t0))s${NC}"
    else
        fail "pip install failed"
        return 1
    fi

    # 6. Directories
    ensure_dirs
    ok "Data directories"

    # 7. Service
    printf "\n"
    if _is_running; then
        local old_pid; old_pid=$(_get_pid)
        printf " ${Y}⟳${NC}  Restarting service ${D}(was PID %s)${NC}...\n" "$old_pid"
        _stop_service
        sleep 1
    fi

    if _start_service; then
        ok "Service started ${D}PID $(cat "$PID_FILE")${NC}"
    else
        fail "Service failed to start — check logs/$LOG_FILE"
        return 1
    fi

    # 9. Health
    _wait_health || true

    # Dashboard
    show_dashboard

    # Check if pipeline data might be stale
    _check_pipeline_hint

    printf " ${G}${BOLD}Deploy complete.${NC}\n\n"
    dim "  ./deploy.sh status    View dashboard"
    dim "  ./deploy.sh logs -f   Follow logs"
    dim "  ./deploy.sh stop      Stop service"
    printf "\n"
}

cmd_init() {
    show_banner

    printf "\n ${BOLD}${C}◆ Initialize${NC}\n"
    _hr
    printf "\n"

    if validate_python; then
        ok "Python $(get_python_ver)"
    else
        fail "Python >= 3.11 required"; return 1
    fi

    ensure_venv true
    ok "Virtual environment"

    validate_env_file
    ok "Environment file"

    local t0; t0=$(date +%s)
    install_deps && ok "Dependencies ${D}$(($(date +%s) - t0))s${NC}" || fail "pip install failed"

    if check_playwright; then
        ok "Playwright Chromium"
    else
        install_playwright
        check_playwright && ok "Playwright Chromium" || warn "Playwright unavailable"
    fi

    ensure_dirs
    ok "Data directories"

    printf "\n"
    _hr
    printf "\n ${G}${BOLD}Init complete.${NC} Next:\n\n"
    dim "  vi .env               Edit config"
    dim "  ./deploy.sh           Full deploy"
    dim "  ./deploy.sh start     Start only"
    printf "\n"
}

cmd_start() {
    show_banner

    if ! ensure_venv; then
        fail "No virtual environment. Run: ./deploy.sh init"
        return 1
    fi

    if _is_running; then
        warn "Already running (PID $(_get_pid))"
        show_dashboard
        return 0
    fi

    PRODUCTION=true
    printf " ${C}⟳${NC}  Starting service...\n"

    if _start_service; then
        ok "Service started ${D}PID $(cat "$PID_FILE")${NC}"
        _wait_health || true
        show_dashboard
    else
        fail "Failed to start — check $LOG_FILE"
    fi
}

cmd_stop() {
    show_banner

    if ! _is_running; then
        local orphans; orphans=$(_pids_on_port)
        if [[ -n "$orphans" ]]; then
            warn "No PID file, but port $PORT occupied"
            _free_port
            ok "Port freed"
        else
            dim "Service is not running."
        fi
        return 0
    fi

    local pid; pid=$(_get_pid)
    printf " ${C}⟳${NC}  Stopping service (PID %s)...\n" "$pid"
    _stop_service
    ok "Service stopped"
}

cmd_restart() {
    show_banner

    if ! ensure_venv; then
        fail "No virtual environment. Run: ./deploy.sh init"
        return 1
    fi

    PRODUCTION=true

    if _is_running; then
        local pid; pid=$(_get_pid)
        printf " ${C}⟳${NC}  Restarting (PID %s)...\n" "$pid"
        _stop_service
        sleep 1
    fi

    if _start_service; then
        ok "Service started ${D}PID $(cat "$PID_FILE")${NC}"
        _wait_health || true
        show_dashboard
    else
        fail "Failed to start — check $LOG_FILE"
    fi
}

cmd_status() {
    show_banner
    show_dashboard
}

cmd_logs() {
    if [[ ! -f "$LOG_FILE" ]]; then
        warn "Log file not found: $LOG_FILE"
        return 0
    fi
    if [[ "$FOLLOW" == "true" ]]; then
        dim "Tailing $LOG_FILE (Ctrl+C to stop)"
        printf "\n"
        tail -n "$TAIL_LINES" -f "$LOG_FILE"
    else
        tail -n "$TAIL_LINES" "$LOG_FILE"
    fi
}

cmd_crawl() {
    show_banner

    printf "\n ${BOLD}${C}◆ Data Crawling${NC}\n"
    _hr
    printf "\n"

    if ! ensure_venv; then
        fail "No virtual environment. Run: ./deploy.sh init"
        return 1
    fi

    local dimension="${1:-}"
    local concurrency="${2:-4}"

    if [[ -z "$dimension" ]] || [[ "$dimension" == "all" ]]; then
        printf " ${C}⟳${NC}  Running crawler for all dimensions...\n"
        cd "$PROJECT_DIR"
        python3 scripts/crawl/run_all.py --concurrency "$concurrency"
    else
        printf " ${C}⟳${NC}  Running crawler for dimension: ${BOLD}%s${NC}\n" "$dimension"
        cd "$PROJECT_DIR"
        python3 scripts/crawl/run_all.py --dimension "$dimension" --concurrency "$concurrency"
    fi

    printf "\n"
    if [[ $? -eq 0 ]]; then
        ok "Crawl completed successfully"
    else
        fail "Crawl failed — check logs"
        return 1
    fi
}

cmd_crawl_single() {
    show_banner

    printf "\n ${BOLD}${C}◆ Single Source Crawl${NC}\n"
    _hr
    printf "\n"

    if ! ensure_venv; then
        fail "No virtual environment. Run: ./deploy.sh init"
        return 1
    fi

    local source_id="${1:-}"
    if [[ -z "$source_id" ]]; then
        fail "Source ID required. Usage: ./deploy.sh crawl-single <source_id>"
        return 1
    fi

    printf " ${C}⟳${NC}  Running crawler for source: ${BOLD}%s${NC}\n" "$source_id"
    cd "$PROJECT_DIR"
    python3 scripts/crawl/run_single.py --source "$source_id"

    printf "\n"
    if [[ $? -eq 0 ]]; then
        ok "Crawl completed successfully"
    else
        fail "Crawl failed — check logs"
        return 1
    fi
}

cmd_api_usage() {
    show_banner

    printf "\n ${BOLD}${C}◆ LLM API Usage${NC}\n"
    _hr
    printf "\n"

    if ! ensure_venv; then
        fail "No virtual environment. Run: ./deploy.sh init"
        return 1
    fi

    local stats_file="$PROJECT_DIR/data/state/llm_api_stats.json"

    if [[ ! -f "$stats_file" ]]; then
        warn "No API usage stats found yet"
        dim "   Stats will be recorded in: $stats_file"
        printf "\n"
        return 0
    fi

    printf " ${BOLD}API Usage Statistics${NC}\n"
    _hr

    cd "$PROJECT_DIR"
    python3 << 'PYEOF'
import json
from pathlib import Path
from collections import defaultdict

stats_file = Path("data/state/llm_api_stats.json")
if not stats_file.exists():
    print(" ⊘  No stats file found")
else:
    try:
        with open(stats_file, encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            print(" ⊘  No stats recorded yet")
        else:
            # Summary by provider
            by_provider = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0})
            total_cost = 0
            total_calls = 0

            for entry in data.get("calls", []):
                provider = entry.get("provider", "unknown")
                calls = by_provider[provider]
                calls["calls"] += 1
                calls["tokens"] += entry.get("total_tokens", 0)
                calls["cost"] += entry.get("cost_usd", 0)
                total_cost += entry.get("cost_usd", 0)
                total_calls += 1

            # Print summary
            print(f"\n   Total Calls:     {total_calls}")
            print(f"   Total Cost:      ${total_cost:.4f} USD\n")

            print("   By Provider:")
            for provider in sorted(by_provider.keys()):
                stats = by_provider[provider]
                print(f"   • {provider:<20} {stats['calls']:>4} calls | {stats['tokens']:>8} tokens | ${stats['cost']:>8.4f}")

            # Recent calls
            recent = sorted(data.get("calls", []), key=lambda x: x.get("timestamp", ""), reverse=True)[:5]
            if recent:
                print("\n   Recent Calls (Last 5):")
                for call in recent:
                    ts = call.get("timestamp", "?")[:10]
                    model = call.get("model", "?")
                    cost = call.get("cost_usd", 0)
                    print(f"   • {ts} | {model:<25} | ${cost:>8.4f}")

            print()
    except json.JSONDecodeError:
        print(" ✗  Invalid JSON in stats file")
    except Exception as e:
        print(f" ✗  Error reading stats: {e}")

PYEOF

    printf "\n"
}

cmd_help() {
    show_banner
    printf " ${BOLD}Usage${NC}  ./deploy.sh ${D}[command] [options]${NC}\n\n"

    printf " ${BOLD}Commands${NC}\n\n"
    printf "   ${G}deploy${NC}        Full deploy: pull → venv → deps → start  ${D}(default)${NC}\n"
    printf "   ${G}init${NC}          Initialize environment only\n"
    printf "   ${G}start${NC}         Start service\n"
    printf "   ${G}stop${NC}          Stop service\n"
    printf "   ${G}restart${NC}       Restart service\n"
    printf "   ${G}status${NC}        Show dashboard\n"
    printf "   ${G}logs${NC}          View logs ${D}(-f to follow)${NC}\n"
    printf "   ${G}crawl${NC}         Run data crawler {{all|dimension_name}} {{concurrency}}\n"
    printf "   ${G}crawl-single${NC}  Run single source crawler {{source_id}}\n"
    printf "   ${G}api-usage${NC}     View LLM API usage statistics\n"
    printf "   ${G}help${NC}          This message\n"

    printf "\n ${BOLD}Options${NC}\n\n"
    printf "   --port N          Listen port ${D}(default: %s)${NC}\n" "$PORT"
    printf "   --workers N       Worker count ${D}(default: %s)${NC}\n" "$WORKERS"
    printf "   --production      Disable auto-reload\n"
    printf "   --tail N          Log lines ${D}(default: %s)${NC}\n" "$TAIL_LINES"
    printf "   -f, --follow      Follow log output\n"

    printf "\n ${BOLD}Examples${NC}\n\n"
    printf "   ${D}\$${NC} ./deploy.sh              ${D}# one-command deploy${NC}\n"
    printf "   ${D}\$${NC} ./deploy.sh logs -f       ${D}# follow logs${NC}\n"
    printf "   ${D}\$${NC} ./deploy.sh status         ${D}# view dashboard${NC}\n"
    printf "   ${D}\$${NC} ./deploy.sh crawl all      ${D}# crawl all dimensions${NC}\n"
    printf "   ${D}\$${NC} ./deploy.sh crawl university_faculty 2  {{D}# crawl faculty with concurrency 2${NC}\n"
    printf "   ${D}\$${NC} ./deploy.sh crawl-single tsinghua_cs_faculty  {{D}# crawl single source${NC}\n"
    printf "   ${D}\$${NC} ./deploy.sh api-usage      {{D}# view API usage stats${NC}\n"
    printf "\n"
}

# ── Parse Args ────────────────────────────────────────────────
COMMAND="${1:-deploy}"
shift 2>/dev/null || true

# Separate positional args from flags for crawl commands
declare -a POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)       PORT="$2"; shift 2 ;;
        --workers)    WORKERS="$2"; shift 2 ;;
        --tail)       TAIL_LINES="$2"; shift 2 ;;
        --follow|-f)  FOLLOW=true; shift ;;
        --production) PRODUCTION=true; shift ;;
        -*)           fail "Unknown option: $1"; cmd_help; exit 1 ;;
        *)            POSITIONAL_ARGS+=("$1"); shift ;;
    esac
done

case "$COMMAND" in
    deploy)         cmd_deploy ;;
    init)           cmd_init ;;
    start)          cmd_start ;;
    stop)           cmd_stop ;;
    restart)        cmd_restart ;;
    status)         cmd_status ;;
    logs)           cmd_logs ;;
    crawl)          cmd_crawl "${POSITIONAL_ARGS[0]:-}" "${POSITIONAL_ARGS[1]:-4}" ;;
    crawl-single)   cmd_crawl_single "${POSITIONAL_ARGS[0]:-}" ;;
    api-usage)      cmd_api_usage ;;
    help|--help|-h) cmd_help ;;
    *)              fail "Unknown: $COMMAND"; cmd_help; exit 1 ;;
esac
