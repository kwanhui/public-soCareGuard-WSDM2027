"""Local re-identification of the model's reply.

Surrogates and generalised phrases from the session's vault are replaced by the originals,
longest first so that a short form never clobbers a full name. Generalised phrases are
restored only on exact match, which is best-effort by nature: a model that paraphrases
"a secondary school" keeps the generalised form, which is the safe direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from socareguard.outbound.vault import Mapping, Vault


@dataclass
class Restored:
    text: str
    n_restored: int
    unrestored_surrogates: list[str]


def restore(reply: str, vault: Vault, session: str, restore_generalised: bool = True) -> Restored:
    maps = vault.mappings(session)
    if not restore_generalised:
        maps = [m for m in maps if m.kind in ("surrogate", "derived")]
    n = 0
    text = reply
    for m in sorted(maps, key=lambda m: -len(m.surrogate)):
        if not m.surrogate.strip():
            continue
        pattern = re.compile(r"(?<![\w-])" + re.escape(m.surrogate) + r"(?![\w-])")
        text, k = pattern.subn(lambda _, o=m.original: o, text)
        n += k
    left = [
        m.surrogate
        for m in maps
        if m.kind == "surrogate" and m.surrogate in text and m.surrogate != m.original
    ]
    return Restored(text=text, n_restored=n, unrestored_surrogates=left)


def originals(vault: Vault, session: str) -> list[Mapping]:
    return [m for m in vault.mappings(session) if m.kind == "surrogate"]
