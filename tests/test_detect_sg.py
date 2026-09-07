from socareguard.detect import sg

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
    assert ("sg.block", "Blk 412") in cats
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
