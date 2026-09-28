"""Append-only audit ledger with a hash chain.

One JSON row per proxied request: what left the premises (hash and counts, never the
payload), to which provider under the transfer-basis statement the deployer set, what came
back, what the screen decided, and any practitioner override with its reason. PDPC's Advisory
Guidelines on Use of Personal Data in Generative AI (section 9.3) ask deployers to keep this kind
of record of prompts and outputs.

Each row carries its sequence number (``seq``, the row's position in the file) and the hash of
the previous row, and both are inside the row's own hash. ``report`` therefore detects an edit
to any row, a reordering, and a deleted middle row. A party with write access to the file can
still rewrite every row from some point onwards, or cut the tail, and produce a file that
verifies on its own. Every append therefore logs the new head hash and row count at INFO on the
``socareguard.ledger`` logger; shipping that log off the host is the deployer's step, and a
verifier compares the file against the last shipped head (``expected_rows``, ``head_sha256``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("SOCAREGUARD_LEDGER", "vault/ledger.jsonl"))
log = logging.getLogger("socareguard.ledger")


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

    def _tail(self) -> tuple[str | None, int]:
        """The last row's hash and the number of rows."""
        last, n = None, 0
        with self.path.open() as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["row_sha256"]
                    n += 1
        return last, n

    def last_hash(self) -> str | None:
        return self._tail()[0]

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            prev, n = self._tail()
            body = {"ts": time.time(), **fields, "seq": n, "prev_sha256": prev}
            row_hash = hashlib.sha256(_canon(body).encode()).hexdigest()
            row = {**body, "row_sha256": row_hash}
            with self.path.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            # The anchor line: a log shipper that copies it off the host lets a verifier detect
            # a rewritten suffix or a cut tail, which the file alone cannot show.
            log.info("ledger head %s rows %d", row_hash, n + 1)
            return row

    def rows(self) -> list[dict[str, Any]]:
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def report(self, expected_rows: int | None = None) -> dict[str, Any]:
        """Recompute the chain and the sequence.

        Returns ``ok``, ``rows``, ``head_sha256`` (the last row's hash), ``first_bad_row`` (the
        first row whose hash or link does not match), ``first_seq_gap`` (the first row whose
        ``seq`` is not its position; rows written before ``seq`` existed are skipped) and
        ``truncated`` (fewer rows than ``expected_rows``, when the caller passes it)."""
        rows = self.rows()
        prev, bad, gap = None, None, None
        for i, row in enumerate(rows):
            body = {k: v for k, v in row.items() if k != "row_sha256"}
            if bad is None and (
                body.get("prev_sha256") != prev
                or hashlib.sha256(_canon(body).encode()).hexdigest() != row.get("row_sha256")
            ):
                bad = i
            if gap is None and "seq" in row and row["seq"] != i:
                gap = i
            prev = row.get("row_sha256")
        truncated = expected_rows is not None and len(rows) < expected_rows
        return {
            "ok": bad is None and gap is None and not truncated,
            "rows": len(rows),
            "head_sha256": rows[-1].get("row_sha256") if rows else None,
            "first_bad_row": bad,
            "first_seq_gap": gap,
            "expected_rows": expected_rows,
            "truncated": truncated,
        }

    def verify(self) -> tuple[bool, int]:
        """Recompute the chain. Returns (ok, first bad row index or row count)."""
        r = self.report()
        if r["ok"]:
            return True, r["rows"]
        bad = [x for x in (r["first_bad_row"], r["first_seq_gap"]) if x is not None]
        return False, min(bad)
