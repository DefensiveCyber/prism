"""
server.py - PRISM Flask web server (Tier 2 production).
Run with Gunicorn: gunicorn -c gunicorn.conf.py server:app
"""

import os, time, tempfile
from pathlib import Path
import yaml
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR      = Path(__file__).parent
SIGS_FILE     = BASE_DIR / "config" / "signatures.yaml"
SETTINGS_FILE = BASE_DIR / "config" / "settings.yaml"
STATE_DIR     = BASE_DIR / "state"
LOG_DIR       = BASE_DIR / "logs"

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_settings():
    with open(SETTINGS_FILE) as f:
        return yaml.safe_load(f) or {}

def save_settings(cfg):
    with open(SETTINGS_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

def get_clf():
    from classifier import LogClassifier
    return LogClassifier(str(SIGS_FILE))

def get_router():
    from router import LogRouter
    s = load_settings()
    landing   = BASE_DIR / s.get("landing", {}).get("base_dir", "landing")
    threshold = s.get("classification", {}).get("review_queue_threshold", 0.6)
    return LogRouter(str(landing), review_threshold=threshold)

def _result_resp(filename, rd, destination=None, routed=False, file_path=None):
    return dict(
        filename=filename,
        sourcetype=rd.get("sourcetype"), category=rd.get("category"),
        vendor=rd.get("vendor"), product=rd.get("product"),
        confidence=round(rd.get("confidence", 0), 4),
        confidence_pct=f"{rd.get('confidence', 0):.0%}",
        matched_patterns=rd.get("matched_patterns", []),
        required_patterns=rd.get("required_patterns", []),
        routed=routed, destination=destination,
        file_path=file_path or rd.get("file_path", ""),
    )

# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR / "templates"), "index.html")

@app.route("/favicon.svg")
def favicon():
    return send_from_directory(str(BASE_DIR / "static"), "favicon.svg", mimetype="image/svg+xml")

@app.route("/favicon.ico")
def favicon_ico():
    return send_from_directory(str(BASE_DIR / "static"), "favicon.svg", mimetype="image/svg+xml")

# ── Classify single file ──────────────────────────────────────────────────────

@app.route("/api/classify", methods=["POST"])
def api_classify():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f     = request.files["file"]
    route = request.form.get("route", "false").lower() == "true"

    suffix = Path(f.filename).suffix or ".log"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="px_") as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        from celery_app import celery
        # Submit to priority queue and wait (max 30s) — fast for single files
        task   = celery.send_task("tasks.classify_single_file",
                                  args=[tmp_path, route], queue="priority")
        result = task.get(timeout=30)
        return jsonify(_result_resp(f.filename, result,
                                    destination=str(Path(result.get("destination","")).parent) if result.get("destination") else None,
                                    routed=result.get("routed", False),
                                    file_path=result.get("destination") or tmp_path))
    except Exception as e:
        try: os.unlink(tmp_path)
        except: pass
        return jsonify({"error": str(e)}), 500


@app.route("/api/classify-text", methods=["POST"])
def api_classify_text():
    data = request.get_json() or {}
    if not data.get("text", "").strip():
        return jsonify({"error": "No text"}), 400
    try:
        from celery_app import celery
        task   = celery.send_task("tasks.classify_text",
                                  args=[data["text"]], queue="priority")
        result = task.get(timeout=15)
        return jsonify(_result_resp("(pasted text)", result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Bulk scan ─────────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def api_scan_start():
    data      = request.get_json() or {}
    directory = data.get("directory", "").strip()
    recursive = data.get("recursive", True)
    route     = data.get("route", True)

    if not directory:
        return jsonify({"error": "directory required"}), 400
    if not Path(directory).is_dir():
        return jsonify({"error": f"Not a directory: {directory}"}), 400

    import db
    from celery_app import celery

    # Prevent duplicate scans of the same directory
    active = [j for j in db.get_jobs(limit=10)
              if j["status"] == "running" and j["directory"] == directory]
    if active:
        return jsonify({"error": f"A scan of this directory is already running ({active[0]['job_id']})",
                        "job_id": active[0]["job_id"]}), 409

    job_id = f"scan_{int(time.time()*1000)}"
    db.create_job(job_id, directory, recursive, route)

    task = celery.send_task("tasks.scan_directory",
                            args=[job_id, directory, recursive, route],
                            queue="classify")
    db.update_job(job_id, celery_id=task.id)
    return jsonify({"job_id": job_id})


@app.route("/api/scan/<job_id>")
def api_scan_status(job_id):
    import db
    job = db.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/scan/jobs")
def api_scan_jobs():
    import db
    return jsonify(db.get_jobs())


@app.route("/api/scan/<job_id>/results")
def api_scan_results(job_id):
    """Return per-file results for a completed scan job from audit_log."""
    import db
    job = db.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    rows = db.get_audit_by_job(job_id)
    return jsonify({
        "job_id":  job_id,
        "total":   job["total"],
        "done":    job["done"],
        "errors":  job["errors"],
        "results": rows,
    })


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    import db
    return jsonify(db.get_stats(request.args.get("date")))


# ── Queue ─────────────────────────────────────────────────────────────────────

@app.route("/api/queue")
def api_queue():
    import db
    return jsonify({"summary": db.get_review_summary(),
                    "pending": db.get_pending_reviews()})


@app.route("/api/queue/clear", methods=["POST"])
def api_queue_clear():
    """Remove all unreviewed items from the review queue (keeps files)."""
    import db
    data         = request.get_json() or {}
    delete_files = data.get("delete_files", False)
    count, deleted_files = db.clear_review_queue(delete_files=delete_files)
    return jsonify({"success": True, "cleared": count, "files_deleted": deleted_files})


@app.route("/api/queue/delete-item", methods=["POST"])
def api_queue_delete_item():
    """Remove a single item from the queue, optionally deleting the file too."""
    import db
    data         = request.get_json() or {}
    file_path    = data.get("file", "")
    delete_file  = data.get("delete_file", False)
    if not file_path:
        return jsonify({"error": "file required"}), 400
    ok, file_deleted = db.delete_review_item(file_path, delete_file=delete_file)
    return (jsonify({"success": True, "file_deleted": file_deleted}) if ok
            else jsonify({"error": "Not found"}), 404)


@app.route("/api/queue/resolve", methods=["POST"])
def api_queue_resolve():
    import db, shutil
    from classifier import ClassificationResult
    data       = request.get_json() or {}
    file_path  = data.get("file", "")
    sourcetype = data.get("sourcetype", "")

    if not file_path or not sourcetype:
        return jsonify({"error": "file and sourcetype required"}), 400

    # Mark resolved in DB
    ok = db.resolve_review(file_path, sourcetype)
    if not ok:
        return jsonify({"error": "Not found in queue"}), 404

    # Route the file to the correct landing zone
    destination = None
    if Path(file_path).exists():
        try:
            # Build a minimal result object so the router can name the directory
            fake_result = ClassificationResult(
                sourcetype=sourcetype,
                category="reviewed",
                vendor="Manual",
                product="Manual Review",
                confidence=1.0,
            )
            router = get_router()
            destination = router.route(file_path, fake_result, move=True)
            # Record in audit log
            db.record_audit(file_path, destination,
                            {"sourcetype": sourcetype, "category": "reviewed",
                             "vendor": "Manual", "product": "Manual Review",
                             "confidence": 1.0, "matched_patterns": ["manual review"]})
        except Exception as e:
            # File may have already been moved or deleted — not a fatal error
            pass

    return jsonify({"success": True, "destination": destination})


# ── Landing zones ─────────────────────────────────────────────────────────────

@app.route("/api/landing")
def api_landing():
    return jsonify(get_router().list_landing_dirs())


@app.route("/api/landing/add", methods=["POST"])
def api_landing_add():
    data = request.get_json() or {}
    name = data.get("name", "").strip().replace(" ", "_").replace("/", "_")
    if not name:
        return jsonify({"error": "name required"}), 400
    s       = load_settings()
    landing = BASE_DIR / s.get("landing", {}).get("base_dir", "landing")
    (landing / name).mkdir(parents=True, exist_ok=True)
    return jsonify({"created": str(landing / name), "name": name})


# ── Watched directories ───────────────────────────────────────────────────────

@app.route("/api/watched-dirs")
def api_watched_dirs():
    return jsonify(load_settings().get("watched_dirs", []))


@app.route("/api/watched-dirs/add", methods=["POST"])
def api_watched_dirs_add():
    data = request.get_json() or {}
    path = data.get("path", "").strip()
    if not path or not Path(path).is_dir():
        return jsonify({"error": f"Not a directory: {path}"}), 400
    cfg  = load_settings()
    dirs = cfg.get("watched_dirs", [])
    if path not in dirs:
        dirs.append(path)
        cfg["watched_dirs"] = dirs
        save_settings(cfg)
    return jsonify({"watched_dirs": dirs})


@app.route("/api/watched-dirs/remove", methods=["POST"])
def api_watched_dirs_remove():
    data = request.get_json() or {}
    path = data.get("path", "").strip()
    cfg  = load_settings()
    cfg["watched_dirs"] = [d for d in cfg.get("watched_dirs", []) if d != path]
    save_settings(cfg)
    return jsonify({"watched_dirs": cfg["watched_dirs"]})


# ── Watcher status (the watcher is now a separate process) ────────────────────

@app.route("/api/watcher/status")
def api_watcher_status():
    """Check if the watcher process is running by inspecting its PID file."""
    pid_file = BASE_DIR / "logs" / "watcher.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)   # signal 0 = check existence only
            return jsonify({"running": True, "pid": pid})
        except (ProcessLookupError, ValueError):
            pass
    return jsonify({"running": False})


@app.route("/api/watcher/start", methods=["POST"])
def api_watcher_start():
    """Start the watcher as a subprocess (for non-systemd use)."""
    import subprocess
    pid_file = BASE_DIR / "logs" / "watcher.pid"
    proc = subprocess.Popen(
        ["python3", str(BASE_DIR / "watcher.py")],
        cwd=str(BASE_DIR),
        stdout=open(BASE_DIR / "logs" / "watcher.log", "a"),
        stderr=subprocess.STDOUT,
    )
    pid_file.write_text(str(proc.pid))
    return jsonify({"status": "started", "pid": proc.pid})


@app.route("/api/watcher/stop", methods=["POST"])
def api_watcher_stop():
    import signal
    pid_file = BASE_DIR / "logs" / "watcher.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"status": "stopped"})


# ── Signatures ────────────────────────────────────────────────────────────────

@app.route("/api/signatures")
def api_signatures():
    clf  = get_clf()
    return jsonify([{
        "sourcetype":       s.sourcetype, "category": s.category,
        "vendor":           s.vendor,     "product":  s.product,
        "confidence":       s.confidence,
        "patterns":         len(s.line_patterns),
        "required_count":   len(s.required_patterns),
        "min_matches":      s.min_matches,
        "file_level":       s.file_level,
    } for s in clf.signatures])


@app.route("/api/signatures/<path:sourcetype>")
def api_signature_detail(sourcetype):
    detail = get_clf().get_signature_detail(sourcetype)
    return jsonify(detail) if detail else (jsonify({"error": "Not found"}), 404)


@app.route("/api/signatures", methods=["POST"])
def api_signature_add():
    data    = request.get_json() or {}
    missing = [k for k in ["sourcetype","category","vendor","product","line_patterns"] if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400
    entry = {k: data[k] for k in ["sourcetype","category","vendor","product","line_patterns"]}
    entry["confidence"]  = float(data.get("confidence", 0.90))
    entry["min_matches"] = int(data.get("min_matches", 1))
    entry["file_level"]  = bool(data.get("file_level", False))
    if data.get("header_match"):      entry["header_match"]      = data["header_match"]
    if data.get("exclude_patterns"):  entry["exclude_patterns"]  = data["exclude_patterns"]
    ok = get_clf().add_signature(entry)
    return (jsonify({"success": True, "sourcetype": entry["sourcetype"]}) if ok
            else (jsonify({"error": "Duplicate"}), 409))


@app.route("/api/signatures/<path:sourcetype>/patterns", methods=["PUT"])
def api_signature_patterns(sourcetype):
    data = request.get_json() or {}
    if "line_patterns" not in data:
        return jsonify({"error": "line_patterns required"}), 400
    ok = get_clf().update_signature_patterns(
        sourcetype,
        data["line_patterns"],
        data.get("min_matches"),
        data.get("required_patterns"),
        filter_mode   = data.get("filter_mode"),
        line_filter   = data.get("line_filter"),
        multiline_mode= data.get("multiline_mode"),
    )
    return jsonify({"success": ok}) if ok else (jsonify({"error": "Not found"}), 404)


@app.route("/api/signatures/<path:sourcetype>", methods=["DELETE"])
def api_signature_delete(sourcetype):
    ok = get_clf().delete_signature(sourcetype)
    return jsonify({"success": ok}) if ok else (jsonify({"error": "Not found"}), 404)


@app.route("/api/signatures/reload", methods=["POST"])
def api_signatures_reload():
    clf = get_clf()
    clf.reload()
    return jsonify({"success": True, "count": len(clf.signatures)})


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/api/settings")
def api_settings():
    return jsonify(load_settings())


@app.route("/api/settings", methods=["PUT"])
def api_settings_update():
    data = request.get_json() or {}
    cfg  = load_settings()
    if "classification" in data:
        cfg["classification"] = {**cfg.get("classification", {}), **data["classification"]}
    if "include_extensions" in data:
        cfg["include_extensions"] = data["include_extensions"]
    save_settings(cfg)
    return jsonify({"success": True})


# ── Browse / open folder ──────────────────────────────────────────────────────

@app.route("/api/browse")
def api_browse():
    import platform, string
    req_path = request.args.get("path", "").strip()
    if not req_path:
        if platform.system() == "Windows":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
            return jsonify({"path": "", "parent": None, "drives": drives, "dirs": []})
        else:
            req_path = str(Path.home())
    p = Path(req_path)
    if not p.exists() or not p.is_dir():
        return jsonify({"error": f"Not a directory: {req_path}"}), 400
    try:
        dirs = sorted([str(c) for c in p.iterdir()
                       if c.is_dir() and not c.name.startswith(".")],
                      key=lambda x: x.lower())
    except PermissionError:
        dirs = []
    return jsonify({"path": str(p), "parent": str(p.parent) if p.parent != p else None,
                    "dirs": dirs, "name": p.name or str(p)})


@app.route("/api/browse/files")
def api_browse_files():
    """List files in a directory for Lens directory scan."""
    from lens import _normalize_path
    req_path = _normalize_path(request.args.get("path", "").strip())
    if not req_path:
        return jsonify({"error": "path required"}), 400
    p = Path(req_path)
    if not p.exists() or not p.is_dir():
        return jsonify({"error": f"Not a directory: {req_path}"}), 400
    try:
        files = sorted(
            [{"name": c.name,
              "path": str(c),
              "size": c.stat().st_size,
              "type": "file"}
             for c in p.iterdir()
             if c.is_file() and not c.name.startswith(".")],
            key=lambda x: x["name"]
        )
        return jsonify({"path": str(p), "files": files, "count": len(files)})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403


@app.route("/api/open-folder")
def api_open_folder():
    import subprocess, platform
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    p = Path(path)
    # If a file path was passed, open its parent directory
    if p.exists() and p.is_file():
        p = p.parent
    if not p.exists() or not p.is_dir():
        return jsonify({"error": f"Not found: {path}"}), 404
    try:
        system = platform.system()
        # Detect WSL2: /proc/version contains 'microsoft' or 'WSL'
        is_wsl = False
        try:
            proc_ver = Path("/proc/version").read_text().lower()
            is_wsl   = "microsoft" in proc_ver or "wsl" in proc_ver
        except Exception:
            pass

        if system == "Windows":
            subprocess.Popen(["explorer", str(p)])
            return jsonify({"opened": str(p), "method": "explorer"})

        elif is_wsl:
            # WSL2: convert Linux path to Windows path and open with explorer.exe
            # Use powershell.exe which is always available at a known path in WSL2
            win_path = str(p)
            if win_path.startswith("/mnt/") and len(win_path) > 6:
                # /mnt/c/foo/bar → C:\foo\bar
                drive    = win_path[5].upper()
                rest     = win_path[6:].replace("/", "\\")
                win_path = f"{drive}:{rest}"
            else:
                # Path is inside WSL2 filesystem (/home/..., /root/..., etc.)
                # Use PRISM_WSL_DISTRO env var if set, otherwise auto-detect
                distro = os.environ.get("PRISM_WSL_DISTRO", "").strip()
                if not distro:
                    try:
                        # wsl.exe -l outputs UTF-16-LE — decode properly
                        result = subprocess.run(
                            ["/mnt/c/Windows/System32/wsl.exe", "-l"],
                            capture_output=True
                        )
                        output = result.stdout.decode("utf-16-le", errors="ignore")
                        for line in output.splitlines():
                            line = line.strip().lstrip("\ufeff")
                            if not line or "NAME" in line or "Windows" in line:
                                continue
                            name = line.lstrip("* ").split()[0].strip()
                            if name:
                                distro = name
                                break
                    except Exception:
                        pass
                if not distro:
                    distro = "Ubuntu"
                linux_path = str(p).replace("/", "\\")
                win_path   = f"\\\\wsl$\\{distro}{linux_path}"

            # Use cmd.exe /c start — most reliable way to open a folder from WSL2
            # Works with UNC paths like \\wsl$\Ubuntu\... and drive paths like C:\...
            cmd = "/mnt/c/Windows/System32/cmd.exe"
            if Path(cmd).exists():
                subprocess.Popen([cmd, "/c", "start", "", win_path])
            else:
                subprocess.Popen(["explorer.exe", win_path])
            return jsonify({"opened": str(p), "win_path": win_path, "method": "cmd_start"})

        elif system == "Darwin":
            subprocess.Popen(["open", str(p)])
            return jsonify({"opened": str(p), "method": "open"})

        else:
            # Native Linux — try xdg-open, fall back to path copy
            result = subprocess.run(["which", "xdg-open"], capture_output=True)
            if result.returncode == 0:
                subprocess.Popen(["xdg-open", str(p)])
                return jsonify({"opened": str(p), "method": "xdg-open"})
            else:
                return jsonify({"note": f"Headless server — path: {path}", "path": str(p)})

    except Exception as e:
        return jsonify({"note": f"Could not open automatically. Path: {path}", "path": str(p)})


@app.route("/api/file/view")
def api_file_view():
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    p = Path(path)
    if not p.exists() or not p.is_file():
        return jsonify({"error": f"Not found: {path}"}), 404
    try:
        size = p.stat().st_size
        size_human = (f"{size} B" if size < 1024
                      else f"{size/1024:.1f} KB" if size < 1048576
                      else f"{size/1048576:.1f} MB")
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total    = len(lines)
        shown    = lines[:500]
        return jsonify({"path": str(p), "filename": p.name, "size_human": size_human,
                        "total_lines": total, "lines_shown": len(shown),
                        "truncated": total > 500, "content": "".join(shown)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Run (dev only — use gunicorn in production) ───────────────────────────────


@app.route("/api/cleaning/derived")
def api_cleaning_derived():
    """Return all signatures with their explicit + derived cleaning config."""
    from cleaner import derive_filter_config
    clf    = get_clf()
    config = clf._load_raw()
    result = []
    for raw in config.get("signatures", []):
        try:
            derived = derive_filter_config(raw)
            result.append({
                "sourcetype":          raw.get("sourcetype", ""),
                "category":            raw.get("category", ""),
                "vendor":              raw.get("vendor", ""),
                "product":             raw.get("product", ""),
                # Explicit overrides saved in YAML
                "filter_mode":         raw.get("filter_mode", ""),
                "line_filter":         raw.get("line_filter", ""),
                "multiline_mode":      raw.get("multiline_mode", ""),
                # What will actually run (derived if not explicit)
                "eff_mode":            raw.get("filter_mode") or derived["filter_mode"],
                "eff_filter":          raw.get("line_filter") or derived["line_filter"],
                "eff_multiline":       raw.get("multiline_mode") or derived["multiline_mode"],
                "is_custom":           bool(raw.get("filter_mode") or
                                            raw.get("line_filter") or
                                            raw.get("multiline_mode")),
                # enabled=True by default; False disables cleaning for this sig
                "cleaning_enabled":    raw.get("cleaning_enabled", True),
            })
        except Exception as e:
            result.append({
                "sourcetype": raw.get("sourcetype", "unknown"),
                "category":   raw.get("category", ""),
                "eff_mode":   "passthrough",
                "eff_filter": "", "eff_multiline": "",
                "is_custom":  False, "error": str(e),
            })
    return jsonify(result)


@app.route("/api/cleaning/<path:sourcetype>/toggle", methods=["POST"])
def api_cleaning_toggle(sourcetype):
    """Enable or disable cleaning for a signature."""
    data    = request.get_json() or {}
    enabled = data.get("enabled", True)
    clf     = get_clf()
    config  = clf._load_raw()
    updated = False
    for s in config.get("signatures", []):
        if s.get("sourcetype") == sourcetype:
            s["cleaning_enabled"] = enabled
            updated = True
            break
    if updated:
        clf._save_raw(config)
        clf.reload()
        return jsonify({"success": True, "cleaning_enabled": enabled})
    return jsonify({"error": "Not found"}), 404


# ══════════════════════════════════════════════════════════════ LENS (AI ANALYSIS)

@app.route("/api/lens/status")
def api_lens_status():
    from lens import check_ollama
    return jsonify(check_ollama())


@app.route("/api/lens/analyze", methods=["POST"])
def api_lens_analyze():
    import db
    from lens import run_logwhisperer, OLLAMA_MODEL
    data       = request.get_json() or {}
    file_path  = data.get("file_path", "").strip()
    sourcetype = data.get("sourcetype", "")
    free_chat  = data.get("free_chat", False)

    # Free chat mode — no file required, create a blank session
    if free_chat or not file_path:
        try:
            summary    = "Free chat session — no log file"
            session_id = db.create_lens_session("", "mistral", summary, OLLAMA_MODEL)
            return jsonify({"session_id": session_id, "summary": summary})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if not Path(file_path).exists():
        return jsonify({"error": f"File not found: {file_path}"}), 404

    try:
        summary    = run_logwhisperer(file_path, sourcetype)
        session_id = db.create_lens_session(file_path, sourcetype, summary, OLLAMA_MODEL)
        return jsonify({"session_id": session_id, "summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lens/chat", methods=["POST"])
def api_lens_chat():
    import db
    from lens import chat_with_context
    data       = request.get_json() or {}
    session_id = data.get("session_id")
    message    = data.get("message", "").strip()

    if not session_id or not message:
        return jsonify({"error": "session_id and message required"}), 400

    session = db.get_lens_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    try:
        db.append_lens_message(session_id, "user", message)
        response = chat_with_context(
            file_path   = session["file_path"],
            sourcetype  = session["sourcetype"],
            summary     = session["summary"],
            messages    = session["messages"],
            user_message= message,
        )
        db.append_lens_message(session_id, "assistant", response)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lens/sessions")
def api_lens_sessions():
    import db
    return jsonify(db.get_lens_sessions())


@app.route("/api/lens/session/<int:session_id>")
def api_lens_session(session_id):
    import db
    s = db.get_lens_session(session_id)
    return jsonify(s) if s else (jsonify({"error": "Not found"}), 404)


@app.route("/api/lens/session/<int:session_id>", methods=["DELETE"])
def api_lens_session_delete(session_id):
    import db
    ok = db.delete_lens_session(session_id)
    return jsonify({"success": ok}) if ok else (jsonify({"error": "Not found"}), 404)


if __name__ == "__main__":
    import db
    for d in [STATE_DIR, LOG_DIR, BASE_DIR/"templates"]:
        d.mkdir(parents=True, exist_ok=True)
    s       = load_settings()
    landing = BASE_DIR / s.get("landing", {}).get("base_dir", "landing")
    landing.mkdir(parents=True, exist_ok=True)
    db.init_db()
    print("=" * 55)
    print("  PRISM — WARNING: Use gunicorn in production!")
    print("  gunicorn -c gunicorn.conf.py server:app")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
