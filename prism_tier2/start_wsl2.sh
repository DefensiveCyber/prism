#!/usr/bin/env bash
# =============================================================================
# PRISM - Start all services (WSL2 with venv)
# Usage: ./start_wsl2.sh
# =============================================================================

set -e
PRISM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PRISM_DIR"

# Activate venv
if [ ! -f "venv/bin/activate" ]; then
    echo "ERROR: venv not found. Run setup first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate

# Load .env
[ -f .env ] && export $(grep -v '^#' .env | xargs)

# PYTHONPATH must point to project root so workers find classifier.py
export PYTHONPATH="$PRISM_DIR"

export PRISM_REDIS_URL="${PRISM_REDIS_URL:-redis://localhost:6379/0}"
export PRISM_DB_URL="${PRISM_DB_URL:-postgresql+psycopg2://prism:prism@localhost:5432/prism}"

mkdir -p logs state landing/_review_queue landing/_unknown

echo "======================================================"
echo "  PRISM - Starting services (WSL2 / venv)"
echo "  Directory: $PRISM_DIR"
echo "  Python:    $(which python)"
echo "======================================================"

# ── 1. Check dependencies ──────────────────────────────────────────────────
python -c "import celery, redis, psycopg2, gunicorn, watchdog" 2>/dev/null || {
    echo "ERROR: Missing packages. Run:"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
}

# ── 2. Check Redis ─────────────────────────────────────────────────────────
sudo service redis-server start 2>/dev/null || true
python -c "
import redis, os
r = redis.from_url(os.environ.get('PRISM_REDIS_URL','redis://localhost:6379/0'))
r.ping()
print('  ✓ Redis connected')
" || { echo "ERROR: Redis not responding. Try: sudo service redis-server start"; exit 1; }

# ── 3. Check PostgreSQL ────────────────────────────────────────────────────
sudo service postgresql start 2>/dev/null || true
sleep 1

# ── 4. Initialize database ─────────────────────────────────────────────────
python -c "import db; db.init_db(); print('  ✓ Database ready')" || {
    echo "ERROR: Cannot connect to PostgreSQL."
    echo "  Check PRISM_DB_URL in .env"
    echo "  Run: sudo service postgresql start"
    exit 1
}

# ── 5. Start Celery workers ────────────────────────────────────────────────
echo "  Starting Celery priority worker..."
celery -A celery_app worker \
    --loglevel=info \
    --queues=priority \
    --concurrency=4 \
    --hostname=priority@%h \
    --logfile=logs/celery_priority.log \
    --pidfile=logs/celery_priority.pid \
    --detach

echo "  Starting Celery classify worker..."
celery -A celery_app worker \
    --loglevel=info \
    --queues=classify \
    --concurrency=8 \
    --hostname=classify@%h \
    --logfile=logs/celery_classify.log \
    --pidfile=logs/celery_classify.pid \
    --detach

echo "  ✓ Celery workers started"

# ── 6. Start watcher ───────────────────────────────────────────────────────
echo "  Starting file system watcher..."
python watcher.py > logs/watcher.log 2>&1 &
echo $! > logs/watcher.pid
echo "  ✓ Watcher started (PID $(cat logs/watcher.pid))"

# ── 7. Start web server ────────────────────────────────────────────────────
echo "  Starting Gunicorn web server..."
# On WSL2 with project on /mnt/c/, --daemon can fail due to Windows filesystem
# restrictions on PID files. Run in background instead.
gunicorn -c gunicorn.conf.py server:app \
    --pid logs/gunicorn.pid \
    >> logs/gunicorn_error.log 2>&1 &
GUNICORN_PID=$!
sleep 1
# Verify it actually started
if kill -0 $GUNICORN_PID 2>/dev/null; then
    echo $GUNICORN_PID > logs/gunicorn.pid
    echo "  ✓ Web server started (PID $GUNICORN_PID)"
else
    echo "  ✗ Gunicorn failed to start. Check logs/gunicorn_error.log"
    tail -5 logs/gunicorn_error.log
    exit 1
fi

echo ""
echo "======================================================"
echo "  PRISM is running at http://localhost:5000"
echo "  Logs: $PRISM_DIR/logs/"
echo "  Stop: ./stop.sh"
echo "======================================================"
