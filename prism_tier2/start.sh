#!/usr/bin/env bash
# =============================================================================
#  PRISM — Start all services
#  Order: Redis → PostgreSQL → Ollama → Model preload →
#         Celery workers → Watcher → Gunicorn → Flower
# =============================================================================

set -euo pipefail

PRISM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PRISM_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
info() { echo -e "  ${CYAN}→${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }
fail() { echo -e "  ${RED}✗${RESET} $*"; }

# ── Load environment ───────────────────────────────────────────────────────────
[ -f .env ] && export $(grep -v '^#' .env | xargs)
export PYTHONPATH="$PRISM_DIR"
export PRISM_REDIS_URL="${PRISM_REDIS_URL:-redis://localhost:6379/0}"
export PRISM_DB_URL="${PRISM_DB_URL:-postgresql+psycopg2://prism:prism@localhost:5432/prism}"
export PRISM_OLLAMA_URL="${PRISM_OLLAMA_URL:-http://localhost:11434}"
export PRISM_OLLAMA_MODEL="${PRISM_OLLAMA_MODEL:-mistral}"

mkdir -p logs state landing/_review_queue landing/_unknown

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║        PRISM  —  Starting Services           ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Python dependencies ─────────────────────────────────────────────────────
info "Checking Python dependencies..."
python3 -c "import celery, redis, psycopg2, gunicorn, watchdog, requests, yaml" 2>/dev/null \
    && ok "Dependencies OK" \
    || { fail "Missing packages — run: pip3 install -r requirements.txt --break-system-packages"; exit 1; }

# ── 2. Redis ───────────────────────────────────────────────────────────────────
info "Starting Redis..."
if ! pgrep -x redis-server > /dev/null 2>&1; then
    sudo service redis-server start > /dev/null 2>&1 || true
    sleep 1
fi
python3 -c "
import redis, os
r = redis.from_url(os.environ.get('PRISM_REDIS_URL','redis://localhost:6379/0'))
r.ping()
" 2>/dev/null && ok "Redis ready" \
    || { fail "Redis not responding — run: sudo service redis-server start"; exit 1; }

# ── 3. PostgreSQL ──────────────────────────────────────────────────────────────
info "Starting PostgreSQL..."
if ! pgrep -x postgres > /dev/null 2>&1; then
    sudo service postgresql start > /dev/null 2>&1 || true
    sleep 2
fi
python3 -c "import db; db.init_db()" 2>/dev/null \
    && ok "PostgreSQL + schema ready" \
    || { fail "PostgreSQL not responding — check PRISM_DB_URL in .env"; exit 1; }

# ── 4. Ollama ──────────────────────────────────────────────────────────────────
info "Starting Ollama..."
if ! pgrep -x ollama > /dev/null 2>&1; then
    nohup ollama serve > logs/ollama.log 2>&1 &
    echo $! > logs/ollama.pid
    # Wait up to 15s for Ollama API to be ready
    for i in $(seq 1 30); do
        curl -sf "${PRISM_OLLAMA_URL}/api/tags" > /dev/null 2>&1 && break
        sleep 0.5
    done
fi
if curl -sf "${PRISM_OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
    ok "Ollama ready at ${PRISM_OLLAMA_URL}"
else
    warn "Ollama not responding — Lens AI features will be unavailable"
fi

# ── 5. Model preload ───────────────────────────────────────────────────────────
if curl -sf "${PRISM_OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
    info "Checking model: ${PRISM_OLLAMA_MODEL}..."
    MODEL_OK=$(curl -sf "${PRISM_OLLAMA_URL}/api/tags" \
        | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = '${PRISM_OLLAMA_MODEL}'
print('yes' if any(t in m.get('name','') for m in d.get('models',[])) else 'no')
" 2>/dev/null || echo "no")
    if [ "$MODEL_OK" = "yes" ]; then
        ok "Model '${PRISM_OLLAMA_MODEL}' available"
        # Warm up in background so first Lens request doesn't wait for model load
        curl -sf "${PRISM_OLLAMA_URL}/api/generate" \
            -d "{\"model\":\"${PRISM_OLLAMA_MODEL}\",\"prompt\":\"ready\",\"stream\":false}" \
            > /dev/null 2>&1 &
        ok "Model warm-up started in background"
    else
        warn "Model '${PRISM_OLLAMA_MODEL}' not found — run: ollama pull ${PRISM_OLLAMA_MODEL}"
    fi
fi

# ── 6. Celery workers ──────────────────────────────────────────────────────────
info "Starting Celery workers..."
pkill -f "celery.*celery_app.*worker" 2>/dev/null || true
sleep 1

celery -A celery_app worker \
    --loglevel=info \
    --queues=priority \
    --concurrency=4 \
    --hostname=priority@%h \
    --logfile=logs/celery_priority.log \
    --pidfile=logs/celery_priority.pid \
    --detach
ok "Celery priority worker (concurrency=4)"

celery -A celery_app worker \
    --loglevel=info \
    --queues=classify \
    --concurrency=8 \
    --hostname=classify@%h \
    --logfile=logs/celery_classify.log \
    --pidfile=logs/celery_classify.pid \
    --detach
ok "Celery classify worker (concurrency=8)"

# ── 7. File watcher ────────────────────────────────────────────────────────────
info "Starting file watcher..."
pkill -f "python.*watcher.py" 2>/dev/null || true
sleep 0.5
nohup python3 watcher.py > logs/watcher.log 2>&1 &
echo $! > logs/watcher.pid
sleep 0.5
kill -0 "$(cat logs/watcher.pid)" 2>/dev/null \
    && ok "File watcher started (PID $(cat logs/watcher.pid))" \
    || warn "Watcher may not have started — check logs/watcher.log"

# ── 8. Gunicorn ────────────────────────────────────────────────────────────────
info "Starting Gunicorn..."
sudo fuser -k 5000/tcp > /dev/null 2>&1 || true
sleep 0.5
gunicorn -c gunicorn.conf.py server:app >> logs/gunicorn_error.log 2>&1 &
GUNICORN_PID=$!
sleep 2
if kill -0 "$GUNICORN_PID" 2>/dev/null; then
    echo "$GUNICORN_PID" > logs/gunicorn.pid
    ok "Gunicorn started (PID $GUNICORN_PID) → http://localhost:5000"
else
    fail "Gunicorn failed — check logs/gunicorn_error.log:"
    tail -5 logs/gunicorn_error.log
    exit 1
fi

# ── 9. Flower (optional) ───────────────────────────────────────────────────────
if python3 -c "import flower" &>/dev/null; then
    info "Starting Flower..."
    pkill -f "celery.*flower" 2>/dev/null || true
    sleep 0.5
    python3 -m celery -A celery_app flower \
        --port=5555 \
        --broker="${PRISM_REDIS_URL}" \
        >> logs/flower.log 2>&1 &
    echo $! > logs/flower.pid
    ok "Flower → http://localhost:5555"
else
    warn "Flower not installed — run: pip3 install flower --break-system-packages"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║  PRISM is live                               ║${RESET}"
echo -e "${BOLD}╠══════════════════════════════════════════════╣${RESET}"
echo -e "${BOLD}║${RESET}  Web UI  →  http://localhost:5000            ${BOLD}║${RESET}"
echo -e "${BOLD}║${RESET}  Flower  →  http://localhost:5555            ${BOLD}║${RESET}"
echo -e "${BOLD}║${RESET}  Ollama  →  ${PRISM_OLLAMA_URL}     ${BOLD}║${RESET}"
echo -e "${BOLD}║${RESET}  Model   →  ${PRISM_OLLAMA_MODEL}                        ${BOLD}║${RESET}"
echo -e "${BOLD}║${RESET}  Logs    →  $PRISM_DIR/logs/       ${BOLD}║${RESET}"
echo -e "${BOLD}║${RESET}  Stop    →  ./stop.sh                        ${BOLD}║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""
