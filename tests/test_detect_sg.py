from socareguard.detect import sg
from socareguard.detect.pipeline import detect

TEXT = (
    "Client Tan Wei Ming, NRIC S1234567D (also typed S1234567A), DOB 14/03/2011, born 2011-03-14. "
    "Address: Blk 412 Yishun Ring Road #07-123, Singapore 760412. Contact 9123 4567 or +65 6234 5678. "
    "Youth Court reference YC/2026/0412; FSC ref FSC-2026-0288. Seen on 2 Sep 2026 for 40 hours of service."
)


def test_nric_with_and_without_valid_checksum():
    hits = sg.find_nric(TEXT)
    assert [(h.text, h.score) for h in hits] == [("S1234567D", 1.0), ("S1234567A", 0.6)]


def test_address_parts():
    cats = {(h.detector, h.text) for h in sg.find_all(TEXT) if h.category == "ADDRESS"}
    # round 4: the street after the block belongs to the block span
    assert ("sg.street", "Blk 412 Yishun Ring Road") in cats
    assert ("sg.unit", "#07-123") in cats
    assert any(d == "sg.postal" and "760412" in t for d, t in cats)


def test_phone_and_case_refs():
    phones = [h.text for h in sg.find_phone(TEXT)]
    assert "9123 4567" in phones and "+65 6234 5678" in phones
    refs = [h.text for h in sg.find_case_ref(TEXT)]
    assert refs == ["YC/2026/0412", "FSC-2026-0288"]


def test_dob_vs_date_of_contact():
    hits = {h.text: h.category for h in sg.find_dob(TEXT)}
    assert hits["14/03/2011"] == "DOB"
    assert hits["2011-03-14"] == "DOB"
    assert hits["2 Sep 2026"] == "DATE"


def test_spans_reslice_and_no_nested_duplicates():
    hits = sg.find_all(TEXT)
    for h in hits:
        assert TEXT[h.start : h.end] == h.text
    starts = [(h.start, h.end) for h in hits]
    assert len(starts) == len(set(starts))


def test_a_date_without_a_year_is_never_a_dob():
    from socareguard.detect.pipeline import _sane
    from socareguard.detect.sg import Hit

    assert not _sane(Hit(0, 5, "2 Sep", "DOB", "gliner", 0.9))
    assert _sane(Hit(0, 10, "2 Sep 1990", "DOB", "gliner", 0.9))
    assert _sane(Hit(0, 8, "02/09/90", "DOB", "gliner", 0.9))


def test_lowercase_employer_phrase_is_detected():
    # A generic employer has no capital letter ("a shipyard"); the lower-case filter that
    # rejects "the void deck" as a facility must not reject it as an employer.
    text = "He works as a welder at a shipyard and his shifts end late."
    ents = detect(text, use_presidio=False, use_gliner=False).entities
    assert ("EMPLOYER", "a shipyard") in [(h.category, h.text) for h in ents]


def test_age_in_a_parenthesis_with_a_comma_is_an_age():
    """Round 3, WSDM N7: "Kaiden (6, Naval Base Primary School)" was not banded."""
    from socareguard.detect.gazetteers import find_ages

    for text, age in (
        ("with son Kaiden (6, Naval Base Primary School).", "6"),
        ("with son Kaiden (6).", "6"),
        ("her son, aged 6, attends school.", "6"),
    ):
        assert [h.text for h in find_ages(text)] == [age], text
    assert find_ages("see appeal (2, attached)") == []
