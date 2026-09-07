from socareguard.corpus.schema import ConductLabel
from socareguard.taxonomy import INBOUND, categories_for_pack


def test_ids_unique_and_match_labels():
    ids = [c.id for c in INBOUND]
    assert len(ids) == len(set(ids))
    labels = {l.value for l in ConductLabel}
    for i in ids:
        assert i in labels


def test_every_pack_has_categories():
    for p in ("disability", "domestic-violence", "youth-offending"):
        cats = categories_for_pack(p)
        assert len(cats) >= 10
        assert any(c.id == "OVER_CAUTION" for c in cats)
    assert not any(c.id == "I14" for c in categories_for_pack("disability"))
