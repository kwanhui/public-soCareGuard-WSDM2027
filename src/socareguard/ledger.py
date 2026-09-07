"""Append-only audit ledger with a hash chain.

One JSON row per proxied request: what left the premises (hash and counts, never the
payload), to which provider under which transfer basis, what came back, what the screen
decided, and any practitioner override with its reason. This is the accountability
artefact that PDPC's Advisory Guidelines on Use of Personal Data in Generative AI (§9.3)
describe when they ask deployers to track prompts and outputs as data sources.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("SOCAREGUARD_LEDGER", "vault/ledger.jsonl"))


def _canon(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Ledger:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        # Appends from concurrent requests serialise here; otherwise two writers can read the
        # same predecessor hash and fork the chain.
        self.lock = threading.Lock()

    def last_hash(self) -> str | None:
        last = None
        with self.path.open() as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["row_sha256"]
        return last

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            prev = self.last_hash()
            body = {"ts": time.time(), **fields, "prev_sha256": prev}
            row_hash = hashlib.sha256(_canon(body).encode()).hexdigest()
            row = {**body, "row_sha256": row_hash}
            with self.path.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return row

    def rows(self) -> list[dict[str, Any]]:
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def verify(self) -> tuple[bool, int]:
        """Recompute the chain. Returns (ok, first bad row index or row count)."""
        prev = None
        for i, row in enumerate(self.rows()):
            body = {k: v for k, v in row.items() if k != "row_sha256"}
            if body.get("prev_sha256") != prev:
                return False, i
            if hashlib.sha256(_canon(body).encode()).hexdigest() != row["row_sha256"]:
                return False, i
            prev = row["row_sha256"]
        return True, len(self.rows())
