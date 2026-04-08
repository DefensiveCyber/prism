"""
parsers/csv_parser.py - Extract classifiable text from CSV log exports.

CSV is a container, not a log type. We read the header row and a sample of
data rows, then produce a text block the classifier can run signatures against.

The header column names are the most reliable signal — they are vendor-specific
and don't change between log entries. Data row values provide secondary signal.
"""

import csv
import io
from pathlib import Path


def extract_text(file_path: str, max_rows: int = 20) -> str:
    """
    Read a CSV file and return a text block suitable for classification.
    The output contains:
      - The header row (most important — column names are vendor-specific)
      - Up to max_rows of data as key=value pairs
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read(65536)  # read up to 64KB

        reader = csv.reader(io.StringIO(raw))
        rows   = list(reader)

        if not rows:
            return ""

        header = rows[0]
        data   = rows[1:max_rows + 1]

        lines = []

        # Line 1: raw header (column names joined — signatures match on these)
        lines.append(",".join(header))

        # Lines 2+: key=value representation so existing regex patterns work
        # e.g. "EventCode=4624 ComputerName=DC01 SourceName=Microsoft-Windows-Security"
        for row in data:
            if len(row) == len(header):
                kv = " ".join(
                    f"{k}={v}" for k, v in zip(header, row) if v.strip()
                )
            else:
                kv = ",".join(row)
            if kv.strip():
                lines.append(kv)

        return "\n".join(lines)

    except Exception:
        return ""


def is_csv(file_path: str) -> bool:
    """Quick check: does this file look like a CSV?"""
    p = Path(file_path)
    if p.suffix.lower() == ".csv":
        return True
    # Sniff the first 512 bytes even without .csv extension
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(512)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|")
        return dialect is not None
    except Exception:
        return False
