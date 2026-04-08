"""
router.py - Routes classified log files into sourcetype-named landing zones.

After classification, files are cleaned (dirty/non-conforming lines stripped)
before being written to their landing zone. Noise is preserved in a sidecar
.noise file alongside the clean output.

e.g.  landing/cisco_asa/20240101_120000_file.log        ← clean events
      landing/cisco_asa/20240101_120000_file.noise.log  ← stripped lines
      landing/_review_queue/...                          ← low confidence
"""

import shutil
import logging
from pathlib import Path
from datetime import datetime

from classifier import ClassificationResult

logger = logging.getLogger(__name__)

REVIEW_DIR  = "_review_queue"
UNKNOWN_DIR = "_unknown"


def _safe_dirname(sourcetype: str) -> str:
    """Convert a sourcetype string to a safe directory name."""
    return (sourcetype
            .replace(":", "_")
            .replace("/", "_")
            .replace(" ", "_")
            .replace("\\", "_"))


class LogRouter:
    def __init__(self, landing_base: str, review_threshold: float = 0.5,
                 clean_files: bool = True):
        self.landing_base     = Path(landing_base)
        self.review_threshold = review_threshold
        self.clean_files      = clean_files  # set False to disable cleaning globally
        self.landing_base.mkdir(parents=True, exist_ok=True)
        (self.landing_base / REVIEW_DIR).mkdir(exist_ok=True)
        (self.landing_base / UNKNOWN_DIR).mkdir(exist_ok=True)

    # ── Destination resolution ────────────────────────────────────────────────

    def _get_dest_dir(self, result: ClassificationResult) -> Path:
        if result.confidence == 0.0 or result.sourcetype == "unknown":
            return self.landing_base / REVIEW_DIR
        if result.confidence < self.review_threshold:
            return self.landing_base / REVIEW_DIR
        dirname = _safe_dirname(result.sourcetype)
        dest = self.landing_base / dirname
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def _dest_path(self, source_file: Path, dest_dir: Path) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename  = f"{timestamp}_{source_file.name}"
        return dest_dir / filename

    # ── Main route ────────────────────────────────────────────────────────────

    def route(self, source_file: str, result: ClassificationResult,
              move: bool = True, sig: dict = None) -> str:
        """
        Route a classified file to its landing zone, cleaning it first.

        Args:
            source_file: Path to the original log file
            result:      ClassificationResult from classifier
            move:        If True, move file; if False, copy
            sig:         Raw signature dict — used to derive filter config.
                         If None, no cleaning is performed.

        Returns:
            str path of the clean file in the landing zone
        """
        source_path = Path(source_file)
        dest_dir    = self._get_dest_dir(result)
        dest_path   = self._dest_path(source_path, dest_dir)

        # ── Cleaning ──────────────────────────────────────────────────────────
        cleaning_applied = False
        clean_stats = {}

        if self.clean_files and sig is not None and sig.get("cleaning_enabled", True):
            try:
                from cleaner import clean_file, derive_filter_config
                filter_cfg = derive_filter_config(sig)

                if filter_cfg['filter_mode'] != 'passthrough':
                    clean_stats = clean_file(
                        source_path   = str(source_path),
                        dest_path     = str(dest_path),
                        filter_mode   = filter_cfg['filter_mode'],
                        line_filter   = filter_cfg['line_filter'],
                        multiline_mode= filter_cfg['multiline_mode'],
                    )
                    cleaning_applied = True

                    # Remove or keep original based on move flag
                    if move:
                        source_path.unlink(missing_ok=True)

                    noise_info = (f", {clean_stats['noise']} noise → "
                                  f"{Path(clean_stats['noise_path']).name}"
                                  if clean_stats.get('noise_path') else "")
                    logger.info(
                        f"Cleaned + {'moved' if move else 'copied'} → "
                        f"{dest_path.parent.name}/{dest_path.name} "
                        f"({clean_stats['clean']} clean{noise_info})"
                    )

            except Exception as e:
                logger.warning(f"Cleaning failed for {source_path}, "
                               f"routing as-is: {e}")
                cleaning_applied = False

        # ── Fallback: no cleaning or cleaning failed ───────────────────────────
        if not cleaning_applied:
            try:
                if move:
                    shutil.move(str(source_path), str(dest_path))
                else:
                    shutil.copy2(str(source_path), str(dest_path))
                logger.info(
                    f"{'Moved' if move else 'Copied'} → "
                    f"{dest_path.parent.name}/{dest_path.name}"
                )
            except Exception as e:
                logger.error(f"Route failed for {source_path}: {e}")
                raise

        return str(dest_path)

    def route_to_review(self, source_file: str, reason: str = "") -> str:
        source_path = Path(source_file)
        dest_dir    = self.landing_base / REVIEW_DIR
        dest_path   = self._dest_path(source_path, dest_dir)
        shutil.move(str(source_path), str(dest_path))
        if reason:
            dest_path.with_suffix(".reason.txt").write_text(
                f"File: {source_path.name}\nReason: {reason}\n"
            )
        return str(dest_path)

    def list_landing_dirs(self) -> list[dict]:
        """Return all landing zone dirs with file counts and latest activity."""
        result = []
        for d in sorted(self.landing_base.iterdir()):
            if not d.is_dir():
                continue
            files = [
                f for f in d.iterdir()
                if f.is_file()
                and not f.name.endswith((".review.txt", ".reason.txt", ".noise.log"))
            ]
            noise_files = [f for f in d.iterdir() if f.name.endswith(".noise.log")]
            latest = max((f.stat().st_mtime for f in files), default=0) if files else 0
            result.append({
                "name":        d.name,
                "count":       len(files),
                "noise_count": len(noise_files),
                "latest":      datetime.fromtimestamp(latest).strftime(
                    "%Y-%m-%d %H:%M:%S") if latest else "—",
                "path":        str(d),
            })
        return result
