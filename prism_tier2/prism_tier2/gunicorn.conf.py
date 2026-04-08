"""
gunicorn.conf.py - Production Gunicorn configuration for PRISM.
Start with: gunicorn -c gunicorn.conf.py server:app
"""

import multiprocessing
import os

# ── Binding ───────────────────────────────────────────────────────────────────
bind    = os.environ.get("PRISM_BIND", "0.0.0.0:5000")
backlog = 2048          # max queued connections before refusing

# ── Workers ───────────────────────────────────────────────────────────────────
# sync workers: most compatible across all platforms including WSL2.
# PRISM's web server does minimal work (submits Celery tasks, reads DB)
# so sync workers with threads are more than sufficient.
worker_class   = "sync"
workers        = multiprocessing.cpu_count() * 2 + 1
threads        = 4      # threads per worker for concurrent requests

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout       = 120     # kill worker if no response in 120s
keepalive     = 5       # keep-alive connections (seconds)
graceful_timeout = 30   # time to finish in-flight requests on SIGTERM

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = "logs/gunicorn_access.log"
errorlog  = "logs/gunicorn_error.log"
loglevel  = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Process management ────────────────────────────────────────────────────────
# Preload app once in master, fork to workers (saves RAM via copy-on-write)
preload_app   = True
daemon        = False    # systemd manages the process, not gunicorn
# pidfile managed by start.sh

# ── Memory safety ─────────────────────────────────────────────────────────────
# Recycle workers after N requests to prevent memory creep
max_requests          = 10000
max_requests_jitter   = 500   # stagger recycling so not all workers restart at once

# ── Hooks ─────────────────────────────────────────────────────────────────────
def on_starting(server):
    """Initialize DB schema before any worker starts."""
    import db
    db.init_db()

def post_fork(server, worker):
    """After fork, each worker gets a fresh DB engine (don't share connections)."""
    import db
    db._engine = None   # force new engine in this worker process

def worker_exit(server, worker):
    """Clean up DB connections when a worker exits."""
    import db
    if db._engine:
        db._engine.dispose()
