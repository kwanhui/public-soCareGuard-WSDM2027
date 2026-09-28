"""Cue-lexicon detector for sensitive attributes.

Sensitive attributes are disclosures, not entities: "disclosed that her husband pushed her",
"has capacity for this decision", "is 14 and under Youth Court investigation". A zero-shot
span model finds some of them; these clause-level cues find the rest. The span returned is
the clause containing the cue, from the previous sentence or clause boundary to the next,
because the whole clause is what the policy pack generalises.
"""

from __future__ import annotations

import re

from socareguard.detect.sg import Hit

CUES: dict[str, re.Pattern[str]] = {
    "dv_disclosure": re.compile(
        r"\b(disclos\w*|report\w*|stated|said|alleg\w*)\b[^.;\n]{0,80}\b(hit|hits|hitting|push\w*|slap\w*|punch\w*|kick\w*|shout\w*|threw|throw\w*|hurt|assault\w*|abus\w*|violen\w*|threat\w*|strangl\w*|choke\w*|monitor\w*|controll\w*|restrict\w*|bruis\w*|injur\w*)\b"
        r"|\b(family violence|domestic violence|physical (?:abuse|violence)|coercive control|financial abuse|emotional abuse|verbal abuse)\b",
        re.IGNORECASE,
    ),
    "ppo": re.compile(
        r"\b(PPO|personal protection order|protection order|expedited order|domestic exclusion order|DEO)\b"
        # a court hearing with its date or venue, in a clause of its own ("hearing set for 6 Oct")
        r"|\b(?:court\s+)?(hearing|mention)\b(?=[^.;\n]{0,60}(?:\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|\b\d{1,2}/\d{1,2}\b|family justice|\bFJC\b|\bcourts?\b))",
        re.IGNORECASE,
    ),
    "safety_plan": re.compile(
        r"\b(safety plan\w*|safety steps|safety measures|harm reduction|packed bag|go[- ]bag|spare (?:set of )?keys?|code word|escape (?:route|plan)|exit plan|safe (?:place|room|house)|hides? (?:her|his|the) (?:passport|documents|phone))\b",
        re.IGNORECASE,
    ),
    "minor": re.compile(
        r"\b(a minor|minor status|under (?:the age of )?(?:16|18|21)|juvenile|young person|youth court|CYPA|under investigation|below 18)\b",
        re.IGNORECASE,
    ),
    "offence": re.compile(
        r"\b(offen[cs]e\w*|charg\w*|theft|shoplift\w*|stole\w*|steal\w*|riot\w*|vandal\w*|drug[- ]related|cannabis|inhalant|probation|arrest\w*|police report|diversion|restitution|community service|reoffend\w*|recidiv\w*|caught (?:vaping|fighting)|fighting)\b",
        re.IGNORECASE,
    ),
    "capacity": re.compile(
        r"\b(capacity|deputy\w*|donee|mental capacity act|MCA|decision[- ]making|able to (?:understand|weigh|retain)|assent|supported decision)\b",
        re.IGNORECASE,
    ),
    "diagnosis": re.compile(
        r"\b(diagnos\w*|schizophreni\w*|bipolar|depressi\w*|anxiety disorder|epilep\w*|dementia|stroke|cerebral palsy|autis\w*|ADHD|down syndrome|psychiatric|IMH follow[- ]up|medication"
        r"|(?:mild|moderate|severe|profound)?\s*(?:intellectual|learning|developmental) (?:disability|delay)|global developmental delay|spondylosis|lumbar|cardiac|diabet\w*|hypertens\w*|cancer|renal|dialysis)\b",
        re.IGNORECASE,
    ),
    "disability": re.compile(
        r"\b(disabilit\w*|intellectual|wheelchair|mobility aid\w*|walking frame|hearing impair\w*|visual impair\w*|blind|deaf|communication board|special (?:needs|education)|brain injury|impairment)\b",
        re.IGNORECASE,
    ),
}
_BOUNDARY = re.compile(r"[;\n]|\.(?=\s|$)|(?<=[a-z]),\s+(?=(?:and|but|which|who)\b)")


def _clause(text: str, pos: int) -> tuple[int, int]:
    starts = [m.end() for m in _BOUNDARY.finditer(text, 0, pos)]
    start = starts[-1] if starts else 0
    m = _BOUNDARY.search(text, pos)
    end = m.start() if m else len(text)
    while start < end and text[start] in " \t":
        start += 1
    return start, end


def find_attributes(text: str, keys: set[str] | None = None) -> list[Hit]:
    out: list[Hit] = []
    seen: set[tuple[str, int, int]] = set()
    for key, pat in CUES.items():
        if keys and key not in keys:
            continue
        for m in pat.finditer(text):
            s, e = _clause(text, m.start())
            if e - s < 4 or (key, s, e) in seen:
                continue
            seen.add((key, s, e))
            out.append(Hit(s, e, text[s:e], f"ATTR:{key}", "cue", 0.7))
    return sorted(out, key=lambda h: (h.start, -(h.end - h.start)))
