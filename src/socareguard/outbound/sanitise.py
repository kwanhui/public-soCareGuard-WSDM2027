"""Outbound sanitisation: detect -> generalise -> substitute -> vault, with a structured event log.

Returns the text that may cross the boundary plus the events the scenario scripts assert on.
Nothing in the returned events contains an original identifier; the ledger is written by
the caller from the same events.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from socareguard.detect.pipeline import Detection, detect
from socareguard.detect.sg import Hit
from socareguard.outbound import generalise as gen
from socareguard.outbound.surrogates import SurrogateFactory
from socareguard.outbound.vault import Mapping, Vault
from socareguard.scenarios.events import Detect, DetectedSpan, Generalise, Substitute

QUASI_GENERALISERS = {
    "AGE": lambda t, pack: gen.generalise_age(t, pack),
    "ESTATE": lambda t, pack: gen.generalise_estate(t),
    "SCHOOL": lambda t, pack: gen.generalise_school(t),
    "FACILITY": lambda t, pack: gen.generalise_facility(t),
    "EMPLOYER": lambda t, pack: gen.generalise_employer(t),
}
DIRECT_SURROGATES = {
    "NAME": "name",
    "NRIC": "nric",
    "PHONE": "phone",
    "ADDRESS": "address",
    "DOB": "dob",
    "CASE_REF": "case_ref",
    "SCHOOL": "school",
    "FACILITY": "facility",
    "EMAIL": "email",
}
ADDRESS_PARTS = {"sg.postal": "postal", "sg.unit": "unit", "sg.block": "block"}


@dataclass
class Sanitised:
    session: str
    text: str
    detection: Detection
    replacements: list[tuple[Hit, str, str]] = field(
        default_factory=list
    )  # (hit, outbound text, kind)
    events: list = field(default_factory=list)
    payload_sha256: str = ""


class Sanitiser:
    def __init__(self, vault: Vault, pack, use_presidio: bool = True, use_gliner: bool = True):
        self.vault = vault
        self.pack = pack
        self.use_presidio = use_presidio
        self.use_gliner = use_gliner

    def _replacement(
        self, h: Hit, factory: SurrogateFactory, seq: dict[str, int]
    ) -> tuple[str, str, str | None]:
        """Return (outbound text, kind, rule_id)."""
        cat = h.category
        if cat.startswith("ATTR:"):
            key = cat.split(":", 1)[1]
            rule = self.pack.attribute_rule(key)
            if rule is None:
                return h.text, "kept", None
            return (
                gen.generalise_attribute(key, h.text, rule.generalise_to, self.pack.id),
                "generalised",
                f"{self.pack.id}.attr.{key}",
            )
        qrule = self.pack.quasi_rule(cat)
        if qrule is not None and cat in QUASI_GENERALISERS:
            if (
                cat == "FACILITY"
                and qrule.kinds
                and not any(k in gen.generalise_facility(h.text) for k in qrule.kinds)
            ):
                return factory.facility(h.text), "surrogate", None
            return (
                QUASI_GENERALISERS[cat](h.text, self.pack.id),
                "generalised",
                f"{self.pack.id}.quasi.{cat.lower()}",
            )
        if cat == "AGE":
            return gen.generalise_age(h.text, self.pack.id), "generalised", "default.quasi.age"
        method = ADDRESS_PARTS.get(h.detector) if cat == "ADDRESS" else None
        method = method or DIRECT_SURROGATES.get(cat, "generic")
        return getattr(factory, method)(h.text), "surrogate", None

    def sanitise(
        self, text: str, session: str, seed: int | None = None, seq_start: int = 1
    ) -> Sanitised:
        det = detect(
            text,
            use_presidio=self.use_presidio,
            use_gliner=self.use_gliner,
            attribute_keys={r.key for r in self.pack.outbound.attributes},
        )
        # An attribute clause may absorb name spans (the generalised phrase names the role, not the
        # person) but never another entity: a clause holding an NRIC, case reference or school is
        # left to entity substitution and its attribute wording stays as written.
        names = {"NAME", "THIRD_PARTY_NAME"}
        spans = list(det.entities)
        for a_hit in det.attributes:
            overlapping = [e for e in det.entities if e.start < a_hit.end and a_hit.start < e.end]
            if all(e.category in names for e in overlapping):
                spans = [e for e in spans if e not in overlapping] + [a_hit]
        spans = _drop_nested(spans)
        forbidden = {h.text for h in spans}
        factory = SurrogateFactory(
            seed if seed is not None else int(hashlib.sha256(session.encode()).hexdigest()[:8], 16),
            forbidden,
        )
        # Consistent surrogates: same original text -> same outbound text. Names are assigned
        # longest-first so that a short form seen before its full form maps to the same person.
        memo: dict[tuple[str, str], tuple[str, str, str | None]] = {}
        for h in sorted((h for h in spans if h.category == "NAME"), key=lambda h: -len(h.text)):
            key = (h.category, h.text)
            if key not in memo:
                memo[key] = self._replacement(h, factory, {})
        out, pos, replacements, rules = [], 0, [], []
        n_entities = len(memo)
        for h in sorted(spans, key=lambda h: h.start):
            key = (h.category, h.text)
            if key not in memo:
                memo[key] = self._replacement(h, factory, {})
                n_entities += 1
            new, kind, rule_id = memo[key]
            if (
                kind == "generalised"
                and new
                and _at_sentence_start("".join(out) + text[pos : h.start])
            ):
                new = new[0].upper() + new[1:]
            out.append(text[pos : h.start])
            out.append(new)
            pos = h.end
            replacements.append((h, new, kind))
            if kind == "generalised":
                rules.append({"rule": rule_id, "category": h.category, "to": new})
            if kind in ("surrogate", "generalised") and new != h.text:
                for d_orig, d_new in _derived_forms(h.category, h.text, new):
                    self.vault.put(
                        Mapping(
                            session,
                            d_orig,
                            d_new,
                            h.category,
                            "derived",
                            f"{h.category}:{hash(h.text) & 0xFFFF:04x}",
                        )
                    )
                self.vault.put(
                    Mapping(
                        session,
                        h.text,
                        new,
                        h.category,
                        kind,
                        f"{h.category}:{hash(h.text) & 0xFFFF:04x}",
                    )
                )
        out.append(text[pos:])
        outbound = "".join(out)
        seq = seq_start
        events = [
            Detect(
                seq=seq,
                spans=[
                    DetectedSpan(
                        start=h.start,
                        end=h.end,
                        text="",
                        type=(
                            "ATTRIBUTE"
                            if h.category.startswith("ATTR:")
                            else "QUASI"
                            if h.category in QUASI_GENERALISERS
                            else "DIRECT"
                        ),
                        category=("ATTRIBUTE" if h.category.startswith("ATTR:") else h.category),
                        detector=h.detector,
                        score=h.score,
                    )
                    for h in spans
                ],
            ),
            Generalise(seq=seq + 1, rules=rules),
            Substitute(
                seq=seq + 2, n_spans=len(replacements), n_entities=n_entities, vault_session=session
            ),
        ]
        return Sanitised(
            session=session,
            text=outbound,
            detection=det,
            replacements=replacements,
            events=events,
            payload_sha256=hashlib.sha256(outbound.encode()).hexdigest(),
        )


_COMMON_WORDS = {
    "low",
    "long",
    "young",
    "white",
    "brown",
    "king",
    "wee",
    "ho",
    "ang",
    "mark",
    "may",
    "sim",
    "goh",
}
_DOB_FORMATS = (
    "%d/%m/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%-d %b %Y",
    "%-d %B %Y",
)


def _derived_forms(category: str, original: str, surrogate: str) -> list[tuple[str, str]]:
    """Extra (original, surrogate) pairs so that a reply that writes 'Ms Neo', '11/03/1970' or just the
    postal code still restores. Restoration is by surrogate, so each pair is looked up by its surrogate."""
    out: list[tuple[str, str]] = []
    if category == "NAME":
        from socareguard.outbound.surrogates import title_token

        o, n = title_token(original), title_token(surrogate)
        if (
            o
            and n
            and o != n
            and len(n) >= 3
            and n.lower() not in _COMMON_WORDS
            and o.lower() != original.lower()
        ):
            out.append((o, n))
    elif category == "DOB":
        from datetime import datetime

        for fmt in _DOB_FORMATS:
            try:
                d_o = datetime.strptime(original, fmt.replace("%-d", "%d"))  # noqa: DTZ007
                d_n = datetime.strptime(surrogate, fmt.replace("%-d", "%d"))  # noqa: DTZ007
            except ValueError:
                continue
            for f2 in _DOB_FORMATS:
                try:
                    a, b = d_o.strftime(f2), d_n.strftime(f2)
                except ValueError:
                    continue
                if b != surrogate:
                    out.append((a, b))
            break
    elif category == "ADDRESS":
        o_parts = re.findall(
            r"#\d{1,2}-\d{1,4}|\b\d{6}\b|\b(?:Blk|Block)\s+\d{1,4}[A-Z]?\b", original
        )
        n_parts = re.findall(
            r"#\d{1,2}-\d{1,4}|\b\d{6}\b|\b(?:Blk|Block)\s+\d{1,4}[A-Z]?\b", surrogate
        )
        for a, b in zip(o_parts, n_parts, strict=False):
            if a != b:
                out.append((a, b))
    return out


def _at_sentence_start(prefix: str) -> bool:
    stripped = prefix.rstrip(" ")
    return stripped == "" or stripped.endswith((".", "!", "?", "\n", ":"))


def _drop_nested(spans: list[Hit]) -> list[Hit]:
    kept: list[Hit] = []
    for h in sorted(spans, key=lambda h: (h.start, -(h.end - h.start))):
        if any(k.start <= h.start and h.end <= k.end for k in kept):
            continue
        if any(h.start < k.end and k.start < h.end for k in kept):
            # partial overlap: keep the earlier, longer one
            continue
        kept.append(h)
    return kept
