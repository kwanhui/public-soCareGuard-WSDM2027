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
    "PASSPORT": "passport",
    "BANK_ACCOUNT": "generic",
    "HANDLE": "handle",
    "MRN": "generic",
    "WARD_BED": "generic",
    "VEHICLE": "generic",
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
    rule_ids: dict[tuple[int, int], str] = field(default_factory=dict)  # span -> pack rule id


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
        if cat == "ATTR:never_leak":
            entry = next((e for e in self.pack.outbound.never_leak if e.label == h.detector), None)
            placeholder = (entry.withhold_as if entry and entry.withhold_as else None) or (
                f"[withheld: {h.detector}]"
            )
            return placeholder, "generalised", f"{self.pack.id}.never_leak"
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
                # Not a kind this pack bands by name, but a named place still leaves as its kind:
                # inventing a plausible centre name would be a fabrication the model may expand.
                return (
                    gen.generalise_facility(h.text),
                    "generalised",
                    f"{self.pack.id}.quasi.facility",
                )
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
        self,
        text: str,
        session: str,
        seed: int | None = None,
        seq_start: int = 1,
        attributes: bool = True,
        attribute_floor: int = 0,
    ) -> Sanitised:
        det = detect(
            text,
            use_presidio=self.use_presidio,
            use_gliner=self.use_gliner,
            attributes=attributes,
            attribute_keys={r.key for r in self.pack.outbound.attributes},
        )
        # An attribute clause may absorb name spans (the generalised phrase names the role, not the
        # person) but never another entity: a clause holding an NRIC, case reference or school is
        # left to entity substitution and its attribute wording stays as written.
        names = {"NAME", "THIRD_PARTY_NAME"}
        spans = list(det.entities)
        # never_leak entries with a pattern are withheld outright and take precedence over any
        # attribute clause they overlap.
        nl_hits: list[Hit] = []
        for entry in self.pack.outbound.never_leak:
            if not entry.pattern:
                continue
            for m in re.finditer(entry.pattern, text, re.IGNORECASE):
                if m.start() >= attribute_floor:
                    nl_hits.append(
                        Hit(m.start(), m.end(), m.group(0), "ATTR:never_leak", entry.label, 0.99)
                    )
        ruled = {r.key for r in self.pack.outbound.attributes}

        def generalised_clause(a: Hit) -> bool:
            return a.category.split(":", 1)[1] in ruled

        # A never_leak span inside an attribute clause that this pack generalises is removed by
        # that clause's rule; inside any other clause it keeps its own precedence.
        contained = [
            n
            for n in nl_hits
            if any(
                a.start <= n.start and n.end <= a.end and generalised_clause(a)
                for a in det.attributes
            )
        ]
        nl_hits = [n for n in nl_hits if n not in contained]
        attrs = [
            a
            for a in det.attributes
            if not any(n.start < a.end and a.start < n.end for n in nl_hits)
        ] + nl_hits
        redacting = {
            r.key for r in self.pack.outbound.attributes if r.generalise_to == "redact"
        } | {"never_leak"}
        for a_hit in attrs:
            if a_hit.start < attribute_floor:
                continue
            overlapping = [e for e in det.entities if e.start < a_hit.end and a_hit.start < e.end]
            key = a_hit.category.split(":", 1)[1] if ":" in a_hit.category else ""
            # A redacted clause (safety plan, never_leak) takes its unit numbers and phones with
            # it; any other clause holding a non-name entity is left to entity substitution.
            if key in redacting or all(e.category in names for e in overlapping):
                spans = [e for e in spans if e not in overlapping] + [a_hit]
        spans = _drop_nested(spans)
        forbidden = {h.text for h in spans}
        factory = SurrogateFactory(
            seed if seed is not None else int(hashlib.sha256(session.encode()).hexdigest()[:8], 16),
            forbidden,
        )
        # Consistent surrogates: same original text -> same outbound text, within this call and
        # across calls in the same session (a second turn, a regeneration). Names are assigned
        # longest-first so that a short form seen before its full form maps to the same person.
        memo: dict[tuple[str, str], tuple[str, str, str | None]] = {}
        for prior in self.vault.mappings(session):
            if prior.kind == "surrogate":
                memo[(prior.category, prior.original)] = (prior.surrogate, "surrogate", None)
                factory.used.add(prior.surrogate.lower())
                if prior.category == "NAME":
                    from socareguard.corpus import names as nm

                    toks = [t for t in re.split(r"[\s,()/]+", prior.surrogate) if t]
                    factory.persons.setdefault(
                        prior.original.lower(),
                        nm.PersonName("", "", prior.surrogate, toks[0], f"Mdm {toks[0]}"),
                    )
        for h in sorted((h for h in spans if h.category == "NAME"), key=lambda h: -len(h.text)):
            key = (h.category, h.text)
            if key not in memo:
                memo[key] = self._replacement(h, factory, {})
        out, pos, replacements, rules = [], 0, [], []
        rule_ids: dict[tuple[int, int], str] = {}
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
            gap = text[pos : h.start]
            if kind == "generalised" and new and new.split(" ", 1)[0].lower() in {"a", "an", "the"}:
                # "at a cafe" -> "at an employer": drop the article that precedes the generalised phrase
                m_art = re.search(r"\b(a|an|the)\s*$", gap, re.IGNORECASE)
                if m_art:
                    gap = gap[: m_art.start()]
                elif not gap.strip() and out:
                    m_out = re.search(r"\b(a|an|the)\s*$", out[-1], re.IGNORECASE)
                    if m_out:
                        out[-1] = out[-1][: m_out.start()]
            if kind == "generalised" and replacements and replacements[-1][2] == "generalised":
                prev_hit, prev_new, _ = replacements[-1]
                between = text[prev_hit.end : h.start]
                if (
                    prev_new.lower().rstrip(".") == new.lower().rstrip(".")
                    and len(between.strip(" ;,.")) == 0
                ):
                    new = ""  # the same generalised statement twice in a row: keep one
                    gap = ""  # and the separator between the two
            out.append(gap)
            out.append(new)
            pos = h.end
            replacements.append((h, new, kind))
            if rule_id:
                rule_ids[(h.start, h.end)] = rule_id
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
                seq=seq + 2,
                n_spans=sum(1 for _, _, k in replacements if k == "surrogate"),
                n_entities=n_entities,
                n_generalised=sum(1 for _, _, k in replacements if k == "generalised"),
                n_kept=sum(1 for _, _, k in replacements if k == "kept"),
                n_withheld=sum(1 for h, _, _ in replacements if h.category == "ATTR:never_leak"),
                vault_session=session,
            ),
        ]
        return Sanitised(
            session=session,
            text=outbound,
            detection=det,
            replacements=replacements,
            events=events,
            payload_sha256=hashlib.sha256(outbound.encode()).hexdigest(),
            rule_ids=rule_ids,
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
        from socareguard.outbound.surrogates import _LINK_TOKENS, _TITLES, title_token

        o, n = title_token(original), title_token(surrogate)
        if (
            o
            and n
            and o != n
            and len(n) >= 2
            and n.lower() not in _COMMON_WORDS
            and o.lower() != original.lower()
        ):
            out.append((o, n))
        # Every other distinctive token, position-wise ("Farah" for "Aisyah"), so a reply that
        # uses the given name alone still restores.
        skip = set(_LINK_TOKENS) | set(_TITLES)

        def core(name: str) -> list[str]:
            return [
                t
                for t in re.split(r"[\s,()]+", name.strip())
                if t and t.lower() not in skip and len(t) >= 3
            ]

        oc, nc = core(original), core(surrogate)
        pairs = list(zip(oc, nc, strict=False)) if len(oc) == len(nc) else []
        if not pairs and oc and nc:
            pairs = [(oc[0], nc[0])] + ([(oc[-1], nc[-1])] if len(oc) > 1 and len(nc) > 1 else [])
        for a, b in pairs:
            if a != b and b.lower() not in _COMMON_WORDS and (a, b) not in out and b != surrogate:
                out.append((a, b))
        # "Nur Izzati" for "Nabilah": the surrogate's honorific prefix plus given name maps to the
        # original given name, so the prefix does not survive as a stray token.
        n_toks = [t for t in re.split(r"[\s,()]+", surrogate.strip()) if t]
        o_toks = [t for t in re.split(r"[\s,()]+", original.strip()) if t and t.lower() not in skip]
        prefixes = {"nur", "siti", "muhammad", "mohamed", "mohammad", "abdul"}
        if len(n_toks) >= 2 and n_toks[0].lower() in prefixes and o_toks:
            o_first = (
                o_toks[0]
                if o_toks[0].lower() not in prefixes
                else (o_toks[1] if len(o_toks) > 1 else o_toks[0])
            )
            pair = (
                o_first if o_toks[0].lower() not in prefixes else f"{o_toks[0]} {o_first}",
                f"{n_toks[0]} {n_toks[1]}",
            )
            if pair[1] != surrogate and pair not in out:
                out.insert(0, pair)
    elif category == "PHONE":
        od, nd = re.sub(r"\D", "", original), re.sub(r"\D", "", surrogate)
        if len(od) >= 8 and len(nd) >= 8:
            od, nd = od[-8:], nd[-8:]
            for fmt in ("{0} {1}", "{0}-{1}", "+65 {0} {1}", "+65{0}{1}", "{0}{1}"):
                a, b = fmt.format(od[:4], od[4:]), fmt.format(nd[:4], nd[4:])
                if b != surrogate and (a, b) not in out:
                    out.append((a, b))
    elif category == "CASE_REF":
        for src, dst in (("/", "-"), ("-", "/")):
            a, b = original.replace(src, dst), surrogate.replace(src, dst)
            if b != surrogate and a != original:
                out.append((a, b))
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
        # The estate name inside a surrogate address ("Tampines" in "Blk 474C Tampines Ave 4")
        # maps back to the original estate, so "from Tampines" restores.
        from socareguard.detect.gazetteers import _ESTATE_RE

        eo, en = _ESTATE_RE.search(original), _ESTATE_RE.search(surrogate)
        if eo and en and eo.group(0) != en.group(0):
            out.append((eo.group(0), en.group(0)))
        # and the whole street phrase ("Whampoa Drive" -> "Marsiling Rise"), so a reply that
        # keeps the surrogate's street type does not restore to a hybrid address
        so, sn = _STREET_RE.search(original), _STREET_RE.search(surrogate)
        if so and sn and so.group(0) != sn.group(0):
            out.insert(0, (so.group(0), sn.group(0)))
    return out


_STREET_RE = re.compile(
    r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)? (?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Crescent|Cres|Close|Walk|Way|Link|Loop|Rise|View|Terrace|Place|Grove|Hill|Park|Central|North|South|East|West)"
    r"(?: \d{1,3})?\b|\b(?:Lorong|Jalan) [A-Z0-9][A-Za-z0-9]*\b"
)


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
