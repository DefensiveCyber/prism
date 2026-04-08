"""
classifier.py - Core log classification engine with hot-reload and GUI write-back support.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    sourcetype: str
    category: str
    vendor: str
    product: str
    confidence: float
    matched_patterns: list = field(default_factory=list)
    required_patterns: list = field(default_factory=list)
    file_level: bool = False


@dataclass
class Signature:
    sourcetype: str
    category: str
    vendor: str
    product: str
    confidence: float
    line_patterns: list        # optional booster patterns
    raw_patterns: list
    min_matches: int           # min optional patterns that must match
    required_patterns: list    # ALL of these must match (hard requirement)
    raw_required_patterns: list
    header_match: Optional[object]
    raw_header_match: Optional[str]
    exclude_patterns: list
    raw_exclude_patterns: list
    file_level: bool


def _extract_text(file_path: str, max_bytes: int = 8192) -> str:
    """
    Route a file through the appropriate parser based on its format,
    returning a plain-text representation for the classifier.
    Falls back to plain text read for unknown formats.
    """
    from pathlib import Path
    import sys, os

    # Ensure parsers package is importable
    _base = Path(__file__).parent
    if str(_base) not in sys.path:
        sys.path.insert(0, str(_base))

    p = Path(file_path)
    ext = p.suffix.lower()

    # ── EVTX / EVT (Windows binary event log) ─────────────────────────────
    if ext in {".evtx", ".evt"}:
        from parsers.evtx_parser import extract_text, _evtx_stub
        # Try full parse first, then stub — never fall through to plain text
        # because binary content would produce garbage matches
        text = extract_text(file_path)
        if not text:
            text = _evtx_stub(file_path)
        if text:
            return text
        # File had .evtx extension but no ElfFile magic — treat as unknown
        return "<!-- EVTX file unreadable -->"

    # ── Check for other binary files — don't pass binary to regex engine ───
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(512)
        if chunk.count(b"\x00") > len(chunk) * 0.1:
            # Binary file with unknown extension — return empty so it goes to review
            return ""
    except Exception:
        pass

    # ── CSV ───────────────────────────────────────────────────────────────
    if ext == ".csv":
        try:
            from parsers.csv_parser import extract_text
            text = extract_text(file_path)
            if text:
                return text
        except Exception:
            pass

    # ── Elasticsearch NDJSON export ────────────────────────────────────────
    if ext in {".json", ".ndjson", ".jsonl"}:
        try:
            from parsers.elastic_parser import is_elastic_ndjson, extract_text
            if is_elastic_ndjson(file_path):
                text = extract_text(file_path)
                if text:
                    return text
        except Exception:
            pass

    # ── Default: plain text read ───────────────────────────────────────────
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_bytes)


class LogClassifier:
    def __init__(self, signatures_path: str):
        self.signatures_path = signatures_path
        self.signatures: list = []
        self.settings: dict = {}
        self._load_signatures()

    def _load_signatures(self):
        with open(self.signatures_path, "r") as f:
            config = yaml.safe_load(f)
        self.settings = config.get("settings", {})
        self.signatures = []
        for entry in config.get("signatures", []):
            raw_patterns = entry.get("line_patterns", [])
            raw_excludes  = entry.get("exclude_patterns", [])
            raw_header    = entry.get("header_match")
            raw_required  = entry.get("required_patterns", [])
            sig = Signature(
                sourcetype=entry["sourcetype"],
                category=entry.get("category", "unknown"),
                vendor=entry.get("vendor", "Unknown"),
                product=entry.get("product", "Unknown"),
                confidence=entry.get("confidence", 0.5),
                line_patterns=[re.compile(p, re.IGNORECASE | re.MULTILINE) for p in raw_patterns],
                raw_patterns=raw_patterns,
                min_matches=entry.get("min_matches", 1),
                required_patterns=[re.compile(p, re.IGNORECASE | re.MULTILINE) for p in raw_required],
                raw_required_patterns=raw_required,
                header_match=re.compile(raw_header, re.IGNORECASE | re.MULTILINE) if raw_header else None,
                raw_header_match=raw_header,
                exclude_patterns=[re.compile(p, re.IGNORECASE | re.MULTILINE) for p in raw_excludes],
                raw_exclude_patterns=raw_excludes,
                file_level=entry.get("file_level", False),
            )
            self.signatures.append(sig)
        logger.info(f"Loaded {len(self.signatures)} signatures")

    def reload(self):
        self._load_signatures()

    def _score(self, sig, raw, lines, header_lines):
        if sig.header_match and not sig.header_match.search(header_lines):
            return 0.0, []
        for excl in sig.exclude_patterns:
            if excl.search(raw):
                return 0.0, []
        text = raw if sig.file_level else "\n".join(lines)
        # required_patterns: ALL must match or score is 0
        for req in sig.required_patterns:
            if not req.search(text):
                return 0.0, []
        # Optional matches only — used for scoring ratio
        matched = [p.pattern for p in sig.line_patterns if p.search(text)]
        if len(matched) < sig.min_matches:
            return 0.0, []

        # Confidence scoring — Floor + Boost model:
        #
        # Required patterns all matched (gate enforced) → establishes a floor
        # of FLOOR_PCT (85%) of the signature's base confidence.
        # Each optional pattern that matches adds a proportional boost,
        # filling the remaining headroom up to the full base confidence.
        #
        # Example (base_confidence=0.97, 5 optional patterns):
        #   required only (0/5 opt) → 0.97 × 0.85           = 0.8245  (82.5%)
        #   required + 2/5 opt      → 0.97 × (0.85 + 0.06)  = 0.8882  (88.8%)
        #   required + 5/5 opt      → 0.97 × 1.00            = 0.9700  (97.0%)
        #
        # Files with no required patterns are scored purely on optional ratio.
        # Score is always ≤ base_confidence.
        FLOOR_PCT = 0.85   # floor when required patterns match but no optionals

        req_total   = len(sig.required_patterns)
        opt_total   = len(sig.line_patterns)
        opt_matched = len(matched)   # optional-only matches

        if req_total > 0 and opt_total > 0:
            # Floor from required match + proportional boost from optionals
            opt_ratio = opt_matched / opt_total
            ratio = FLOOR_PCT + (1.0 - FLOOR_PCT) * opt_ratio
        elif req_total > 0:
            # Required patterns only, no optionals defined — full score
            ratio = 1.0
        else:
            # Optional patterns only — scored purely on match ratio
            ratio = opt_matched / max(opt_total, 1)

        return round(sig.confidence * ratio, 4), matched

    def _best(self, raw, lines):
        header = "\n".join(lines[:5])
        best_score, best_result = 0.0, None
        for sig in self.signatures:
            score, matched = self._score(sig, raw, lines, header)
            if score > best_score:
                best_score = score
                best_result = ClassificationResult(
                    sourcetype=sig.sourcetype, category=sig.category,
                    vendor=sig.vendor, product=sig.product,
                    confidence=score,
                    matched_patterns=[p.pattern for p in sig.required_patterns] + matched,
                    required_patterns=[p.pattern for p in sig.required_patterns],
                    file_level=sig.file_level,
                )
        return best_result or ClassificationResult("unknown","unknown","Unknown","Unknown",0.0)

    def classify(self, file_path):
        max_bytes = self.settings.get("file_read_bytes", 8192)
        max_lines = self.settings.get("max_sample_lines", 20)

        # Route through format-specific parsers before text classification
        try:
            raw = _extract_text(file_path, max_bytes)
        except Exception as e:
            logger.error(f"Read error {file_path}: {e}")
            return ClassificationResult("unknown","unknown","Unknown","Unknown",0.0)

        if not raw:
            return ClassificationResult("unknown","unknown","Unknown","Unknown",0.0)

        lines = [l for l in raw.splitlines() if l.strip()][:max_lines]
        return self._best(raw, lines)

    def classify_text(self, text):
        max_lines = self.settings.get("max_sample_lines", 20)
        lines = [l for l in text.splitlines() if l.strip()][:max_lines]
        return self._best("\n".join(lines), lines)

    def _load_raw(self):
        with open(self.signatures_path, "r") as f:
            return yaml.safe_load(f)

    def _save_raw(self, config):
        with open(self.signatures_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def add_signature(self, entry):
        config = self._load_raw()
        sigs = config.get("signatures", [])
        for s in sigs:
            if s.get("sourcetype") == entry.get("sourcetype") and s.get("product","") == entry.get("product",""):
                return False
        sigs.append(entry)
        config["signatures"] = sigs
        self._save_raw(config)
        self.reload()
        return True

    def update_signature_patterns(self, sourcetype, new_patterns, min_matches=None,
                                  required_patterns=None, filter_mode=None,
                                  line_filter=None, multiline_mode=None):
        config = self._load_raw()
        sigs = config.get("signatures", [])
        updated = False
        for s in sigs:
            if s.get("sourcetype") == sourcetype:
                s["line_patterns"] = new_patterns
                if min_matches is not None:
                    s["min_matches"] = min_matches
                if required_patterns is not None:
                    if required_patterns:
                        s["required_patterns"] = required_patterns
                    else:
                        s.pop("required_patterns", None)
                # Cleaning config — only set if explicitly provided
                if filter_mode is not None:
                    if filter_mode:
                        s["filter_mode"] = filter_mode
                    else:
                        s.pop("filter_mode", None)
                if line_filter is not None:
                    if line_filter:
                        s["line_filter"] = line_filter
                    else:
                        s.pop("line_filter", None)
                if multiline_mode is not None:
                    if multiline_mode:
                        s["multiline_mode"] = multiline_mode
                    else:
                        s.pop("multiline_mode", None)
                updated = True
                break
        if updated:
            config["signatures"] = sigs
            self._save_raw(config)
            self.reload()
        return updated

    def get_signature_detail(self, sourcetype):
        config = self._load_raw()
        for s in config.get("signatures", []):
            if s.get("sourcetype") == sourcetype:
                return s
        return None

    def delete_signature(self, sourcetype):
        config = self._load_raw()
        sigs = config.get("signatures", [])
        new_sigs = [s for s in sigs if s.get("sourcetype") != sourcetype]
        if len(new_sigs) == len(sigs):
            return False
        config["signatures"] = new_sigs
        self._save_raw(config)
        self.reload()
        return True

    def list_signatures_raw(self):
        return self._load_raw().get("signatures", [])
