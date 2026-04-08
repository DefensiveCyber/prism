"""
parsers/evtx_parser.py - Parse Windows .evt/.evtx binary files into text.

Uses python-evtx if installed. Falls back to magic-byte detection stub
that produces synthetic XML matching the WinEventLog:evtx signature.

Install for full parsing:
    pip3 install python-evtx --break-system-packages
"""

from pathlib import Path


def _evtx_stub(file_path: str) -> str:
    """
    Detect EVTX by magic bytes and return synthetic XML that matches
    the WinEventLog:evtx signature. Works without python-evtx installed.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
        if header[:7] == b"ElfFile":
            return (
                "<!-- Windows EVTX binary log file -->\n"
                "<Event xmlns=\"http://schemas.microsoft.com/win/2004/08/events/event\">\n"
                "  <s>\n"
                "    <Channel>Windows Event Log (EVTX binary)</Channel>\n"
                "    <EventID>0</EventID>\n"
                "  </s>\n"
                "</Event>\n"
                "<!-- Install python-evtx for full parsing: "
                "pip3 install python-evtx --break-system-packages -->"
            )
    except Exception:
        pass
    return ""


def extract_text(file_path: str, max_events: int = 20) -> str:
    """
    Parse a .evtx file and return the first max_events records as XML text.
    Falls back to stub when python-evtx isn't installed.
    """
    try:
        import Evtx.Evtx as evtx
        lines = []
        count = 0
        with evtx.Evtx(file_path) as log:
            for record in log.records():
                if count >= max_events:
                    break
                try:
                    lines.append(record.xml())
                    count += 1
                except Exception:
                    continue
        return "\n".join(lines) if lines else _evtx_stub(file_path)
    except ImportError:
        return _evtx_stub(file_path)
    except Exception:
        return _evtx_stub(file_path)


def is_evtx(file_path: str) -> bool:
    p = Path(file_path)
    if p.suffix.lower() in {".evtx", ".evt"}:
        return True
    try:
        with open(file_path, "rb") as f:
            return f.read(7) == b"ElfFile"
    except Exception:
        return False
