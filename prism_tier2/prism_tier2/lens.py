"""
lens.py - PRISM Lens Module
AI-powered log analysis using LogWhisperer + Ollama.
Provides initial summary and interactive chat about classified log files.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent
LOGWHISPERER_DIR = BASE_DIR / "logwhisperer"
OLLAMA_URL       = os.environ.get("PRISM_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL     = os.environ.get("PRISM_OLLAMA_MODEL", "mistral")
MAX_LOG_CHARS    = 8000   # chars of log content sent to LLM as context
MAX_HISTORY      = 20     # max conversation turns kept in context


# ── LogWhisperer integration ──────────────────────────────────────────────────

def run_logwhisperer(file_path: str, sourcetype: str = "") -> str:
    """
    Run LogWhisperer on a file and return the summary text.
    Falls back to direct Ollama call if LogWhisperer is unavailable.
    """
    file_path = _normalize_path(file_path)
    lw_script = LOGWHISPERER_DIR / "logwhisperer.py"

    if lw_script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(lw_script),
                 "--source", "file",
                 "--logfile", file_path,
                 "--model", OLLAMA_MODEL],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "OLLAMA_HOST": OLLAMA_URL}
            )
            output = result.stdout.strip()
            if output:
                logger.info(f"LogWhisperer summary for {file_path}")
                return output
            if result.stderr:
                logger.warning(f"LogWhisperer stderr: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning("LogWhisperer timed out — falling back to direct Ollama")
        except Exception as e:
            logger.warning(f"LogWhisperer failed: {e} — falling back to direct Ollama")

    # Fallback: call Ollama directly
    return _direct_summarize(file_path, sourcetype)


def _direct_summarize(file_path: str, sourcetype: str) -> str:
    """Call Ollama directly to summarize the log file."""
    try:
        content = _read_log_sample(file_path)
        st_hint = f" This is a {sourcetype} log." if sourcetype else ""

        prompt = (
            f"You are a security analyst. Analyze the following log file sample and provide:\n"
            f"1. A concise summary of what this log contains\n"
            f"2. Any notable events, errors, or security concerns\n"
            f"3. Key entities (IPs, users, hostnames, services) observed\n"
            f"4. Overall assessment (normal activity / suspicious / requires investigation){st_hint}\n\n"
            f"Log sample:\n```\n{content}\n```"
        )
        return _ollama_chat([{"role": "user", "content": prompt}])
    except Exception as e:
        logger.error(f"Direct summarize failed: {e}")
        return f"Analysis failed: {e}"


# ── Ollama chat ───────────────────────────────────────────────────────────────

def _ollama_chat(messages: list, stream: bool = False) -> str:
    """Send messages to Ollama and return the response text."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_URL}. "
            "Is Ollama running? Try: ollama serve"
        )
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


def chat_with_context(file_path: str, sourcetype: str,
                      summary: str, messages: list,
                      user_message: str) -> str:
    """
    Continue a conversation about a log file, or free chat if no file.
    Builds context from the file sample + previous conversation.
    """
    # Free chat mode — no file path, no log context
    if not file_path or not Path(file_path).exists():
        system = (
            "You are a helpful AI assistant with expertise in cybersecurity, "
            "log analysis, and IT operations. Answer questions clearly and concisely."
        )
    else:
        log_sample = _read_log_sample(file_path)
        st_hint    = f"Sourcetype: {sourcetype}\n" if sourcetype else ""
        system = (
            f"You are an expert security log analyst. You are analyzing a log file.\n"
            f"{st_hint}"
            f"Log sample (first {MAX_LOG_CHARS} chars):\n```\n{log_sample}\n```\n\n"
            f"Initial analysis summary:\n{summary}\n\n"
            f"Answer the user's questions about this log concisely and accurately."
        )

    # Build message history for context (capped)
    history = [{"role": "system", "content": system}]
    for m in messages[-MAX_HISTORY:]:
        history.append({"role": m["role"], "content": m["content"]})
    history.append({"role": "user", "content": user_message})

    return _ollama_chat(history)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_path(file_path: str) -> str:
    """Convert Windows WSL UNC paths to Linux paths."""
    import re
    p = file_path.strip()
    m = re.match(r'^\\\\wsl[\$.]?[^\\\\]*\\\\[^\\\\]+\\\\(.+)$', p)
    if m:
        return '/' + m.group(1).replace('\\', '/')
    return file_path

def _read_log_sample(file_path: str) -> str:
    """Read a sample of the log file for LLM context."""
    try:
        file_path = _normalize_path(file_path)
        p = Path(file_path)
        if not p.exists():
            return f"[File not found: {file_path}]"
        if p.suffix.lower() in {".evtx", ".evt"}:
            # Use EVTX parser to get readable XML
            sys.path.insert(0, str(BASE_DIR))
            from parsers.evtx_parser import extract_text
            text = extract_text(file_path, max_events=10)
            return text[:MAX_LOG_CHARS] if text else "[Could not parse EVTX]"
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(MAX_LOG_CHARS)
    except Exception as e:
        return f"[Could not read file: {e}]"


def check_ollama() -> dict:
    """Check if Ollama is running and the model is available."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"].split(":")[0] for m in resp.json().get("models", [])]
        model_available = OLLAMA_MODEL in models or any(
            OLLAMA_MODEL in m for m in models
        )
        return {
            "running":         True,
            "model_available": model_available,
            "model":           OLLAMA_MODEL,
            "models":          models,
            "ollama_url":      OLLAMA_URL,
        }
    except Exception as e:
        return {
            "running":         False,
            "model_available": False,
            "model":           OLLAMA_MODEL,
            "error":           str(e),
            "ollama_url":      OLLAMA_URL,
        }
