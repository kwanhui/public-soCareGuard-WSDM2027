"""The public commit that a deployed build was made from.

The Space is built from a copy of the public repository without its `.git` directory, so the
deploy workflow writes the commit it deployed into `build_commit.txt` beside this module. The
setting `SOCAREGUARD_BUILD_COMMIT` overrides the file. A local run has neither, and the commit is
then reported as unknown (None).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

BUILD_COMMIT_FILE = Path(__file__).parent / "build_commit.txt"
BUILD_COMMIT_ENV = "SOCAREGUARD_BUILD_COMMIT"
_SHA = re.compile(r"[0-9a-f]{7,40}")


def build_commit() -> str | None:
    """The commit recorded for this build, or None when nothing records one.

    Only a hexadecimal commit id is returned, so a malformed file never reaches `/healthz`.
    """
    value = (os.environ.get(BUILD_COMMIT_ENV) or "").strip()
    if not value:
        try:
            value = BUILD_COMMIT_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    value = value.lower()
    return value if _SHA.fullmatch(value) else None
