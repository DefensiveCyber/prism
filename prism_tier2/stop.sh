#!/usr/bin/env bash
# =============================================================================
#  PRISM — Stop all services
#  Usage:
#    ./stop.sh            — stop PRISM services (Redis + PostgreSQL keep running)
#    ./stop.sh --shutdown — stop everything and shut down WSL2
# =============================================================================

PRISM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PRISM_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
info() { echo -e "  ${CYAN}→${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }

SHUTDOWN=false
for arg in "$@"; do [ "$arg" = "--shutdown" ] && SHUTDOWN=true; done

echo ""
if $SHUTDOWN; then
    echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║   PRISM  —  Full Shutdown                    ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
else
    echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║   PRISM  —  Stopping Services                ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
fi
echo ""

# ── Helper ─────────────────────────────────────────────────────────────────────
stop_service() {
    local name="$1" pidfile="$2" pattern="$3"
    if [ -f "$pidfile" ]; then
        local pid; pid=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null
            for i in $(seq 1 10); do
                kill -0 "$pid" 2>/dev/null || break; sleep 0.5
            done
            kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
    if [ -n "$pattern" ]; then
        local pids; pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
            sleep 1
            pids=$(pgrep -f "$pattern" 2>/dev/null || true)
            [ -n "$pids" ] && echo "$pids" | xargs kill -KILL 2>/dev/null || true
        fi
    fi
    ok "$name stopped"
}

# ── PRISM services ─────────────────────────────────────────────────────────────
info "Stopping Gunicorn..."
stop_service "Gunicorn"       "logs/gunicorn.pid"        "gunicorn.*server:app"
sudo fuser -k 5000/tcp > /dev/null 2>&1 || true

info "Stopping Celery workers..."
stop_service "Celery priority" "logs/celery_priority.pid" "celery.*worker.*priority"
stop_service "Celery classify" "logs/celery_classify.pid" "celery.*worker.*classify"
remaining=$(pgrep -f "celery.*celery_app" 2>/dev/null || true)
if [ -n "$remaining" ]; then
    echo "$remaining" | xargs kill -TERM 2>/dev/null || true
    sleep 1
    remaining=$(pgrep -f "celery.*celery_app" 2>/dev/null || true)
    [ -n "$remaining" ] && echo "$remaining" | xargs kill -KILL 2>/dev/null || true
fi

info "Stopping Flower..."
stop_service "Flower"         "logs/flower.pid"          "celery.*flower"

info "Stopping file watcher..."
stop_service "Watcher"        "logs/watcher.pid"         "python.*watcher.py"

info "Stopping Ollama..."
stop_service "Ollama"         "logs/ollama.pid"          "ollama serve"
pkill -x ollama 2>/dev/null || true

# ── Full shutdown: also stop Redis + PostgreSQL ────────────────────────────────
if $SHUTDOWN; then
    info "Stopping Redis..."
    sudo service redis-server stop > /dev/null 2>&1 || \
        pkill -x redis-server 2>/dev/null || true
    ok "Redis stopped"

    info "Stopping PostgreSQL..."
    sudo service postgresql stop > /dev/null 2>&1 || true
    ok "PostgreSQL stopped"
fi

echo ""
echo -e "${BOLD}All PRISM services stopped.${RESET}"

# ── WSL2 shutdown ──────────────────────────────────────────────────────────────
if $SHUTDOWN; then
    echo ""
    echo -e "  ${YELLOW}Shutting down WSL2 in 3 seconds…${RESET}"
    sleep 3
    # Call wsl --shutdown from Windows side via cmd.exe
    if command -v cmd.exe &>/dev/null; then
        cmd.exe /c "wsl --shutdown" &
    elif command -v powershell.exe &>/dev/null; then
        powershell.exe -Command "wsl --shutdown" &
    else
        sudo kill -TERM 1 2>/dev/null || true
    fi
fi
