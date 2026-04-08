"""
celery_app.py - Celery application factory for PRISM.
Import this everywhere you need the Celery app instance.
"""

import os
from pathlib import Path
from celery import Celery

# Load .env so Redis URL is available when workers start
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

def make_celery() -> Celery:
    broker  = os.environ.get("PRISM_REDIS_URL", "redis://localhost:6379/0")
    backend = os.environ.get("PRISM_REDIS_URL", "redis://localhost:6379/0")

    app = Celery(
        "prism",
        broker=broker,
        backend=backend,
        include=["tasks"],   # auto-discover tasks module
    )

    app.conf.update(
        # ── Serialization ──────────────────────────────────────────────
        task_serializer        = "json",
        result_serializer      = "json",
        accept_content         = ["json"],

        # ── Task behavior ──────────────────────────────────────────────
        task_acks_late         = True,   # ack AFTER task completes, not before
        task_reject_on_worker_lost = True,  # re-queue if worker dies mid-task
        worker_prefetch_multiplier = 1,  # one task per worker at a time (fair dispatch)

        # ── Result TTL ─────────────────────────────────────────────────
        result_expires         = 86400,  # keep results 24 hours

        # ── Rate limits ────────────────────────────────────────────────
        # Per-task rate limiting is set on each task with @app.task(rate_limit=...)
        # Global: don't overwhelm the disk
        worker_max_tasks_per_child = 5000,  # restart worker after 5k tasks (memory safety)

        # ── Retry defaults ─────────────────────────────────────────────
        task_default_retry_delay   = 5,    # seconds between retries
        task_max_retries           = 3,

        # ── Queues ─────────────────────────────────────────────────────
        # Two queues: 'classify' for bulk file work, 'priority' for UI requests
        task_default_queue = "classify",
        task_queues = {
            "priority": {"exchange": "priority", "routing_key": "priority"},
            "classify": {"exchange": "classify", "routing_key": "classify"},
        },
        task_routes = {
            "tasks.classify_single_file": {"queue": "priority"},
            "tasks.classify_text":        {"queue": "priority"},
            "tasks.scan_directory":       {"queue": "classify"},
        },

        # ── Monitoring ─────────────────────────────────────────────────
        worker_send_task_events = True,    # enables Flower monitoring
        task_send_sent_event    = True,
    )

    return app


celery = make_celery()
