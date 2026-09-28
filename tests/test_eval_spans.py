from socareguard.corpus.inject import inject
from socareguard.detect import sg
from socareguard.eval import spans as ev
from tests.test_inject import make_template


def test_oracle_scores_perfectly():
    n = inject(make_template())
    rep = ev.score_note(n, ev.preds_from_spans(n.spans))
    d = rep.as_dict()
    assert d["exact"]["ALL"]["f1"] == 1.0 and d["relaxed"]["ALL"]["f1"] == 1.0
    assert d["leakage_matched"]["leakage_rate"] == 0.0
    assert d["leakage_covered"]["leakage_rate"] == 0.0
    assert d["recall_by_origin"]["chinese"]["recall"] == 1.0


def test_partial_and_wrong_category():
    n = inject(make_template())
    preds = ev.preds_from_spans(n.spans)
    # shift the NRIC by one char (relaxed hit, exact miss) and drop the phone (miss + leak)
    nric = next(p for p in preds if p.category == "NRIC")
    preds = [
        ev.Pred(p.start + 1, p.end, p.category) if p is nric else p
        for p in preds
        if p.category != "PHONE"
    ]
    d = ev.score_note(n, preds).as_dict()
    assert d["exact"]["NRIC"]["tp"] == 0 and d["relaxed"]["NRIC"]["tp"] == 1
    assert d["relaxed"]["PHONE"]["fn"] == 1
    assert d["leakage_matched"]["direct_missed"] == 1
    assert d["leakage_covered"]["direct_uncovered"] == 1


def test_sg_recognisers_against_gold():
    n = inject(make_template())
    preds = [ev.Pred(h.start, h.end, h.category, h.score) for h in sg.find_all(n.text)]
    d = ev.score_note(n, preds, categories=["NRIC", "PHONE", "CASE_REF", "DOB"]).as_dict()
    assert d["relaxed"]["NRIC"]["recall"] == 1.0
    assert d["relaxed"]["PHONE"]["recall"] == 1.0
    assert d["relaxed"]["CASE_REF"]["recall"] == 1.0


def test_merge_adds_counts():
    n = inject(make_template())
    r = ev.score_note(n, ev.preds_from_spans(n.spans))
    m = ev.merge([r, r]).as_dict()
    assert m["exact"]["ALL"]["tp"] == 2 * r.exact["ALL"].tp


def test_covered_leakage_counts_any_direct_detection_over_the_span():
    n = inject(make_template())
    preds = ev.preds_from_spans(n.spans)
    nric = next(p for p in preds if p.category == "NRIC")
    phone = next(p for p in preds if p.category == "PHONE")
    name = next(p for p in preds if p.category == "NAME")
    others = [p for p in preds if p not in (nric, phone, name)]
    # The NRIC detected as a phone number and a name detected in part are still substituted, so
    # they are covered, though the matched measure counts the NRIC as missed. The phone number,
    # overlapped only by a quasi-identifier detection, reaches the provider as written.
    preds = others + [
        ev.Pred(nric.start, nric.end, "PHONE"),
        ev.Pred(name.start, name.start + 2, "NAME"),
        ev.Pred(phone.start, phone.end, "ESTATE"),
    ]
    d = ev.score_note(n, preds).as_dict()
    assert d["leakage_matched"]["direct_missed"] == 2  # the NRIC and the phone number
    assert d["leakage_covered"]["direct_uncovered"] == 1  # the phone number only
    assert d["leakage_covered"]["direct_gold"] == d["leakage_matched"]["direct_gold"]


def test_one_detection_covers_every_gold_span_it_overlaps():
    n = inject(make_template())
    direct = [s for s in n.spans if s.type.value == "DIRECT"]
    lo, hi = min(s.start for s in direct), max(s.end for s in direct)
    d = ev.score_note(n, [ev.Pred(lo, hi, "ADDRESS")]).as_dict()
    assert d["leakage_covered"]["direct_uncovered"] == 0
    assert d["leakage_matched"]["direct_missed"] == len(direct) - 1
