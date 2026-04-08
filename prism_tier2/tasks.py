"""
tasks.py - Celery tasks for PRISM.
All heavy classification and routing work runs here, off the web server.
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# Load .env before anything else so DB/Redis URLs are available in worker processes
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

from celery import Task
from celery_app import celery
import db

logger = logging.getLogger(__name__)

BASE_DIR      = Path(__file__).parent
SIGS_FILE     = BASE_DIR / "config" / "signatures.yaml"
SETTINGS_FILE = BASE_DIR / "config" / "settings.yaml"


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _load_settings():
    import yaml
    with open(SETTINGS_FILE) as f:
        return yaml.safe_load(f) or {}


def _get_classifier():
    """Each worker process gets its own classifier instance (not shared across processes)."""
    from classifier import LogClassifier
    return LogClassifier(str(SIGS_FILE))


def _get_router(settings):
    from router import LogRouter
    landing = BASE_DIR / settings.get("landing", {}).get("base_dir", "landing")
    threshold = settings.get("classification", {}).get("review_queue_threshold", 0.6)
    return LogRouter(str(landing), review_threshold=threshold)


def _should_process(path: Path, settings: dict) -> bool:
    inc = settings.get("include_extensions", [])
    exc = settings.get("exclude_extensions", [])
    if path.suffix in exc or path.name.endswith((".review.txt", ".reason.txt")):
        return False
    if inc and path.suffix not in inc:
        return False
    return True


def _build_result_dict(result) -> dict:
    return {
        "sourcetype":       result.sourcetype,
        "category":         result.category,
        "vendor":           result.vendor,
        "product":          result.product,
        "confidence":       round(result.confidence, 4),
        "matched_patterns": result.matched_patterns,
    }


def _maybe_queue(dest, result_dict, clf_settings):
    """Add to DB review queue if confidence is below threshold."""
    threshold = clf_settings.get("review_queue_threshold", 0.6)
    if result_dict["confidence"] < threshold or result_dict["sourcetype"] == "unknown":
        try:
            with open(dest, "r", encoding="utf-8", errors="replace") as fh:
                sample = [l for l in fh.read(65536).splitlines() if l.strip()][:100]
        except Exception:
            sample = []
        db.add_to_review(dest, result_dict, sample)


# ── Task: classify single file (priority queue — UI requests) ─────────────────

@celery.task(
    name="tasks.classify_single_file",
    bind=True,
    max_retries=3,
    rate_limit="300/m",   # max 300 single-file classifies per minute
)
def classify_single_file(self, file_path: str, route: bool = True) -> dict:
    """
    Classify one file and optionally route it to the landing zone.
    Returns the classification result dict.
    """
    try:
        settings = _load_settings()
        clf      = _get_classifier()
        result   = clf.classify(file_path)
        rd       = _build_result_dict(result)

        dest = None
        if route:
            move   = settings.get("classification", {}).get("move_files", True)
            router = _get_router(settings)
            # Find matching signature dict for cleaning config
            sig_dict = clf.get_signature_detail(result.sourcetype)
            dest   = router.route(file_path, result, move=move, sig=sig_dict)
            db.record_audit(file_path, dest, rd)
            _maybe_queue(dest, rd, clf.settings)

        return {**rd, "destination": dest, "routed": route and dest is not None}

    except Exception as exc:
        logger.error(f"classify_single_file failed for {file_path}: {exc}")
        raise self.retry(exc=exc, countdown=5)


# ── Task: classify pasted text (priority queue) ────────────────────────────────

@celery.task(
    name="tasks.classify_text",
    bind=True,
)
def classify_text_task(self, text: str) -> dict:
    clf    = _get_classifier()
    result = clf.classify_text(text)
    return _build_result_dict(result)


# ── Task: bulk directory scan (classify queue) ─────────────────────────────────

@celery.task(
    name="tasks.scan_directory",
    bind=True,
    max_retries=1,
    rate_limit="2/m",     # max 2 concurrent bulk scans per worker
    time_limit=86400,     # kill if running > 24 hours
    soft_time_limit=82800,# warn at 23 hours
)
def scan_directory(self, job_id: str, directory: str, recursive: bool, route: bool) -> dict:
    """
    Bulk-scan a directory, classifying every eligible file.
    Progress is written to PostgreSQL so the web server can poll it.
    Includes checkpointing: if the task is retried it skips already-processed files.
    """
    from datetime import datetime, timezone

    db.update_job(job_id,
                  status="running",
                  started=datetime.now(timezone.utc),
                  celery_id=self.request.id)

    settings = _load_settings()
    clf      = _get_classifier()
    router   = _get_router(settings) if route else None
    move     = settings.get("classification", {}).get("move_files", True)

    dp = Path(directory)
    if not dp.exists():
        db.update_job(job_id, status="failed", finished=datetime.now(timezone.utc))
        return {"error": f"Directory not found: {directory}"}

    # Collect files
    glob   = "**/*" if recursive else "*"
    files  = [p for p in dp.glob(glob) if p.is_file() and _should_process(p, settings)]
    total  = len(files)
    db.update_job(job_id, total=total)

    # Load checkpoint (in case of retry)
    checkpoint_file = BASE_DIR / "state" / f"{job_id}.ckpt"
    already_done: set = set()
    if checkpoint_file.exists():
        import json
        try:
            already_done = set(json.loads(checkpoint_file.read_text()))
        except Exception:
            already_done = set()

    done = len(already_done)
    errors = 0
    results = []

    CHECKPOINT_EVERY = 500    # write checkpoint every 500 files
    BATCH_DB_EVERY   = 100    # batch DB writes every 100 files for performance
    pending_audits   = []
    pending_reviews  = []

    for i, fp in enumerate(files):
        if str(fp) in already_done:
            continue

        try:
            result = clf.classify(str(fp))
            rd     = _build_result_dict(result)
            dest   = None

            if route and router:
                # Find matching signature dict for cleaning config
                sig_dict_bulk = clf.get_signature_detail(result.sourcetype)
                dest = router.route(str(fp), result, move=move, sig=sig_dict_bulk)
                pending_audits.append((str(fp), str(dest), rd))
                threshold = clf.settings.get("review_queue_threshold", 0.6)
                if rd["confidence"] < threshold or rd["sourcetype"] == "unknown":
                    # Read sample for review queue
                    try:
                        with open(dest, "r", encoding="utf-8", errors="replace") as fh:
                            sample = [l for l in fh.read(65536).splitlines() if l.strip()][:100]
                    except Exception:
                        sample = []
                    pending_reviews.append((dest, rd, sample))

            results.append({
                "file":           fp.name,
                "path":           str(fp),
                "sourcetype":     rd["sourcetype"],
                "category":       rd["category"],
                "confidence":     rd["confidence"],
                "confidence_pct": f"{rd['confidence']:.0%}",
                "destination":    dest,
            })

        except Exception as e:
            errors += 1
            logger.error(f"[{job_id}] Failed {fp}: {e}")
            results.append({
                "file": fp.name, "path": str(fp),
                "sourcetype": "ERROR", "confidence": 0, "error": str(e),
            })

        done += 1
        already_done.add(str(fp))

        # Batch DB writes
        if len(pending_audits) >= BATCH_DB_EVERY:
            _flush_audits(pending_audits, job_id)
            pending_audits.clear()
        if len(pending_reviews) >= BATCH_DB_EVERY:
            _flush_reviews(pending_reviews)
            pending_reviews.clear()

        # Update job progress in DB
        if done % 100 == 0 or done == total:
            db.update_job(job_id, done=done, errors=errors)

        # Write checkpoint periodically
        if done % CHECKPOINT_EVERY == 0:
            import json
            checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_file.write_text(json.dumps(list(already_done)))

    # Final flush
    if pending_audits:
        _flush_audits(pending_audits, job_id)
    if pending_reviews:
        _flush_reviews(pending_reviews)

    # Clean up checkpoint
    if checkpoint_file.exists():
        checkpoint_file.unlink()

    db.update_job(job_id,
                  status="done",
                  done=done,
                  errors=errors,
                  finished=datetime.now(timezone.utc))

    return {"job_id": job_id, "total": total, "done": done, "errors": errors}


def _flush_audits(pending: list, job_id: str):
    """Batch-insert audit records for performance."""
    from sqlalchemy import insert
    with db.get_session() as s:
        now = datetime.now(timezone.utc)
        s.execute(
            insert(db.AuditEntry),
            [{"ts": now, "source_file": src, "destination": dst,
              "sourcetype": rd["sourcetype"], "category": rd["category"],
              "vendor": rd["vendor"], "product": rd["product"],
              "confidence": rd["confidence"], "matched_pats": rd["matched_patterns"],
              "job_id": job_id}
             for src, dst, rd in pending]
        )
        s.commit()


def _flush_reviews(pending: list):
    """Batch-insert review queue entries."""
    from sqlalchemy import insert
    with db.get_session() as s:
        now = datetime.now(timezone.utc)
        s.execute(
            insert(db.ReviewEntry),
            [{"added": now, "file": dest, "sourcetype": rd["sourcetype"],
              "confidence": rd["confidence"], "vendor": rd["vendor"],
              "product": rd["product"], "sample_lines": sample,
              "matched_pats": rd["matched_patterns"]}
             for dest, rd, sample in pending]
        )
        s.commit()


# ── Task: watcher dispatch (called by watchdog watcher) ───────────────────────

@celery.task(
    name="tasks.dispatch_watched_file",
    bind=True,
    max_retries=3,
    rate_limit="600/m",   # 600 files/min per worker = 10/sec
)
def dispatch_watched_file(self, file_path: str) -> dict:
    """
    Called by the file system watcher for each new file.
    Thin wrapper around classify_single_file — rate-limited separately.
    """
    try:
        return classify_single_file(file_path, route=True)
    except Exception as exc:
        logger.error(f"dispatch_watched_file failed for {file_path}: {exc}")
        raise self.retry(exc=exc, countdown=10)
