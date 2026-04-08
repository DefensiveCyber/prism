"""
audit.py - Logs every classification decision to a JSONL audit file.
Every classification is recorded so you can review decisions, spot
misclassifications, and track accuracy over time.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class AuditLog:
    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log_file(self) -> Path:
        """One audit file per day."""
        date_str = datetime.now().strftime("%Y%m%d")
        return self.log_dir / f"audit_{date_str}.jsonl"

    def record(self, source_file: str, result_dict: dict, destination: str, action: str = "classified"):
        """Write a classification decision to the audit log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "source_file": source_file,
            "destination": destination,
            "sourcetype": result_dict.get("sourcetype"),
            "category": result_dict.get("category"),
            "vendor": result_dict.get("vendor"),
            "product": result_dict.get("product"),
            "confidence": result_dict.get("confidence"),
            "matched_patterns": result_dict.get("matched_patterns", []),
        }

        try:
            with open(self._log_file(), "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log entry: {e}")

    def stats(self, date_str: str = None) -> dict:
        """
        Return classification statistics for a given date (YYYYMMDD).
        Defaults to today.
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y%m%d")

        log_file = self.log_dir / f"audit_{date_str}.jsonl"
        if not log_file.exists():
            return {"date": date_str, "total": 0, "by_sourcetype": {}, "by_category": {}, "review_queue": 0}

        total = 0
        by_sourcetype: dict = {}
        by_category: dict = {}
        review_count = 0

        with open(log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except Exception:
                    continue

                total += 1
                st = entry.get("sourcetype", "unknown")
                cat = entry.get("category", "unknown")
                by_sourcetype[st] = by_sourcetype.get(st, 0) + 1
                by_category[cat] = by_category.get(cat, 0) + 1
                if st == "unknown" or entry.get("confidence", 1.0) < 0.5:
                    review_count += 1

        return {
            "date": date_str,
            "total": total,
            "by_sourcetype": dict(sorted(by_sourcetype.items(), key=lambda x: -x[1])),
            "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
            "review_queue": review_count,
        }
