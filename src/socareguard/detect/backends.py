"""Presidio and GLiNER backends, mapped onto the corpus categories.

Both are reused, credited components. Presidio contributes NER-backed names and its
``SG_NRIC_FIN`` recogniser; GLiNER contributes zero-shot spans for names, addresses and
the sensitive-attribute labels that no entity catalogue has. GLiNER2-PII
(``fastino/gliner2-privacy-filter-PII-multi``) is used when the ``gliner2`` package loads,
otherwise ``urchade/gliner_multi_pii-v1``.
"""

from __future__ import annotations

import os
from functools import lru_cache

from socareguard.detect.sg import Hit

PRESIDIO_MAP = {
    "PERSON": "NAME",
    "SG_NRIC_FIN": "NRIC",
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "DATE_TIME": "DATE",
}
PRESIDIO_MIN = {"NAME": 0.6, "NRIC": 0.4, "PHONE": 0.4, "EMAIL": 0.5, "DATE": 0.95}

GLINER_LABELS = {
    "person": "NAME",
    "national identity number": "NRIC",
    "phone number": "PHONE",
    "home address": "ADDRESS",
    "school": "SCHOOL",
    "shelter or care facility or hospital": "FACILITY",
    "employer": "EMPLOYER",
    "case reference number": "CASE_REF",
    "date of birth": "DOB",
}
ATTRIBUTE_LABELS = {
    "disability or medical diagnosis": "disability",
    "disclosure of domestic violence or abuse": "dv_disclosure",
    "protection order status": "ppo",
    "safety plan details": "safety_plan",
    "criminal offence or charge": "offence",
    "decision-making capacity assessment": "capacity",
}


@lru_cache(maxsize=1)
def _presidio():
    from presidio_analyzer import AnalyzerEngine

    return AnalyzerEngine()


def presidio_hits(text: str) -> list[Hit]:
    out = []
    for r in _presidio().analyze(text=text, language="en"):
        cat = PRESIDIO_MAP.get(r.entity_type)
        if not cat or r.score < PRESIDIO_MIN[cat]:
            continue
        out.append(
            Hit(
                r.start,
                r.end,
                text[r.start : r.end],
                cat,
                f"presidio.{r.entity_type}",
                float(r.score),
            )
        )
    return out


class _Gliner1:
    name = "urchade/gliner_multi_pii-v1"

    def __init__(self):
        from gliner import GLiNER

        self.model = GLiNER.from_pretrained(self.name)

    def predict(self, text: str, labels: list[str], threshold: float) -> list[dict]:
        return self.model.predict_entities(text, labels, threshold=threshold)


class _Gliner2:
    name = "fastino/gliner2-privacy-filter-PII-multi"

    def __init__(self):
        from gliner2 import GLiNER2

        self.model = GLiNER2.from_pretrained(self.name)

    def predict(self, text: str, labels: list[str], threshold: float) -> list[dict]:
        res = self.model.extract_entities(
            text, labels, threshold=threshold, include_spans=True, include_confidence=True
        )
        ents = res.get("entities", res) if isinstance(res, dict) else res
        out = []
        for label, items in ents.items():
            for it in items:
                if isinstance(it, dict) and it.get("start") is not None:
                    out.append(
                        {
                            "start": it["start"],
                            "end": it["end"],
                            "text": it.get("text"),
                            "label": label,
                            "score": float(it.get("confidence", it.get("score", 0.5))),
                        }
                    )
        return out


@lru_cache(maxsize=1)
def _gliner():
    want = os.environ.get("SOCAREGUARD_GLINER", "auto")
    if want in ("auto", "gliner2"):
        try:
            return _Gliner2()
        except Exception:
            if want == "gliner2":
                raise
    return _Gliner1()


def gliner_backend_name() -> str:
    return _gliner().name


def gliner_hits(text: str, threshold: float = 0.5) -> list[Hit]:
    out = []
    for e in _gliner().predict(text, list(GLINER_LABELS), threshold):
        if e.get("start") is None:
            continue
        cat = GLINER_LABELS[e["label"]]
        out.append(
            Hit(e["start"], e["end"], text[e["start"] : e["end"]], cat, "gliner", float(e["score"]))
        )
    return out


def gliner_attribute_hits(text: str, threshold: float = 0.4) -> list[Hit]:
    out = []
    for e in _gliner().predict(text, list(ATTRIBUTE_LABELS), threshold):
        if e.get("start") is None:
            continue
        key = ATTRIBUTE_LABELS[e["label"]]
        out.append(
            Hit(
                e["start"],
                e["end"],
                text[e["start"] : e["end"]],
                f"ATTR:{key}",
                "gliner.attr",
                float(e["score"]),
            )
        )
    return out
