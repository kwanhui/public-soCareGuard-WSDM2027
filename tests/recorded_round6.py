"""Round-6 household notes with the Presidio and GLiNER2 hits recorded on them (2026-09-28).

Recorded by running both NER backends on each message as the proxy sends it (the instruction and
the note joined by a blank line). ``use(monkeypatch, name)`` replays the recorded hits, as in
tests/recorded_round5.py. The family service centre note is verbatim from the round-2 FSC social
worker's finding F3. The safe-contact note is
the round-4 DV advocate's note (finding DV-N4, a shared surname), rebuilt from its
outbound text and its detected spans, which it matches at every offset."""

from __future__ import annotations

from socareguard.detect import backends
from socareguard.detect.sg import Hit

NOTES: dict[str, dict] = {
    "fsc_household": {
        "pack": "domestic-violence",
        "text": (
            "Summarise this note and draft three next steps for the case file.\n\n"
            "Case summary, 28 Sep 2026. Client: Farhana binti Rosli, NRIC S8834211A, age 34, "
            "residing at Blk 118 Ang Mo Kio Avenue 4 #09-233, Singapore 560118. Household: "
            "husband Zulkifli bin Hassan (contact 91234567), children Amirah (10, P4 at "
            "Yishun Primary School) and Danish (7, P1 at Northview Primary School). "
            "Grandmother Rosnah binti Rosli, same surname as the client, lives with the "
            "family and helps with childcare.\n\n"
            "Presenting concern: Farhana reports her husband has been verbally abusive after "
            "losing his job in June 2026, and raised his hand at her once in August but did "
            "not strike her. She is considering moving to her sister's flat in Sengkang "
            "temporarily.\n\n"
            "Assessment: moderate risk, no protection order filed yet. Family is cooperative "
            "and open to counselling."
        ),
        "presidio": [
            (102, 121, "Farhana binti Rosli", "NAME", 0.85),
            (233, 252, "Zulkifli bin Hassan", "NAME", 0.85),
            (282, 288, "Amirah", "NAME", 0.85),
            (383, 401, "Rosnah binti Rosli", "NAME", 0.85),
            (500, 507, "Farhana", "NAME", 0.85),
        ],
        "gliner": [
            (233, 252, "Zulkifli bin Hassan", "NAME", 0.99),
            (102, 121, "Farhana binti Rosli", "NAME", 0.98),
            (383, 401, "Rosnah binti Rosli", "NAME", 0.97),
            (282, 288, "Amirah", "NAME", 0.9),
            (327, 333, "Danish", "NAME", 0.85),
            (128, 137, "S8834211A", "NRIC", 0.99),
            (262, 270, "91234567", "PHONE", 0.99),
            (344, 368, "Northview Primary School", "SCHOOL", 1.0),
            (300, 321, "Yishun Primary School", "SCHOOL", 1.0),
        ],
        "gliner_attr": [
            (755, 784, "no protection order filed yet", "ATTR:ppo", 0.62),
            (740, 753, "moderate risk", "ATTR:capacity", 0.42),
        ],
    },
    "dv_safe_contact": {
        "pack": "domestic-violence",
        "text": (
            "Write a short case note for the file.\n\n"
            "Contact note, 27 Sep 2026. Client Mdm Aishah binti Karim, 28, case ref "
            "FSC-2026-5512. Aishah's safe contact in an emergency is her mother, Mdm Zainab "
            "binti Karim, who lives separately and is not known to Aishah's husband Hafiz bin"
            " Nordin. Aishah has given the centre Zainab's number to call if she cannot be "
            "reached.\n\n"
            "Assessment: safe contact confirmed and recorded."
        ),
        "presidio": [
            (73, 95, "Mdm Aishah binti Karim", "NAME", 0.85),
            (125, 131, "Aishah", "NAME", 0.85),
            (178, 200, "Mdm Zainab binti Karim", "NAME", 0.85),
            (243, 249, "Aishah", "NAME", 0.85),
            (260, 276, "Hafiz bin Nordin", "NAME", 0.85),
            (278, 284, "Aishah", "NAME", 0.85),
            (306, 312, "Zainab", "NAME", 0.85),
        ],
        "gliner": [
            (260, 276, "Hafiz bin Nordin", "NAME", 1.0),
            (77, 95, "Aishah binti Karim", "NAME", 1.0),
            (182, 200, "Zainab binti Karim", "NAME", 0.99),
            (110, 123, "FSC-2026-5512", "CASE_REF", 0.99),
            (97, 99, "28", "DOB", 0.5),
        ],
        "gliner_attr": [],
    },
}


def _hits(name: str, backend: str, detector: str):
    def fn(text: str, *args, **kwargs) -> list[Hit]:
        note = NOTES[name]
        if text != note["text"]:
            return []
        return [Hit(s, e, t, cat, detector, sc) for s, e, t, cat, sc in note[backend]]

    return fn


def use(monkeypatch, name: str) -> dict:
    """Replay the recorded NER hits for note ``name`` and return the note (pack and text)."""
    monkeypatch.setattr(backends, "presidio_hits", _hits(name, "presidio", "presidio.PERSON"))
    monkeypatch.setattr(backends, "gliner_hits", _hits(name, "gliner", "gliner"))
    monkeypatch.setattr(
        backends, "gliner_attribute_hits", _hits(name, "gliner_attr", "gliner.attr")
    )
    monkeypatch.setattr(backends, "gliner_backend_name", lambda: "recorded")
    return NOTES[name]
