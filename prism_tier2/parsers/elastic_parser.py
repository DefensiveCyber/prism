"""
parsers/elastic_parser.py - Extract classifiable text from Elasticsearch exports.

Elasticsearch exports logs in NDJSON format (one JSON object per line).
Two variants:

1. Filebeat ECS output — already handled by existing elastic:ecs:json signatures.
   Fields like "event.dataset", "event.module", "@timestamp" at the top level.

2. Raw ES index export (via _search or snapshot restore) — each line has an
   Elasticsearch metadata wrapper:
   {"_index":"logs-2024","_id":"abc","_source":{"@timestamp":...,"message":...}}

   This parser unwraps the _source field so the inner document is what the
   classifier sees — which then matches existing ECS/vendor signatures.
"""

import json
from pathlib import Path


def extract_text(file_path: str, max_lines: int = 20) -> str:
    """
    Read an Elasticsearch NDJSON export and return classifiable text.
    Unwraps _source if present. Returns raw lines otherwise.
    """
    try:
        lines = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, raw_line in enumerate(f):
                if i >= max_lines:
                    break
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                    # Unwrap ES export wrapper if present
                    if "_source" in obj:
                        inner = obj["_source"]
                        # Re-serialize the inner document for the classifier
                        lines.append(json.dumps(inner))
                        # Also emit key=value style for regex-based signatures
                        for k, v in inner.items():
                            if isinstance(v, (str, int, float)):
                                lines.append(f"{k}={v}")
                    else:
                        lines.append(raw_line)
                except json.JSONDecodeError:
                    lines.append(raw_line)

        return "\n".join(lines)

    except Exception:
        return ""


def is_elastic_ndjson(file_path: str) -> bool:
    """
    Detect Elasticsearch NDJSON export by peeking at the first line.
    Looks for _index/_source wrapper or ECS @timestamp field.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
        if not first:
            return False
        obj = json.loads(first)
        # ES export wrapper
        if "_index" in obj and "_source" in obj:
            return True
        # ECS direct output (Filebeat style)
        if "@timestamp" in obj and (
            "event.dataset" in obj or
            "event" in obj or
            "log" in obj
        ):
            return True
        return False
    except Exception:
        return False
