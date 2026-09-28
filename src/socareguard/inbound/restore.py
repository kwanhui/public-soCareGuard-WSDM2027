"""Local re-identification of the model's reply.

Surrogates and generalised phrases from the session's vault are replaced by the originals,
longest first so that a short form never clobbers a full name, and only on whole tokens.
Generalised phrases are restored only on exact match, which is best-effort by nature: a model
that paraphrases "a secondary school" keeps the generalised form, which is the safe direction.

A surrogate is restored as a unit or not at all. A reply may reformat a surrogate ("Mr. Wee Hao
Ran" for "Mr Wee Hao Ran", an address without its postal code). The pieces the vault knows
("Ran" for the surname) would then restore on their own and fuse with the words around them into
a name or an address that exists nowhere. When a restored piece still sits next to a word of the
same surrogate that nothing restored, the whole run is put back as the surrogate and reported as
a partial restore, which the leak check turns into a flag.
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
    partial: list[str] = field(default_factory=list)  # surrogates restored in part, then reverted


def _choose(group: list[Mapping]) -> Mapping | None:
    """Which original a surrogate restores to. A surrogate (or derived form) shared by a full
    name and its short form restores to the longest original. A generalised phrase shared by two
    different originals restores to nothing: putting either back would fabricate the record."""
    kinds = {m.kind for m in group}
    if kinds <= {"surrogate", "derived"}:
        # the longest original; between a spelling variant and the form derived from the full
        # name, the derived form
        return max(group, key=lambda m: (len(m.original), m.kind == "derived"))
    originals = {m.original for m in group}
    if len(originals) == 1:
        return group[0]
    return None


_TITLE_DOT = re.compile(r"^(Mdm|Mr|Mrs|Ms|Dr|Madam)\b", re.IGNORECASE)


def _pattern(surrogate: str) -> re.Pattern[str]:
    """Whole-token pattern for a surrogate. Spacing may differ and a title may carry a full stop:
    "Mr. Wee Hao Ran" is the surrogate "Mr Wee Hao Ran"."""
    toks = surrogate.split()
    parts = [re.escape(t) for t in toks]
    if parts and _TITLE_DOT.match(toks[0]) and len(toks) > 1:
        parts[0] += r"\.?"
    return re.compile(r"(?<![\w-])" + r"[ \t\u00a0]+".join(parts) + r"(?![\w-])")


def _mark(i: int) -> str:
    # a private-use character, which no surrogate pattern can match
    return f"\x00{chr(0xF0000 + i)}\x00"


def _index(m: re.Match[str]) -> int:
    return ord(m.group(1)) - 0xF0000


_BAND_CONTEXT = re.compile(r"\b(?:between|from|aged|ages)\s*$", re.IGNORECASE)
# A verb a reply adds after a generalised phrase to finish its sentence ("once his health condition
# improves"). When the original clause carries its own verb ("leg heals"), putting the original
# back already supplies the grammar, and the added verb is dropped with the phrase.
_SUPPLIED_VERB = (
    r"(?i:heals?|healed|improves?|improved|recovers?|recovered|resolves?|resolved"
    r"|stabili[sz]es?|stabili[sz]ed|settles?|settled|gets better|is better|clears up|subsides?)"
)
_MARK = re.compile("\x00([\U000f0000-\U000fffff])\x00")


def restore(reply: str, vault: Vault, session: str, restore_generalised: bool = True) -> Restored:
    # a remembered withheld name is the outbound step's memory, not a mapping to restore
    maps = [m for m in vault.mappings(session) if m.kind != "withheld_name"]
    if not restore_generalised:
        maps = [m for m in maps if m.kind in ("surrogate", "derived")]
    ambiguous: list[str] = []
    groups: dict[str, list[Mapping]] = {}
    for m in maps:
        if m.surrogate.strip():
            groups.setdefault(m.surrogate, []).append(m)
    # Each restoration is first held as a marker, so a later, shorter surrogate never matches
    # inside a restored original, and a restored piece can be put back if its run is incomplete.
    held: list[tuple[Mapping, str]] = []  # (mapping restored, surrogate text as written)
    text = reply
    for surrogate in sorted(groups, key=lambda s: -len(s)):
        m = _choose(groups[surrogate])
        pattern = _pattern(surrogate)
        if (
            m is not None
            and m.kind == "generalised"
            and re.search(rf"(?<![\w-]){_SUPPLIED_VERB}\s*$", m.original)
            and not re.search(rf"(?<![\w-]){_SUPPLIED_VERB}(?![\w-])", surrogate)
        ):
            pattern = re.compile(pattern.pattern + rf"(?:[ \t]+{_SUPPLIED_VERB}(?![\w-]))?")
        if m is None:
            if pattern.search(text):
                ambiguous.append(surrogate)
            continue

        def hold(match: re.Match[str], m: Mapping = m) -> str:
            if (
                m.kind == "generalised"
                and m.category == "AGE"
                and _BAND_CONTEXT.search(match.string[: match.start()])
            ):
                # "aged between 3 to 5" names a band; its original age does not fit the phrase
                return match.group(0)
            held.append((m, match.group(0)))
            return _mark(len(held) - 1)

        text = pattern.sub(hold, text)
    text, reverted = _revert_incomplete_runs(text, held, maps)
    n = len(held) - len(reverted)
    text = _MARK.sub(
        lambda mk: held[_index(mk)][1] if _index(mk) in reverted else held[_index(mk)][0].original,
        text,
    )
    partial = sorted({held[i][0].surrogate for i in reverted})
    left = [
        m.surrogate
        for m in maps
        if m.kind == "surrogate" and m.surrogate in text and m.surrogate != m.original
    ]
    left += _fragments_left(text, maps)
    return Restored(
        text=text,
        n_restored=n,
        unrestored_surrogates=sorted(set(left)),
        ambiguous_generalised=ambiguous,
        partial=partial,
    )


_GENERIC = {
    "singapore", "blk", "block", "mdm", "mr", "mrs", "ms", "dr", "madam", "bin", "binti", "binte",
    "bte", "bt", "s/o", "d/o", "a/l", "a/p",
}  # fmt: skip
_JOIN = r"[ \t\u00a0,.]{1,3}"


_STREET_ABBR = {
    "avenue": "Ave", "street": "St", "road": "Rd", "drive": "Dr", "crescent": "Cres",
    "close": "Cl", "place": "Pl", "lorong": "Lor", "jalan": "Jln", "central": "Ctrl",
}  # fmt: skip


def _entity_tokens(maps: list[Mapping]) -> dict[str, tuple[set[str], set[str]]]:
    """Per entity, (the words of its surrogate forms, the subset that does not occur in its
    originals). The first set holds a run of the surrogate together; a word of the second set
    left in a reply belongs to the surrogate and not to the record. An address also counts its
    street type in short form and its numbers."""
    out: dict[str, tuple[set[str], set[str]]] = {}
    originals: dict[str, set[str]] = {}
    for m in maps:
        if m.kind in ("surrogate", "derived"):
            originals.setdefault(m.entity_id, set()).update(
                t.lower().rstrip(".,") for t in re.split(r"[\s,()]+", m.original) if t
            )
    for m in maps:
        if m.kind not in ("surrogate", "derived"):
            continue
        run, own = out.setdefault(m.entity_id, (set(), set()))
        for t in re.split(r"[\s,()]+", m.surrogate):
            t = t.rstrip(".,")
            tl = t.lower()
            forms = [t] + (
                [_STREET_ABBR[tl]] if m.category == "ADDRESS" and tl in _STREET_ABBR else []
            )
            if tl in _GENERIC or (len(tl) < 2 and not (m.category == "ADDRESS" and tl.isdigit())):
                continue
            run.update(forms)
            if tl not in originals.get(m.entity_id, set()):
                own.update(f for f in forms if f.lower() not in originals.get(m.entity_id, set()))
    return out


def _revert_incomplete_runs(
    text: str, held: list[tuple[Mapping, str]], maps: list[Mapping]
) -> tuple[str, set[int]]:
    """Markers of one entity that sit next to a word of that entity's surrogate which nothing
    restored are reverted, together with every marker of the same entity in that run."""
    tokens = _entity_tokens(maps)
    reverted: set[int] = set()
    for i, (m, _) in enumerate(held):
        if m.kind not in ("surrogate", "derived") or i in reverted:
            continue
        run_words, own_words = tokens.get(m.entity_id, (set(), set()))
        if not own_words:
            continue

        def alt(ws: set[str]) -> str:
            return "|".join(re.escape(w) for w in sorted(ws, key=len, reverse=True))

        unit = rf"(?:{_MARK.pattern}|(?<![\w-])(?:{alt(run_words)})(?![\w-]))"
        mark = _mark(i)
        for run in re.finditer(rf"{unit}(?:{_JOIN}{unit})*", text):
            if mark not in run.group(0):
                continue
            ids = [_index(x) for x in _MARK.finditer(run.group(0))]
            same = [j for j in ids if held[j][0].entity_id == m.entity_id]
            bare = _MARK.sub(" ", run.group(0))
            if re.search(rf"(?<![\w-])(?:{alt(own_words)})(?![\w-])", bare):
                reverted.update(same)
    return text, reverted


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
