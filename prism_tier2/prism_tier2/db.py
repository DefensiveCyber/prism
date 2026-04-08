"""
db.py - Database layer for PRISM Tier 2.
Uses PostgreSQL via SQLAlchemy for audit log, review queue, and job state.
All tables are created automatically on first run.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    create_engine, text,
    Column, String, Float, Integer, Boolean, DateTime, Text, JSON
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# ── Connection ────────────────────────────────────────────────────────────────

def _get_db_url() -> str:
    """
    Build database URL from environment variables.
    Set PRISM_DB_URL to override completely, or set individual vars:
      PRISM_DB_HOST, PRISM_DB_PORT, PRISM_DB_NAME, PRISM_DB_USER, PRISM_DB_PASS
    """
    url = os.environ.get("PRISM_DB_URL")
    if url:
        return url
    host = os.environ.get("PRISM_DB_HOST", "localhost")
    port = os.environ.get("PRISM_DB_PORT", "5432")
    name = os.environ.get("PRISM_DB_NAME", "prism")
    user = os.environ.get("PRISM_DB_USER", "prism")
    pw   = os.environ.get("PRISM_DB_PASS", "prism")
    return f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{name}"


def get_engine():
    """Return a connection-pooled SQLAlchemy engine."""
    url = _get_db_url()
    return create_engine(
        url,
        poolclass=QueuePool,
        pool_size=10,          # base connections kept open
        max_overflow=20,       # burst connections above pool_size
        pool_timeout=30,       # seconds to wait for a connection
        pool_recycle=1800,     # recycle connections every 30 min
        pool_pre_ping=True,    # test connections before use (handles server restarts)
        echo=False,
    )


_engine = None

def engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def get_session() -> Session:
    return sessionmaker(bind=engine())()


# ── Models ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class AuditEntry(Base):
    """Every classification decision, one row per file."""
    __tablename__ = "audit_log"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    ts           = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    source_file  = Column(String(1024))
    destination  = Column(String(1024))
    sourcetype   = Column(String(256), index=True)
    category     = Column(String(128), index=True)
    vendor       = Column(String(256))
    product      = Column(String(256))
    confidence   = Column(Float)
    matched_pats = Column(JSON)       # list of matched pattern strings
    job_id       = Column(String(64), index=True, nullable=True)


class ReviewEntry(Base):
    """Files that need manual review — low confidence or unknown."""
    __tablename__ = "review_queue"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    added         = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    file          = Column(String(1024))
    sourcetype    = Column(String(256))
    confidence    = Column(Float)
    vendor        = Column(String(256))
    product       = Column(String(256))
    sample_lines  = Column(JSON)       # list of strings
    matched_pats  = Column(JSON)
    reviewed      = Column(Boolean, default=False, index=True)
    resolved_st   = Column(String(256), nullable=True)
    resolved_at   = Column(DateTime(timezone=True), nullable=True)


class ScanJob(Base):
    """One row per bulk scan job submitted via the UI."""
    __tablename__ = "scan_jobs"

    job_id      = Column(String(64), primary_key=True)
    directory   = Column(String(1024))
    recursive   = Column(Boolean, default=True)
    route       = Column(Boolean, default=True)
    submitted   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started     = Column(DateTime(timezone=True), nullable=True)
    finished    = Column(DateTime(timezone=True), nullable=True)
    status      = Column(String(32), default="pending")  # pending/running/done/failed
    total       = Column(Integer, default=0)
    done        = Column(Integer, default=0)
    errors      = Column(Integer, default=0)
    celery_id   = Column(String(256), nullable=True)   # Celery task ID


class LensSession(Base):
    """Lens AI analysis session — summary + conversation history."""
    __tablename__ = "lens_sessions"

    id          = Column(Integer, primary_key=True)
    file_path   = Column(Text, nullable=False)
    sourcetype  = Column(String(128))
    summary     = Column(Text)
    model       = Column(String(64))
    messages    = Column(JSON, default=list)
    created_at  = Column(DateTime(timezone=True),
                         default=lambda: datetime.now(timezone.utc))


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    Base.metadata.create_all(engine())
    logger.info("Database schema initialized")


# ── Data access helpers ───────────────────────────────────────────────────────

def record_audit(source_file, destination, result_dict, job_id=None):
    with get_session() as s:
        s.add(AuditEntry(
            source_file  = str(source_file),
            destination  = str(destination),
            sourcetype   = result_dict.get("sourcetype"),
            category     = result_dict.get("category"),
            vendor       = result_dict.get("vendor"),
            product      = result_dict.get("product"),
            confidence   = result_dict.get("confidence"),
            matched_pats = result_dict.get("matched_patterns", []),
            job_id       = job_id,
        ))
        s.commit()


def add_to_review(file_path, result_dict, sample_lines):
    with get_session() as s:
        s.add(ReviewEntry(
            file         = str(file_path),
            sourcetype   = result_dict.get("sourcetype"),
            confidence   = result_dict.get("confidence"),
            vendor       = result_dict.get("vendor"),
            product      = result_dict.get("product"),
            sample_lines = sample_lines[:100],
            matched_pats = result_dict.get("matched_patterns", []),
        ))
        s.commit()


def resolve_review(file_path: str, sourcetype: str) -> bool:
    with get_session() as s:
        row = s.query(ReviewEntry).filter_by(file=file_path, reviewed=False).first()
        if not row:
            return False
        row.reviewed    = True
        row.resolved_st = sourcetype
        row.resolved_at = datetime.now(timezone.utc)
        # Write to audit_log so it appears in dashboard stats
        s.add(AuditEntry(
            source_file  = file_path,
            destination  = file_path,
            sourcetype   = sourcetype,
            category     = row.matched_pats[0] if row.matched_pats else "reviewed",
            vendor       = "Manual",
            product      = "Manual Review",
            confidence   = 1.0,
            matched_pats = ["manual review"],
        ))
        s.commit()
        return True


def clear_review_queue(delete_files: bool = False) -> tuple[int, int]:
    """
    Remove all unreviewed queue entries.
    If delete_files=True, also delete the files from disk.
    Returns (entries_removed, files_deleted).
    """
    import os
    with get_session() as s:
        rows  = s.query(ReviewEntry).filter_by(reviewed=False).all()
        count = len(rows)
        files_deleted = 0
        if delete_files:
            for r in rows:
                try:
                    if r.file and os.path.exists(r.file):
                        os.unlink(r.file)
                        files_deleted += 1
                except Exception:
                    pass
        s.query(ReviewEntry).filter_by(reviewed=False).delete()
        s.commit()
        return count, files_deleted


def delete_review_item(file_path: str, delete_file: bool = False) -> tuple[bool, bool]:
    """
    Remove a single unreviewed queue entry by file path.
    If delete_file=True, also delete the file from disk.
    Returns (entry_removed, file_deleted).
    """
    import os
    with get_session() as s:
        row = s.query(ReviewEntry).filter_by(file=file_path, reviewed=False).first()
        if not row:
            return False, False
        file_deleted = False
        if delete_file:
            try:
                if file_path and os.path.exists(file_path):
                    os.unlink(file_path)
                    file_deleted = True
            except Exception:
                pass
        s.delete(row)
        s.commit()
        return True, file_deleted


def get_pending_reviews(limit=200) -> list[dict]:
    with get_session() as s:
        rows = (s.query(ReviewEntry)
                .filter_by(reviewed=False)
                .order_by(ReviewEntry.added.desc())
                .limit(limit)
                .all())
        return [_review_to_dict(r) for r in rows]


def _review_to_dict(r: ReviewEntry) -> dict:
    return {
        "id":           r.id,
        "file":         r.file,
        "added":        r.added.isoformat() if r.added else None,
        "classification": {
            "sourcetype":       r.sourcetype,
            "confidence":       r.confidence,
            "vendor":           r.vendor,
            "product":          r.product,
            "matched_patterns": r.matched_pats or [],
        },
        "sample_lines": r.sample_lines or [],
    }


def get_review_summary() -> dict:
    with get_session() as s:
        pending  = s.query(ReviewEntry).filter_by(reviewed=False).count()
        resolved = s.query(ReviewEntry).filter_by(reviewed=True).count()
        return {"pending": pending, "reviewed": resolved}


def get_stats(date_str=None) -> dict:
    """Return daily stats. date_str = 'YYYYMMDD', defaults to today.
    Uses a rolling 24-hour window when no date specified to avoid
    timezone boundary issues.
    """
    from datetime import date, timedelta
    if date_str:
        d     = datetime.strptime(date_str, "%Y%m%d").date()
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        end   = start + timedelta(days=1)
    else:
        # Rolling 24-hour window from now — avoids UTC vs local timezone issues
        end   = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)

    with get_session() as s:
        rows = (s.query(AuditEntry)
                .filter(AuditEntry.ts >= start, AuditEntry.ts < end)
                .all())

    total  = len(rows)
    by_st  = {}
    by_cat = {}
    review = 0
    for r in rows:
        by_st[r.sourcetype]  = by_st.get(r.sourcetype,  0) + 1
        by_cat[r.category]   = by_cat.get(r.category,   0) + 1
        if r.confidence is not None and r.confidence < 0.6:
            review += 1

    # Get live queue count from review_queue table (more accurate than audit_log)
    with get_session() as s2:
        queue_pending = s2.query(ReviewEntry).filter_by(reviewed=False).count()

    return {
        "date":           d.strftime("%Y%m%d") if date_str else end.strftime("%Y%m%d"),
        "total":          total,
        "by_sourcetype":  dict(sorted(by_st.items(),  key=lambda x: -x[1])),
        "by_category":    dict(sorted(by_cat.items(), key=lambda x: -x[1])),
        "review_queue":   queue_pending,
    }


def create_job(job_id, directory, recursive, route) -> ScanJob:
    with get_session() as s:
        job = ScanJob(job_id=job_id, directory=directory,
                      recursive=recursive, route=route)
        s.add(job)
        s.commit()
        s.refresh(job)
        return job


def update_job(job_id, **kwargs):
    with get_session() as s:
        s.query(ScanJob).filter_by(job_id=job_id).update(kwargs)
        s.commit()


def get_job(job_id) -> dict | None:
    with get_session() as s:
        job = s.query(ScanJob).filter_by(job_id=job_id).first()
        return _job_to_dict(job) if job else None


def get_audit_by_job(job_id: str, limit: int = 5000) -> list[dict]:
    """Return all audit entries for a specific scan job."""
    with get_session() as s:
        rows = (s.query(AuditEntry)
                .filter_by(job_id=job_id)
                .order_by(AuditEntry.id)
                .limit(limit)
                .all())
        return [{
            "file":           Path(r.source_file).name if r.source_file else "",
            "path":           r.source_file or "",
            "sourcetype":     r.sourcetype or "unknown",
            "category":       r.category or "unknown",
            "confidence":     r.confidence or 0.0,
            "confidence_pct": f"{(r.confidence or 0):.0%}",
            "destination":    r.destination or "",
        } for r in rows]


def get_jobs(limit=50) -> list[dict]:
    with get_session() as s:
        jobs = (s.query(ScanJob)
                .order_by(ScanJob.submitted.desc())
                .limit(limit).all())
        return [_job_to_dict(j) for j in jobs]


def _job_to_dict(j: ScanJob) -> dict:
    return {
        "job_id":    j.job_id,
        "directory": j.directory,
        "recursive": j.recursive,
        "route":     j.route,
        "status":    j.status,
        "submitted": j.submitted.isoformat() if j.submitted else None,
        "started":   j.started.isoformat()   if j.started   else None,
        "finished":  j.finished.isoformat()  if j.finished  else None,
        "total":     j.total,
        "done":      j.done,
        "errors":    j.errors,
        "running":   j.status == "running",
    }


# ── Lens sessions ──────────────────────────────────────────────────────────────

def create_lens_session(file_path: str, sourcetype: str,
                        summary: str, model: str) -> int:
    with get_session() as s:
        row = LensSession(
            file_path  = file_path,
            sourcetype = sourcetype,
            summary    = summary,
            model      = model,
            messages   = [],
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def append_lens_message(session_id: int, role: str, content: str):
    with get_session() as s:
        row = s.query(LensSession).filter_by(id=session_id).first()
        if row:
            msgs = list(row.messages or [])
            msgs.append({
                "role":    role,
                "content": content,
                "ts":      datetime.now(timezone.utc).isoformat(),
            })
            row.messages = msgs
            s.commit()


def get_lens_session(session_id: int) -> dict | None:
    with get_session() as s:
        row = s.query(LensSession).filter_by(id=session_id).first()
        if not row:
            return None
        return {
            "id":         row.id,
            "file_path":  row.file_path,
            "sourcetype": row.sourcetype,
            "summary":    row.summary,
            "model":      row.model,
            "messages":   row.messages or [],
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


def get_lens_sessions(limit: int = 50) -> list[dict]:
    with get_session() as s:
        rows = (s.query(LensSession)
                .order_by(LensSession.created_at.desc())
                .limit(limit).all())
        return [{
            "id":         r.id,
            "file_path":  r.file_path,
            "sourcetype": r.sourcetype,
            "summary":    (r.summary or "")[:120] + "..." if r.summary and len(r.summary) > 120 else (r.summary or ""),
            "model":      r.model,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "msg_count":  len(r.messages or []),
        } for r in rows]


def delete_lens_session(session_id: int) -> bool:
    with get_session() as s:
        row = s.query(LensSession).filter_by(id=session_id).first()
        if not row:
            return False
        s.delete(row)
        s.commit()
        return True
