"""Outbound sanitisation: detect -> generalise -> substitute -> vault, with a structured event log.

Returns the text that may cross the boundary plus the events the scenario scripts assert on.
Nothing in the returned events contains an original identifier. The ledger is written by
the caller from the same events.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from socareguard.detect.pipeline import Detection, detect
from socareguard.detect.sg import Hit
from socareguard.outbound import generalise as gen
from socareguard.outbound.surrogates import (
    SurrogateFactory,
    gender_from_context,
    gender_from_pronouns,
)
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
    "WORK_PERMIT": "work_permit",
    "BANK_ACCOUNT": "generic",
    "HANDLE": "handle",
    "URL": "url",
    "MRN": "generic",
    "WARD_BED": "generic",
    "VEHICLE": "generic",
    "STAFF_ID": "generic",
}
_TOWNS = frozenset(gen.REGION) | {"Jurong", "Bedok North", "Marsiling", "Khatib"}
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
    def __init__(
        self,
        vault: Vault,
        pack,
        use_presidio: bool = True,
        use_gliner: bool = True,
        audience: str | None = None,
    ):
        self._pronoun_gender: dict[str, str] = {}
        # "internal" or "external"; None behaves as external. A named employer leaves as a
        # reversible surrogate for an internal audience, so the practitioner's draft gets the name
        # back, and as "an employer" (never restored) for an external one.
        self.audience = audience
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
            out = gen.generalise_attribute(
                key,
                h.text,
                rule.generalise_to,
                self.pack.id,
                before=self._text[: h.start],
                note=self._text,
            )
            if rule.generalise_to == "category" and any(
                h.start <= n.start and n.end <= h.end and n.text not in out for n in self._name_hits
            ):
                # The clause statement would drop a person the clause names: the person is
                # substituted, never generalised away, so only the phrases naming the condition
                # or the offence are replaced.
                out = gen.soften_in_place(key, h.text)
            if out == h.text:
                # the rule found nothing in this clause to generalise: it leaves as written, with
                # its names substituted
                return h.text, "kept", None
            return out, "generalised", f"{self.pack.id}.attr.{key}"
        place = gen.shared_place(h.text) if cat in ("FACILITY", "EMPLOYER") else None
        if place and (h.detector == "gazetteer.place" or gen.shared_place(h.text)):
            # a mall or a shared place is a place: it leaves as its kind, never as an invented
            # organisation name
            return place, "generalised", f"{self.pack.id}.quasi.place"
        if cat in ("FACILITY", "EMPLOYER") and gen.is_public_body(h.text, _TOWNS):
            # a public hospital or a town's polyclinic is a public body and stays as written, also
            # when a detector reads it as a clinician's employer ("psychiatrist at the Institute
            # of Mental Health")
            return h.text, "kept", None
        qrule = self.pack.quasi_rule(cat)
        if cat == "EMPLOYER" and _generic_org(h.text, self._text[: h.start]):
            # "his employer's HR department", "his warehouse job", "a note for an employer": a
            # role or a possessive generic phrase names no organisation, and neither an invented
            # company name nor "an employer" reads in its place ("his Foxglove Services")
            return h.text, "kept", None
        if cat == "EMPLOYER" and qrule is None and not _proper_noun(h.text):
            # "a prospective employer", "a logistics company": a role, not an organisation. Under a
            # pack without an employer rule the organisation surrogate would turn it into an
            # invented company name that reads as a real one ("a Silverbirch Services"). A pack
            # with an employer rule generalises it to "an employer" as before.
            return h.text, "kept", None
        if cat == "EMPLOYER" and qrule is not None and self.audience == "internal":
            return factory.generic(h.text), "surrogate", f"{self.pack.id}.quasi.employer.internal"
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
        if cat == "URL" and self.pack.outbound.links == "withhold":
            return "[link withheld]", "generalised", f"{self.pack.id}.links"
        method = ADDRESS_PARTS.get(h.detector) if cat == "ADDRESS" else None
        method = method or DIRECT_SURROGATES.get(cat, "generic")
        if method == "name":
            hint = gender_from_context(
                self._text[max(0, h.start - 40) : h.start]
            ) or self._pronoun_gender.get(h.text)
            return factory.name(h.text, gender_hint=hint), "surrogate", None
        return getattr(factory, method)(h.text), "surrogate", None

    def _fit_span(self, text: str, a: Hit) -> Hit:
        """A short diagnosis span must fit the sentence it lands in. When the words before it do
        not take a noun phrase, a predicate or a copula, the span grows left over modifiers
        ("resulting left hemiparesis") to a word that does, or else to its whole clause."""
        key = a.category.split(":", 1)[1] if a.category.startswith("ATTR:") else ""
        rule = self.pack.attribute_rule(key) if key in ("disability", "diagnosis") else None
        if rule is None or rule.generalise_to != "category" or len(a.text.split()) > 12:
            return a
        if gen.grammar_slot(text[: a.start]) != "none":
            return a
        start = a.start
        for _ in range(3):
            m = re.search(r"([\w'-]+)\s+$", text[:start])
            if not m or m.group(1).lower() not in (
                gen.KEPT_NP_MODIFIERS | gen.DROPPED_NP_MODIFIERS
            ):
                break
            start = m.start(1)
            if gen.grammar_slot(text[:start]) in ("np", "bare"):
                return Hit(start, a.end, text[start : a.end], a.category, a.detector, a.score)
        from socareguard.detect.attributes import _clause

        s0, e0 = _clause(text, a.start)
        e0 = max(e0, a.end)
        return Hit(s0, e0, text[s0:e0], a.category, a.detector, a.score)

    def _changes(self, text: str, a: Hit) -> bool:
        key = a.category.split(":", 1)[1] if a.category.startswith("ATTR:") else ""
        rule = self.pack.attribute_rule(key) if key else None
        if rule is None:
            return False
        out = gen.generalise_attribute(
            key, a.text, rule.generalise_to, self.pack.id, before=text[: a.start], note=text
        )
        return out != a.text

    def _keep_subject(self, text: str, a: Hit, entities: list[Hit]) -> Hit:
        """A clause that opens with the person it is about ("Client Aisha Lim, 14, caught ...")
        starts after that person's name and age, when the clause's statement would drop the
        name: the name is substituted and the rest of the clause is generalised."""
        key = a.category.split(":", 1)[1] if a.category.startswith("ATTR:") else ""
        rule = self.pack.attribute_rule(key) if key else None
        if rule is None or rule.generalise_to != "category":
            return a
        for n in sorted(entities, key=lambda e: e.start):
            if n.category != "NAME" or not (a.start <= n.start and n.end <= a.end):
                continue
            if not _SUBJECT_LEAD.fullmatch(text[a.start : n.start]):
                break
            out = gen.generalise_attribute(
                key, a.text, rule.generalise_to, self.pack.id, before=text[: a.start], note=text
            )
            if n.text in out:
                return a
            m = _APPOSITIVE.match(text, n.end)
            start = m.end() if m else n.end
            rest = text[start : a.end]
            if len(rest.split()) < 2:
                return a
            trimmed = gen.generalise_attribute(
                key, rest, rule.generalise_to, self.pack.id, before=text[:start], note=text
            )
            if not re.match(r"(?:is|has|was|had|are|were|have)\b", trimmed):
                # the clause's statement does not read as a predicate after the name ("Oliver no
                # prior offence record is noted"): the clause stays whole and keeps the name
                return a
            return Hit(start, a.end, rest, a.category, a.detector, a.score)
        return a

    def _remember(self, session: str, category: str, original: str, new: str, kind: str) -> None:
        """Store the mapping, and its derived short forms, so that a reply restores."""
        ref = f"{category}:{hash(original) & 0xFFFF:04x}"
        for d_orig, d_new in _derived_forms(category, original, new):
            self.vault.put(Mapping(session, d_orig, d_new, category, "derived", ref))
        self.vault.put(Mapping(session, original, new, category, kind, ref))

    def _substitute_absorbed(
        self,
        clause: str,
        absorbed: list[Hit],
        memo: dict[tuple[str, str], tuple[str, str, str | None]],
        factory: SurrogateFactory,
    ) -> tuple[str, list[tuple[Hit, str, str]]]:
        """Replace the names (and the estates and ages) a kept clause absorbed with their
        surrogates or generalised forms, in one pass so that a replacement is never itself
        rewritten. Returns the clause and the (entity, replacement, kind) triples used."""
        by_text: dict[str, tuple[Hit, str, str]] = {}
        for e in sorted(absorbed, key=lambda e: -len(e.text)):
            key = (e.category, e.text)
            if key not in memo:
                memo[key] = self._replacement(e, factory, {})
            by_text.setdefault(e.text, (e, memo[key][0], memo[key][1]))
        if not by_text:
            return clause, []
        pat = re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, by_text)) + r")(?![\w-])")
        used: dict[str, tuple[Hit, str, str]] = {}

        def sub(m: re.Match[str]) -> str:
            used[m.group(0)] = by_text[m.group(0)]
            return by_text[m.group(0)][1]

        return pat.sub(sub, clause), list(used.values())

    def sanitise(
        self,
        text: str,
        session: str,
        seed: int | None = None,
        seq_start: int = 1,
        attributes: bool = True,
        attribute_floor: int = 0,
    ) -> Sanitised:
        self._text = text
        self._name_hits: list[Hit] = []
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
        self._name_hits = [e for e in det.entities if e.category in names]
        # never_leak entries with a pattern are withheld outright and take precedence over any
        # attribute clause they overlap.
        nl_hits: list[Hit] = []
        for entry in self.pack.outbound.never_leak:
            if not entry.pattern:
                continue
            if entry.internal_audience == "substitute" and self.audience == "internal":
                # the practitioner's own file: the names in the span are substituted and restored
                continue
            for m in re.finditer(entry.pattern, text, re.IGNORECASE):
                # A pattern may match its context ("works at ...") and withhold only the group
                # named "span", so that the sentence keeps its verb.
                s0, e0 = (
                    m.span("span") if "span" in m.re.groupindex and m.group("span") else m.span()
                )
                if s0 >= attribute_floor:
                    nl_hits.append(Hit(s0, e0, text[s0:e0], "ATTR:never_leak", entry.label, 0.99))
        # A remembered name (a gang withheld where it was introduced, in this message or an earlier
        # turn) is withheld at every later exact mention.
        self._repeats: set[tuple[int, int]] = set()
        remembered: list[tuple[str, str]] = []  # (name, never_leak label)
        by_placeholder = {
            e.withhold_as: e for e in self.pack.outbound.never_leak if e.remember and e.withhold_as
        }
        for prior in self.vault.mappings(session):
            if prior.kind == "withheld_name" and prior.surrogate in by_placeholder:
                remembered.append((prior.original, by_placeholder[prior.surrogate].label))
        for n in nl_hits:
            entry = next((e for e in self.pack.outbound.never_leak if e.label == n.detector), None)
            name = _withheld_name(n.text)
            if entry is not None and entry.remember and name:
                remembered.append((name, entry.label))
                self.vault.put(
                    Mapping(
                        session,
                        name,
                        entry.withhold_as or f"[withheld: {entry.label}]",
                        "ATTR:never_leak",
                        "withheld_name",
                        f"withheld:{hash(name) & 0xFFFF:04x}",
                    )
                )
        for name, label in remembered:
            for m in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
                if m.start() < attribute_floor or any(
                    n.start < m.end() and m.start() < n.end for n in nl_hits
                ):
                    continue
                nl_hits.append(Hit(m.start(), m.end(), m.group(0), "ATTR:never_leak", label, 0.99))
                self._repeats.add((m.start(), m.end()))
        ruled = {r.key for r in self.pack.outbound.attributes}

        def generalised_clause(a: Hit) -> bool:
            return a.category.split(":", 1)[1] in ruled

        def removes(a: Hit, n: Hit) -> bool:
            """Whether the clause's own rule drops the never_leak span: a rule that keeps part of
            the clause as written (a sub-clause without the cue) may keep the span too."""
            key = a.category.split(":", 1)[1]
            rule = self.pack.attribute_rule(key)
            out = gen.generalise_attribute(
                key, a.text, rule.generalise_to, self.pack.id, before=text[: a.start], note=text
            )
            return n.text.strip().lower() not in out.lower()

        # A never_leak span inside an attribute clause that this pack generalises is removed by
        # that clause's rule; inside any other clause it keeps its own precedence.
        contained = [
            n
            for n in nl_hits
            if any(
                a.start <= n.start and n.end <= a.end and generalised_clause(a) and removes(a, n)
                for a in det.attributes
            )
        ]
        nl_hits = [n for n in nl_hits if n not in contained]
        # An attribute clause that a never_leak span cuts keeps its part before the span, when that
        # part is a clause of its own ("arrested for shop theft in Hougang ... linked to a group
        # called" before a withheld gang name), so the offence is still generalised.
        attrs = []
        for a in det.attributes:
            cuts = [n for n in nl_hits if n.start < a.end and a.start < n.end]
            if cuts:
                head = text[a.start : min(n.start for n in cuts)].rstrip(" ,;:'\"\u2018\u201c")
                if len(head.split()) < 4:
                    continue
                a = Hit(a.start, a.start + len(head), head, a.category, a.detector, a.score)
            attrs.append(self._keep_subject(text, self._fit_span(text, a), det.entities))
        # Two rules may read the same clause ("Charged with rioting and awaiting Youth Court
        # mention" holds an offence cue and a minor cue). The clause goes to the rule that
        # generalises it, not to one that would leave it as written.
        attrs = _prefer_changing(attrs, lambda a: self._changes(text, a))
        attrs += nl_hits
        redacting = {
            r.key for r in self.pack.outbound.attributes if r.generalise_to == "redact"
        } | {"never_leak"}
        absorbed: list[Hit] = []
        # A piece of an entity left outside a redacted span -> the whole entity it was cut from.
        pieces: dict[tuple[int, int], Hit] = {}
        for a_hit in attrs:
            if a_hit.start < attribute_floor:
                continue
            overlapping = [e for e in det.entities if e.start < a_hit.end and a_hit.start < e.end]
            key = a_hit.category.split(":", 1)[1] if ":" in a_hit.category else ""

            # A redacted clause (safety plan, never_leak) takes its unit numbers and phones with
            # it. Any other clause absorbs names, and estates and ages that lie wholly inside it
            # ("arrested for shop theft in Hougang"), which are replaced within the clause's
            # outbound text; a clause holding another entity is left to entity substitution.
            def absorbable(e: Hit, a: Hit = a_hit) -> bool:
                # a mall inside the clause ("caught shoplifting at Jurong Point") is a place, and
                # it is generalised within the clause's outbound text like an estate
                return e.category in names or (
                    (
                        e.category in {"ESTATE", "AGE"}
                        or e.detector == "gazetteer.place"
                        # a lower-case "employer" a model misread ("community service") names no
                        # organisation and must not keep the clause's offence as written
                        or (e.category == "EMPLOYER" and not _proper_noun(e.text))
                    )
                    and a.start <= e.start
                    and e.end <= a.end
                )

            if key in redacting or all(absorbable(e) for e in overlapping):
                spans = [e for e in spans if e not in overlapping] + [a_hit]
                absorbed += [e for e in overlapping if absorbable(e)]
                if key in redacting:
                    # An entity that runs past the redacted span ("Rumah Damai Womens" before a
                    # withheld "Shelter, Blk 8 ...") keeps the part outside it, which is then
                    # generalised or substituted like any other entity.
                    for e in overlapping:
                        for p in _outside(text, e, a_hit):
                            spans.append(p)
                            pieces[(p.start, p.end)] = e
        spans = _drop_nested(spans)
        # A generalised clause that keeps its sentence (or a clause kept as written) still carries
        # the names it absorbed: those names are substituted inside the clause's outbound text.
        absorbed = [
            e
            for e in absorbed
            if not any(k.start <= e.start and e.end <= k.end and k.category in names for k in spans)
        ]
        forbidden = {h.text for h in spans + absorbed}
        # the gender each name's pronouns indicate, for a name whose gender the lists do not know
        self._pronoun_gender = gender_from_pronouns(
            text, [(h.start, h.end, h.text) for h in spans + absorbed if h.category == "NAME"]
        )
        factory = SurrogateFactory(
            seed if seed is not None else int(hashlib.sha256(session.encode()).hexdigest()[:8], 16),
            forbidden,
        )
        # Consistent surrogates: same original text -> same outbound text, within this call and
        # across calls in the same session (a second turn, a regeneration). Names are assigned
        # longest-first so that a short form seen before its full form maps to the same person.
        memo: dict[tuple[str, str], tuple[str, str, str | None]] = {}
        prior_names = []
        for prior in self.vault.mappings(session):
            if prior.kind == "surrogate":
                memo[(prior.category, prior.original)] = (prior.surrogate, "surrogate", None)
                factory.used.add(prior.surrogate.lower())
                if prior.category == "NAME":
                    prior_names.append(prior)
        # fullest names first, so that a short form seen earlier joins its person
        for prior in sorted(prior_names, key=lambda m: -len(m.original.split())):
            _remember_person(factory, prior.original, prior.surrogate)
        for h in sorted(
            (h for h in spans + absorbed if h.category == "NAME"), key=lambda h: -len(h.text)
        ):
            key = (h.category, h.text)
            if key not in memo:
                memo[key] = self._replacement(h, factory, {})
        out, pos, replacements, rules = [], 0, [], []
        rule_ids: dict[tuple[int, int], str] = {}
        n_entities = len(memo)
        for h in sorted(spans, key=lambda h: h.start):
            key = (h.category, h.text)
            if key not in memo:
                whole = pieces.get((h.start, h.end))
                # A quasi-identifier piece is generalised from the whole entity, so that the kind
                # of place ("a crisis shelter") comes from the words the redaction took.
                basis = whole if whole is not None and h.category in QUASI_GENERALISERS else h
                memo[key] = self._replacement(basis, factory, {})
                n_entities += 1
            new, kind, rule_id = memo[key]
            inner: list[tuple[Hit, str, str]] = []
            if h.category.startswith("ATTR:") and new:
                new, inner = self._substitute_absorbed(
                    new, [e for e in absorbed if e.start < h.end and h.start < e.end], memo, factory
                )
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
            for e, e_new, e_kind in inner:
                replacements.append((e, e_new, e_kind))
                if e_kind in ("surrogate", "generalised") and e_new != e.text:
                    self._remember(session, e.category, e.text, e_new, e_kind)
            if rule_id:
                rule_ids[(h.start, h.end)] = rule_id
            if kind == "generalised":
                rules.append({"rule": rule_id, "category": h.category, "to": new})
            if (
                kind in ("surrogate", "generalised")
                and new != h.text
                and (h.start, h.end) not in self._repeats
            ):
                # a later mention of a withheld name restores from its first mention's mapping
                self._remember(session, h.category, h.text, new, kind)
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


# What may precede the person a clause is about, and the age that may follow the name.
_SUBJECT_LEAD = re.compile(
    r"(?:(?:Client|Clt|Patient|Pt|Young person|YP|Subject)\s*:?\s*)?"
    r"(?:(?:Mdm|Madam|Mr|Mrs|Ms|Miss|Master|Encik|Puan|Cik)\.?\s+)?",
    re.IGNORECASE,
)
_APPOSITIVE = re.compile(r"(?:\s*,\s*(?:age\s*|aged\s*)?\d{1,3}\s*(?:,|(?=\s)))?\s*")


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
    elif category == "URL":
        # a reply that drops the scheme or "www." still restores
        def bare(u: str) -> str:
            return re.sub(r"(?i)^(?:https?://)?(?:www\.)?", "", u)

        if bare(surrogate) != surrogate and bare(original) != original:
            out.append((bare(original), bare(surrogate)))
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
        # the address without its postal code, as a reply often writes it
        o_core = re.sub(r",?\s*(?:Singapore\s*)?\(?S?\(?\d{6}\)?\s*$", "", original)
        n_core = re.sub(r",?\s*(?:Singapore\s*)?\(?S?\(?\d{6}\)?\s*$", "", surrogate)
        if o_core != original and n_core != surrogate and n_core.strip():
            out.append((o_core, n_core))
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
    r"\b[A-Z][a-z]+(?: [A-Z][a-z]+){0,2} (?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Crescent|Cres|Close|Walk|Way|Link|Loop|Rise|View|Terrace|Place|Grove|Hill|Park|Central|North|South|East|West)"
    r"(?: \d{1,3})?\b|\b(?:Lorong|Jalan) [A-Z0-9][A-Za-z0-9]*\b"
)


def _withheld_name(text: str) -> str | None:
    """The name inside a withheld span ("the 'Red Eagles'" -> "Red Eagles"), or None when what is
    left is too short or not a name."""
    t = re.sub(r"(?i)^the\s+", "", text.strip())
    t = t.strip("'\"\u2018\u2019\u201c\u201d ")
    if len(t) < 3 or not re.match(r"[A-Z0-9]", t):
        return None
    return t


_GENERIC_ORG = {
    "employer", "employers", "company", "workplace", "firm", "boss", "office", "warehouse",
    "factory", "shop", "store", "restaurant", "cafe", "job", "work", "workshop", "outlet",
}  # fmt: skip
_DEPARTMENT = {
    "hr", "human", "resources", "department", "dept", "team", "office", "manager", "supervisor",
    "admin", "administration", "management", "payroll", "job", "staff", "personnel", "unit",
}  # fmt: skip


def _generic_org(text: str, before: str) -> bool:
    """Whether an employer span is a generic phrase rather than an organisation's name: a bare
    generic noun ("employer"), or a generic noun after a possessive ("his warehouse job", "his
    employer's HR department"), with nothing else but department words."""
    words = re.sub(r"^(?:the|a|an)\s+", "", text.strip(), flags=re.IGNORECASE).split()
    if not words:
        return False
    head = re.sub(r"(?:'s|\u2019s|s')$", "", words[0].lower())
    lows = [w.lower().strip(",.") for w in words]
    if any(w not in _GENERIC_ORG | _DEPARTMENT for w in [head, *lows[1:]]):
        return False
    possessive = re.search(
        r"(?:\b(?:his|her|their|my|our|your|its)|(?:'s|\u2019s))\s*$", before, re.IGNORECASE
    )
    # a bare role word ("a note for an employer"); a bare kind of workplace ("a cafe") keeps the
    # pack's employer rule
    bare_role = len(words) == 1 and head in {
        "employer",
        "employers",
        "company",
        "workplace",
        "boss",
    }
    return bare_role or bool(possessive) or words[0].lower().endswith(("'s", "\u2019s"))


def _proper_noun(text: str) -> bool:
    """Whether a phrase names something: a capitalised word after any leading article."""
    words = re.sub(r"^(?:the|a|an)\s+", "", text.strip(), flags=re.IGNORECASE).split()
    return any(w[:1].isupper() or w[:1].isdigit() for w in words)


def _at_sentence_start(prefix: str) -> bool:
    stripped = prefix.rstrip(" ")
    return stripped == "" or stripped.endswith((".", "!", "?", "\n", ":"))


def _remember_person(factory: SurrogateFactory, original: str, surrogate: str) -> None:
    """Register a person mapped in an earlier turn of the session, so that a later variant of the
    name (given name, titled form) takes a form of the same surrogate."""
    from socareguard.corpus import names as nm
    from socareguard.outbound.surrogates import _TITLES, guess_gender, guess_origin, title_token

    def bare(name: str) -> str:
        low = name.strip()
        first, _, rest = low.partition(" ")
        return rest if first.lower().rstrip(".") in _TITLES and rest else low

    o, s = bare(original).lower(), bare(surrogate)
    toks = [t for t in re.split(r"[\s,()/]+", s) if t]
    if not toks or o in factory.persons:
        return
    full_known = [k for k in factory.persons if o in k.split() or set(o.split()) < set(k.split())]
    if full_known:
        return  # a short form of a person already registered from a fuller mapping
    title_part = title_token(s) or toks[0]
    given = toks[1] if len(toks) > 2 and toks[0].lower() in {"nur", "siti", "muhammad"} else toks[0]
    factory.persons[o] = nm.PersonName(
        guess_origin(s), guess_gender(surrogate), s, given, f"Mdm {title_part}"
    )


def _prefer_changing(attrs: list[Hit], changes) -> list[Hit]:
    """Among attribute hits on the same span, put one whose rule changes the clause first, so
    that the span keeps that one."""
    by_span: dict[tuple[int, int], list[Hit]] = {}
    for a in attrs:
        by_span.setdefault((a.start, a.end), []).append(a)
    out: list[Hit] = []
    for group in by_span.values():
        if len(group) > 1:
            group = sorted(group, key=lambda a: not changes(a))
        out += group
    return sorted(out, key=lambda a: a.start)


def _outside(text: str, e: Hit, cut: Hit) -> list[Hit]:
    """The parts of entity ``e`` that lie outside the span ``cut``, trimmed of spaces and
    punctuation; parts shorter than two word characters are dropped."""
    out = []
    for s, t in ((e.start, min(e.end, cut.start)), (max(e.start, cut.end), e.end)):
        if t <= s:
            continue
        piece = text[s:t]
        lead = len(piece) - len(piece.lstrip(" ,;:-"))
        piece = piece.strip(" ,;:-")
        if len(re.sub(r"\W", "", piece)) < 2:
            continue
        out.append(Hit(s + lead, s + lead + len(piece), piece, e.category, e.detector, e.score))
    return out


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
