"""Local re-identification of the model's reply.

Surrogates and generalised phrases from the session's vault are replaced by the originals,
longest first so that a short form never clobbers a full name. Generalised phrases are
restored only on exact match, which is best-effort by nature: a model that paraphrases
"a secondary school" keeps the generalised form, which is the safe direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from socareguard.outbound.vault import Mapping, Vault


@dataclass
class Restored:
    text: str
    n_restored: int
    unrestored_surrogates: list[str]
    ambiguous_generalised: list[str] = field(default_factory=list)


def _choose(group: list[Mapping]) -> Mapping | None:
    """Which original a surrogate restores to. A surrogate (or derived form) shared by a full
    name and its short form restores to the longest original. A generalised phrase shared by two
    different originals restores to nothing: putting either back would fabricate the record."""
    kinds = {m.kind for m in group}
    if kinds <= {"surrogate", "derived"}:
        return max(group, key=lambda m: len(m.original))
    originals = {m.original for m in group}
    if len(originals) == 1:
        return group[0]
    return None


def restore(reply: str, vault: Vault, session: str, restore_generalised: bool = True) -> Restored:
    maps = vault.mappings(session)
    if not restore_generalised:
        maps = [m for m in maps if m.kind in ("surrogate", "derived")]
    n = 0
    text = reply
    ambiguous: list[str] = []
    groups: dict[str, list[Mapping]] = {}
    for m in maps:
        if m.surrogate.strip():
            groups.setdefault(m.surrogate, []).append(m)
    for surrogate in sorted(groups, key=lambda s: -len(s)):
        m = _choose(groups[surrogate])
        pattern = re.compile(r"(?<![\w-])" + re.escape(surrogate) + r"(?![\w-])")
        if m is None:
            if pattern.search(text):
                ambiguous.append(surrogate)
            continue
        text, k = pattern.subn(lambda _, o=m.original: o, text)
        n += k
    left = [
        m.surrogate
        for m in maps
        if m.kind == "surrogate" and m.surrogate in text and m.surrogate != m.original
    ]
    left += _fragments_left(text, maps)
    return Restored(
        text=text, n_restored=n, unrestored_surrogates=left, ambiguous_generalised=ambiguous
    )


_LINK = {
    "bin", "binti", "binte", "bte", "bt", "s/o", "d/o", "a/l", "a/p", "mdm", "mr", "mrs", "ms",
    "nur", "siti", "muhammad", "mohamed", "mohammad", "abdul", "haji", "hajjah",
}  # fmt: skip


def _fragments_left(text: str, maps: list[Mapping]) -> list[str]:
    """A distinctive token of a surrogate name, or the digits of a surrogate phone number, that
    survived restoration. Either means the practitioner would read a fabricated detail as real."""
    out: list[str] = []
    originals_lower = " ".join(m.original for m in maps).lower()
    digits_text = re.sub(r"\D", "", text)
    for m in maps:
        if m.kind != "surrogate":
            continue
        if m.category in {"NAME", "FACILITY", "SCHOOL", "EMPLOYER"}:
            for tok in re.split(r"[\s,()]+", m.surrogate):
                if (
                    len(tok) >= 3
                    and tok[0].isupper()
                    and tok.lower() not in _LINK
                    and tok.lower() not in originals_lower
                    and re.search(r"(?<![\w-])" + re.escape(tok) + r"(?![\w-])", text)
                ):
                    out.append(tok)
        elif m.category == "PHONE":
            d = re.sub(r"\D", "", m.surrogate)[-8:]
            if len(d) == 8 and d in digits_text and d not in re.sub(r"\D", "", m.original):
                out.append(m.surrogate)
        elif m.category == "ADDRESS":
            # a street name, postal code, block or unit from the surrogate address that survived
            for part in re.findall(
                r"#\d{1,2}-\d{1,4}|\b\d{6}\b|\b(?:Blk|Block)\s+\d{1,4}[A-Z]?\b|\b[A-Z][a-z]{3,}\b",
                m.surrogate,
            ):
                if (
                    part.lower() not in _ADDRESS_WORDS
                    and part.lower() not in originals_lower
                    and re.search(r"(?<![\w-])" + re.escape(part) + r"(?![\w-])", text)
                ):
                    out.append(part)
    return sorted(set(out))


_ADDRESS_WORDS = {
    "road", "street", "avenue", "drive", "lane", "crescent", "close", "walk", "singapore",
    "block", "north", "south", "east", "west", "central", "ring", "view", "park", "garden",
    "gardens", "heights", "terrace", "place", "rise", "link", "loop", "way", "hill", "grove",
}  # fmt: skip


def originals(vault: Vault, session: str) -> list[Mapping]:
    return [m for m in vault.mappings(session) if m.kind == "surrogate"]
