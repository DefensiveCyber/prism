"""
cleaner.py — PRISM Log File Cleaner

Strips dirty/non-conforming content from log files before they are routed
to landing zones. Supports three filter modes:

  line      — one event per line; strip lines not matching line_filter
  multiline — events span multiple lines; strip by event block boundaries
  passthrough — no cleaning; route file as-is

Dirty lines are written to a sidecar .noise file alongside the clean output
so nothing is permanently lost.
"""

import re
import json
import logging
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────

def clean_file(source_path: str, dest_path: str,
               filter_mode: str, line_filter: str = "",
               multiline_mode: str = "") -> dict:
    """
    Clean a log file and write clean content to dest_path.
    Noise (non-conforming lines/events) goes to dest_path + '.noise'.

    Args:
        source_path:    Original file path
        dest_path:      Where clean output should be written
        filter_mode:    'line' | 'multiline' | 'passthrough'
        line_filter:    Regex pattern a valid line must match (mode=line)
        multiline_mode: 'json_lines' | 'json_object' | 'xml_event' |
                        'zeek_tsv' | 'iis' | 'cef_multiline'

    Returns:
        dict with keys: total, clean, noise, noise_path, skipped_reason
    """
    src = Path(source_path)
    dst = Path(dest_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    noise_path = dst.parent / (dst.stem + '.noise' + dst.suffix)

    stats = {"total": 0, "clean": 0, "noise": 0,
             "noise_path": None, "skipped_reason": None}

    if filter_mode == "passthrough" or (not filter_mode):
        # No cleaning — just copy
        import shutil
        shutil.copy2(source_path, dest_path)
        stats["skipped_reason"] = "passthrough"
        return stats

    try:
        raw = src.read_bytes()
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"cleaner: cannot read {source_path}: {e}")
        stats["skipped_reason"] = str(e)
        return stats

    if filter_mode == "line":
        clean_lines, noise_lines = _filter_lines(text, line_filter)
        stats["total"]  = len(clean_lines) + len(noise_lines)
        stats["clean"]  = len(clean_lines)
        stats["noise"]  = len(noise_lines)

    elif filter_mode == "multiline":
        clean_blocks, noise_blocks = _filter_multiline(
            text, multiline_mode, line_filter)
        clean_lines = clean_blocks
        noise_lines = noise_blocks
        stats["total"]  = len(clean_lines) + len(noise_lines)
        stats["clean"]  = len(clean_lines)
        stats["noise"]  = len(noise_lines)

    else:
        import shutil
        shutil.copy2(source_path, dest_path)
        stats["skipped_reason"] = f"unknown filter_mode={filter_mode}"
        return stats

    # Write clean output
    clean_text = "\n".join(clean_lines)
    if clean_text and not clean_text.endswith("\n"):
        clean_text += "\n"
    dst.write_text(clean_text, encoding="utf-8")

    # Write noise sidecar only if there is noise
    if noise_lines:
        noise_text = "\n".join(noise_lines)
        if not noise_text.endswith("\n"):
            noise_text += "\n"
        noise_path.write_text(noise_text, encoding="utf-8")
        stats["noise_path"] = str(noise_path)
        logger.info(f"cleaner: {src.name} → {stats['clean']} clean, "
                    f"{stats['noise']} noise lines")
    else:
        logger.info(f"cleaner: {src.name} → {stats['clean']} clean lines (no noise)")

    return stats


# ── Line-by-line filtering ────────────────────────────────────────────────────

# Patterns that indicate a line is definitely header/banner noise
# regardless of sourcetype
_BANNER_PATTERNS = re.compile(
    r'^[\s=\-\*#~_]{5,}$'           # pure separator lines: ===, ---, ###
    r'|^SHOW\s+\w+'                  # Cisco "show" command output headers
    r'|^CISCO:.+VER\.\s*[\d\.]+'    # CISCO:IOS:XE VER. 19.04
    r'|^[-]{3,}\s*$'                # --- dividers
    r'|^\s*$'                        # blank lines
    r'|^#{1,6}\s'                    # markdown headers
    r'|^={3,}$',                     # === dividers
    re.IGNORECASE
)


def _filter_lines(text: str, line_filter: str) -> tuple[list, list]:
    """
    Split text into clean lines (matching line_filter) and noise lines.
    Always strips banner/separator lines regardless of line_filter.
    """
    try:
        compiled = re.compile(line_filter) if line_filter else None
    except re.error as e:
        logger.warning(f"cleaner: invalid line_filter regex '{line_filter}': {e}")
        compiled = None

    clean, noise = [], []

    for line in text.splitlines():
        stripped = line.rstrip()

        # Always drop pure banner/separator lines
        if _BANNER_PATTERNS.match(stripped):
            if stripped:  # don't count true blanks as noise
                noise.append(stripped)
            continue

        # If no filter, keep everything non-banner
        if compiled is None:
            clean.append(stripped)
            continue

        if compiled.search(stripped):
            clean.append(stripped)
        else:
            noise.append(stripped)

    return clean, noise


# ── Multiline event filtering ─────────────────────────────────────────────────

def _filter_multiline(text: str, mode: str,
                      line_filter: str) -> tuple[list, list]:
    """
    Route to the appropriate multiline extractor based on mode.
    Returns (clean_blocks, noise_blocks) where each element is a
    string representing one complete event/block.
    """
    if mode == "json_lines":
        return _filter_json_lines(text)

    elif mode == "json_object":
        return _filter_json_objects(text, line_filter)

    elif mode == "xml_event":
        return _filter_xml_events(text, line_filter)

    elif mode == "zeek_tsv":
        return _filter_zeek_tsv(text)

    elif mode == "iis":
        return _filter_iis(text)

    elif mode == "csv_with_header":
        return _filter_csv_with_header(text)

    else:
        # Unknown multiline mode — fall back to line filtering
        logger.warning(f"cleaner: unknown multiline_mode='{mode}', "
                       f"falling back to line filter")
        clean, noise = _filter_lines(text, line_filter)
        return clean, noise


def _filter_json_lines(text: str) -> tuple[list, list]:
    """
    NDJSON / JSON-lines: one JSON object per line.
    Valid lines parse as JSON objects/arrays.
    """
    clean, noise = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, (dict, list)):
                clean.append(s)
            else:
                noise.append(s)
        except json.JSONDecodeError:
            # Not JSON — check if it looks like a banner
            if _BANNER_PATTERNS.match(s):
                noise.append(s)
            else:
                noise.append(s)
    return clean, noise


def _filter_json_objects(text: str, line_filter: str) -> tuple[list, list]:
    """
    Multi-line JSON objects. Each object starts with '{' and ends with '}'.
    Strategy: accumulate lines into a buffer, attempt JSON parse when
    brace depth returns to 0. Non-JSON preamble goes to noise.
    """
    clean, noise = [], []
    buffer = []
    depth = 0
    in_string = False
    escape_next = False

    for line in text.splitlines():
        s = line.rstrip()

        # If we're not inside a JSON object yet, check if this line starts one
        if depth == 0 and not buffer:
            stripped = s.strip()
            if not stripped:
                continue
            if stripped.startswith("{") or stripped.startswith("["):
                buffer.append(s)
                # Count braces on this line
                depth += _count_depth(stripped)
            else:
                # Preamble noise
                if not _BANNER_PATTERNS.match(stripped):
                    noise.append(s)
            continue

        buffer.append(s)
        depth += _count_depth(s)

        if depth <= 0:
            # Complete object
            block = "\n".join(buffer)
            try:
                obj = json.loads(block)
                # Optionally verify against line_filter on the serialized form
                if isinstance(obj, (dict, list)):
                    # Check line_filter against the first line of the block
                    if line_filter:
                        try:
                            if re.search(line_filter, buffer[0]):
                                clean.append(block)
                            else:
                                noise.append(block)
                        except re.error:
                            clean.append(block)
                    else:
                        clean.append(block)
                else:
                    noise.append(block)
            except json.JSONDecodeError:
                noise.append(block)
            buffer = []
            depth = 0

    # Leftover buffer
    if buffer:
        block = "\n".join(buffer)
        try:
            json.loads(block)
            clean.append(block)
        except json.JSONDecodeError:
            noise.append(block)

    return clean, noise


def _count_depth(line: str) -> int:
    """Count net brace/bracket depth change for a line (naive, ignores strings)."""
    depth = 0
    in_str = False
    esc = False
    for ch in line:
        if esc:
            esc = False
            continue
        if ch == '\\' and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in '{[':
            depth += 1
        elif ch in '}]':
            depth -= 1
    return depth


def _filter_xml_events(text: str, line_filter: str) -> tuple[list, list]:
    """
    XML event blocks. Each event starts with an opening tag and ends with
    the matching closing tag. Handles Windows Event Log XML (<Event>...</Event>)
    and similar formats.

    Detects the event tag from the first XML tag found.
    """
    clean, noise = [], []

    # Detect event wrapper tag — look for first element tag
    tag_match = re.search(r'<(\w[\w:]*)[^>]*>', text)
    if not tag_match:
        # No XML found at all — treat as line filter
        return _filter_lines(text, line_filter)

    event_tag = tag_match.group(1)
    open_tag  = f"<{event_tag}"
    close_tag = f"</{event_tag}>"

    # Split on event boundaries
    # Strategy: find all <EventTag...> ... </EventTag> blocks
    pattern = re.compile(
        rf'{re.escape(open_tag)}.*?{re.escape(close_tag)}',
        re.DOTALL
    )

    # Collect everything outside events as noise candidates
    last_end = 0
    for m in pattern.finditer(text):
        # Text before this event
        preamble = text[last_end:m.start()]
        for line in preamble.splitlines():
            s = line.strip()
            if s and not _BANNER_PATTERNS.match(s):
                noise.append(s)

        event_text = m.group(0).strip()
        # Validate against line_filter if provided
        if line_filter:
            try:
                if re.search(line_filter, event_text):
                    clean.append(event_text)
                else:
                    noise.append(event_text)
            except re.error:
                clean.append(event_text)
        else:
            clean.append(event_text)
        last_end = m.end()

    # Trailing content after last event
    trailing = text[last_end:]
    for line in trailing.splitlines():
        s = line.strip()
        if s and not _BANNER_PATTERNS.match(s):
            noise.append(s)

    return clean, noise


def _filter_zeek_tsv(text: str) -> tuple[list, list]:
    """
    Zeek/Bro TSV logs.
    Format:
      #separator \\x09
      #set_separator ,
      #empty_field (empty)
      #unset_field -
      #path conn
      #open 2024-01-01-00-00-00
      #fields ts uid ...
      #types time string ...
      <data lines>
      #close 2024-01-01-00-01-00

    Strategy: keep all #-prefixed header lines and data lines.
    Strip anything that doesn't fit (banners, blank lines).
    """
    clean, noise = [], []
    header_done = False
    fields = []

    for line in text.splitlines():
        s = line.rstrip()
        if not s:
            continue

        if s.startswith('#'):
            clean.append(s)
            if s.startswith('#fields'):
                fields = s.split('\t')[1:]
                header_done = True
            elif s.startswith('#close'):
                header_done = False
        elif header_done:
            # Data line — validate it has right number of tab-separated fields
            parts = s.split('\t')
            if fields and len(parts) < len(fields) // 2:
                noise.append(s)
            else:
                clean.append(s)
        else:
            # Before #fields — could be banner noise
            if _BANNER_PATTERNS.match(s):
                noise.append(s)
            else:
                noise.append(s)  # treat pre-header non-# lines as noise

    return clean, noise


def _filter_iis(text: str) -> tuple[list, list]:
    """
    IIS W3C logs.
    Format:
      #Software: Microsoft Internet Information Services
      #Version: 1.0
      #Date: 2024-01-01 00:00:00
      #Fields: date time ...
      <data lines>

    Keep header comment lines and data lines.
    Strip banners and blank lines.
    """
    clean, noise = [], []
    fields = []
    header_done = False

    for line in text.splitlines():
        s = line.rstrip()
        if not s:
            continue

        if s.startswith('#'):
            clean.append(s)
            if s.lower().startswith('#fields:'):
                fields = s.split()[1:]
                header_done = True
        elif _BANNER_PATTERNS.match(s):
            noise.append(s)
        else:
            clean.append(s)

    return clean, noise


def _filter_csv_with_header(text: str) -> tuple[list, list]:
    """
    CSV logs with a header row.
    Keep the header row and data rows.
    Strip banner/separator lines before the header.
    """
    clean, noise = [], []
    header_found = False

    for line in text.splitlines():
        s = line.rstrip()
        if not s:
            continue

        if not header_found:
            if _BANNER_PATTERNS.match(s):
                noise.append(s)
            else:
                # First non-banner line is the header
                clean.append(s)
                header_found = True
        else:
            if _BANNER_PATTERNS.match(s):
                noise.append(s)
            else:
                clean.append(s)

    return clean, noise


# ── Signature filter mode derivation ─────────────────────────────────────────

def derive_filter_config(sig: dict) -> dict:
    """
    Given a signature dict, return the filter_mode, line_filter,
    and multiline_mode to use for cleaning.

    This is called at classification time so the router knows how to clean.
    Explicit 'filter_mode' / 'line_filter' in the signature YAML take
    precedence over auto-derived values.
    """
    # Explicit overrides in YAML always win
    if sig.get('filter_mode'):
        return {
            'filter_mode':    sig['filter_mode'],
            'line_filter':    sig.get('line_filter', ''),
            'multiline_mode': sig.get('multiline_mode', ''),
        }

    st  = sig.get('sourcetype', '')
    req = sig.get('required_patterns', [])
    req_str = ' '.join(req)

    # ── Multiline: XML events ──────────────────────────────────────────────
    if any(x in req_str for x in [
        '<Event xmlns', '<Channel>', 'EventCode=\\d+'
    ]):
        return {
            'filter_mode':    'multiline',
            'line_filter':    req[0] if req else '',
            'multiline_mode': 'xml_event',
        }

    # ── Multiline: JSON objects ────────────────────────────────────────────
    if any(x in req_str for x in [
        '"eventSource"', '"operationName"', '"logName"', '"eventType"',
        '"CustomerIDString"', '"event_type"\\s*:\\s*"',
        '"kind"\\s*:\\s*"admin#reports', '"Workload"\\s*:\\s*"',
        '"_index"\\s*:\\s*"', '"cluster_id"',
        '"agentId"\\s*:\\s*"', '"vendorId"', '"EventType"\\s*:\\s*"',
        '"issueType"', '"pluginID"', '"nexpose-id"',
        '"QUALYS_ID"', '"cluster\\.name"',
    ]):
        return {
            'filter_mode':    'multiline',
            'line_filter':    req[0] if req else '',
            'multiline_mode': 'json_object',
        }

    # ── Multiline: JSON lines (NDJSON) ─────────────────────────────────────
    if r'^\s*\{' in req_str or st in ('json_no_timestamp', 'elastic:ndjson:export'):
        return {
            'filter_mode':    'multiline',
            'line_filter':    '',
            'multiline_mode': 'json_lines',
        }

    # ── Multiline: Zeek TSV ────────────────────────────────────────────────
    if '#path\\s+' in req_str or '#separator' in req_str:
        return {
            'filter_mode':    'multiline',
            'line_filter':    '',
            'multiline_mode': 'zeek_tsv',
        }

    # ── Multiline: IIS W3C ────────────────────────────────────────────────
    if '#Software: Microsoft Internet Information Services' in req_str:
        return {
            'filter_mode':    'multiline',
            'line_filter':    '',
            'multiline_mode': 'iis',
        }

    # ── Multiline: CSV with header ─────────────────────────────────────────
    if st in ('csv:generic_firewall', 'pan:traffic') and (
        'receive_time,serial' in req_str or
        'src_ip,dst_ip,src_port' in req_str
    ):
        return {
            'filter_mode':    'multiline',
            'line_filter':    req[0] if req else '',
            'multiline_mode': 'csv_with_header',
        }

    # ── Line-by-line: use required_patterns[0] as line filter ─────────────
    if req:
        return {
            'filter_mode':    'line',
            'line_filter':    req[0],
            'multiline_mode': '',
        }

    # ── Passthrough: no patterns to filter by ─────────────────────────────
    return {
        'filter_mode':    'passthrough',
        'line_filter':    '',
        'multiline_mode': '',
    }
