"""
watcher.py - Production file system watcher for PRISM Tier 2.
Uses watchdog (inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows)
instead of polling. Each new file dispatches a Celery task.
"""

import logging, os, sys, time
from pathlib import Path
import yaml

# Ensure PRISM modules are on the path regardless of how the watcher is launched
_base = Path(__file__).parent
if str(_base) not in sys.path:
    sys.path.insert(0, str(_base))
# Also honour PYTHONPATH env var (set in .env / systemd)
_env_pp = os.environ.get("PYTHONPATH", "")
for _p in _env_pp.split(os.pathsep):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from celery_app import celery

BASE_DIR      = Path(__file__).parent
SETTINGS_FILE = BASE_DIR / "config" / "settings.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "logs" / "watcher.log"),
    ]
)
logger = logging.getLogger("prism.watcher")

EXCLUDE_SUFFIXES = {".review.txt", ".reason.txt", ".pyc", ".swp", ".ckpt"}


def load_settings():
    with open(SETTINGS_FILE) as f:
        return yaml.safe_load(f) or {}


def should_process(path: Path, settings: dict) -> bool:
    if path.suffix in EXCLUDE_SUFFIXES or path.name.endswith((".review.txt",".reason.txt")):
        return False
    inc = settings.get("include_extensions", [])
    exc = settings.get("exclude_extensions", [])
    if path.suffix in exc:
        return False
    if inc and path.suffix not in inc:
        return False
    return True


class PRISMEventHandler(FileSystemEventHandler):
    def __init__(self, settings):
        self.settings = settings
        self._seen: set = set()

    def on_created(self, event):
        if not event.is_directory:
            self._dispatch(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            self._dispatch(Path(event.dest_path))

    def _dispatch(self, path: Path):
        if str(path) in self._seen or not should_process(path, self.settings):
            return
        time.sleep(0.5)  # let the file finish writing
        if not path.exists() or not path.is_file():
            return
        self._seen.add(str(path))
        logger.info(f"Dispatching: {path.name}")
        celery.send_task("tasks.dispatch_watched_file", args=[str(path)], queue="classify")


class PRISMWatcher:
    def __init__(self):
        self.observer = Observer()
        self.handlers: dict = {}

    def start(self):
        logger.info("PRISM Watcher starting...")
        self._sync_watches()
        self.observer.start()
        logger.info("Watcher running...")
        try:
            while True:
                time.sleep(30)
                self._sync_watches()  # pick up GUI changes to watched_dirs
        except KeyboardInterrupt:
            logger.info("Stopping...")
        finally:
            self.observer.stop()
            self.observer.join()

    def _sync_watches(self):
        settings     = load_settings()
        current_dirs = set(settings.get("watched_dirs", []))
        active_dirs  = set(self.handlers.keys())
        for d in current_dirs - active_dirs:
            dp = Path(d)
            if not dp.is_dir():
                logger.warning(f"Dir not found: {d}")
                continue
            h = PRISMEventHandler(settings)
            w = self.observer.schedule(h, str(dp), recursive=True)
            self.handlers[d] = (h, w)
            logger.info(f"Now watching: {d}")
        for d in active_dirs - current_dirs:
            h, w = self.handlers.pop(d)
            self.observer.unschedule(w)
            logger.info(f"Stopped watching: {d}")


if __name__ == "__main__":
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
    PRISMWatcher().start()
