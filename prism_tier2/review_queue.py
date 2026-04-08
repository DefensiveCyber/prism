"""
review_queue.py - Tracks files in the review queue and manages manual classification.
Writes sample lines alongside unclassified files for human review.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

SAMPLE_LINES = 100


class ReviewQueue:
    def __init__(self, queue_dir: str, state_dir: str):
        self.queue_dir = Path(queue_dir)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "review_queue_state.json"
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                return {"reviewed": [], "pending": []}
        return {"reviewed": [], "pending": []}

    def _save_state(self):
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def add(self, file_path: str, result_dict: dict, sample_lines: list):
        """Add a file to the review queue with metadata and sample lines."""
        entry = {
            "file": str(file_path),
            "added": datetime.now().isoformat(),
            "classification": result_dict,
            "sample_lines": sample_lines[:SAMPLE_LINES],
            "reviewed": False,
            "assigned_sourcetype": None,
        }
        self.state["pending"].append(entry)
        self._save_state()

        # Write a human-readable review file
        review_path = Path(file_path).with_suffix(".review.txt")
        with open(review_path, "w") as f:
            f.write("=" * 70 + "\n")
            f.write("LOG CLASSIFIER - REVIEW REQUIRED\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"File:       {file_path}\n")
            f.write(f"Added:      {entry['added']}\n")
            f.write(f"Best guess: {result_dict.get('sourcetype', 'unknown')}\n")
            f.write(f"Confidence: {result_dict.get('confidence', 0.0):.2%}\n")
            f.write(f"Vendor:     {result_dict.get('vendor', 'Unknown')}\n")
            f.write(f"Product:    {result_dict.get('product', 'Unknown')}\n\n")
            f.write("--- SAMPLE LOG LINES ---\n\n")
            for line in sample_lines[:SAMPLE_LINES]:
                f.write(line + "\n")
            f.write("\n--- MATCHED PATTERNS ---\n\n")
            for p in result_dict.get("matched_patterns", []):
                f.write(f"  {p}\n")
            f.write("\n" + "=" * 70 + "\n")
            f.write("ACTION REQUIRED:\n")
            f.write("1. Review the sample lines above\n")
            f.write("2. Identify the correct sourcetype\n")
            f.write("3. Run: python main.py resolve --file <path> --sourcetype <sourcetype>\n")
            f.write("4. Add a new signature to config/signatures.yaml to handle this automatically\n")

        logger.info(f"Added to review queue: {file_path}")

    def resolve(self, file_path: str, sourcetype: str):
        """Mark a queued file as reviewed with a manually assigned sourcetype."""
        for entry in self.state["pending"]:
            if entry["file"] == str(file_path):
                entry["reviewed"] = True
                entry["assigned_sourcetype"] = sourcetype
                entry["resolved_at"] = datetime.now().isoformat()
                self.state["reviewed"].append(entry)
                self.state["pending"].remove(entry)
                self._save_state()
                logger.info(f"Resolved {file_path} as sourcetype={sourcetype}")
                return True
        logger.warning(f"File not found in review queue: {file_path}")
        return False

    def list_pending(self) -> list:
        """Return all pending review queue entries."""
        return self.state.get("pending", [])

    def summary(self) -> dict:
        return {
            "pending": len(self.state.get("pending", [])),
            "reviewed": len(self.state.get("reviewed", [])),
        }
