"""Round 2 (2026-09-28), MSW-F6 and WSDM-N1: a reformatted surrogate was restored in part and fused
with the words around it ("Mr. Wee Hao Kow", "Blk 512 Choa Bedok North Street 3", "aged between
5"). A surrogate is now restored as a unit or not at all, and a partial restore is a flag."""

from pathlib import Path

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from tests import recorded_round2 as rec


def _guard(tmp_path: Path) -> Guard:
    return Guard(vault=Vault(tmp_path / "v.sqlite"), ledger=Ledger(tmp_path / "l.jsonl"))


def _send(guard: Guard, note: dict, session: str) -> dict:
    """Run the note once with an empty reply to fill the vault; return the replacement table."""
    res = guard.run(
        [{"role": "user", "content": note["text"]}],
        note["pack"],
        "openai/gpt-4.1-mini",
        session=session,
        reply_fixture="ok",
        seed=7,
    )
    return {r["original"]: r["outbound"] for r in res.replacements}


def _reply(guard: Guard, note: dict, session: str, reply: str):
    return guard.run(
        [{"role": "user", "content": note["text"]}],
        note["pack"],
        "openai/gpt-4.1-mini",
        session=session,
        reply_fixture=reply,
        seed=7,
    )


def test_a_titled_surrogate_with_a_full_stop_restores_whole(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "msw_6")
    g = _guard(tmp_path)
    table = _send(g, note, "msw6")
    surrogate = table["Mr Lim Ah Kow"]  # "Mr <three tokens>"
    dotted = surrogate.replace("Mr ", "Mr. ", 1)
    res = _reply(g, note, "msw6", f"Patient: {dotted}, 68.")
    assert "Mr Lim Ah Kow" in res.reply, res.reply
    for tok in surrogate.split()[1:]:
        assert tok not in res.reply, res.reply
    assert res.decision == "pass"


def test_a_surrogate_reordered_by_the_model_is_left_whole_and_flagged(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "msw_6")
    g = _guard(tmp_path)
    table = _send(g, note, "msw6b")
    toks = table["Mr Lim Ah Kow"].split()[1:]
    # surname last and given names first: no stored form matches, but single pieces would
    reordered = " ".join([*toks[1:], toks[0]])
    res = _reply(g, note, "msw6b", f"Patient {reordered} was admitted after a fall.")
    for real in ("Lim", "Kow"):
        assert real not in res.reply, res.reply
    lk = next(e for e in res.events if e.kind == "leakcheck")
    assert lk.passed is False
    assert res.decision == "annotate"
    flag = next(f for f in res.flags if f.label == "UNRESTORED")
    assert reordered.split()[0] in flag.evidence


def test_an_address_without_its_postal_code_restores_as_a_unit(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "wsdm_a_dv")
    g = _guard(tmp_path)
    table = _send(g, note, "wsdm-a")
    original = "Blk 512 Bedok North Street 3 #07-119, Singapore 460512"
    surrogate = table[original]
    without_postal = surrogate.split(",")[0]
    res = _reply(g, note, "wsdm-a", f"She lives at {without_postal}, Singapore.")
    assert "Blk 512 Bedok North Street 3 #07-119" in res.reply, res.reply
    for tok in without_postal.split()[1:]:
        if tok not in original:
            assert tok not in res.reply, (tok, res.reply)
    assert res.decision == "pass", res.events


def test_an_address_reformatted_beyond_restore_is_never_mixed(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "wsdm_a_dv")
    g = _guard(tmp_path)
    table = _send(g, note, "wsdm-a2")
    surrogate = table["Blk 512 Bedok North Street 3 #07-119, Singapore 460512"]
    blk, rest = surrogate.split(" ", 2)[1], surrogate.split(" ", 2)[2]
    street = rest.split(" #")[0]
    # the model abbreviated the street type and dropped the unit
    abbreviated = f"Blk {blk} {street.replace('Street', 'St').replace('Avenue', 'Ave')}"
    res = _reply(g, note, "wsdm-a2", f"Home visit at {abbreviated}.")
    # either every piece comes back or none does: never an original piece beside a surrogate one
    assert res.reply in (
        f"Home visit at {abbreviated}.",
        "Home visit at Blk 512 Bedok North Street 3.",
    ), res.reply
    if res.reply != "Home visit at Blk 512 Bedok North Street 3.":
        lk = next(e for e in res.events if e.kind == "leakcheck")
        assert lk.passed is False and any(f.label == "UNRESTORED" for f in res.flags)


def test_an_age_band_is_not_restored_inside_a_band_phrase(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "wsdm_a_dv")
    g = _guard(tmp_path)
    table = _send(g, note, "wsdm-a3")
    band = table["5"]
    res = _reply(g, note, "wsdm-a3", f"The younger child is aged between {band}.")
    assert "aged between 5." not in res.reply, res.reply


def test_the_reviewers_address_restores_without_a_stray_estate_token(tmp_path):
    """wsdm-9.json, a_dv_round1_note: the surrogate and the reply as the reviewer recorded them."""
    from socareguard.inbound.restore import restore
    from socareguard.outbound.sanitise import Sanitiser
    from socareguard.policy.loader import load_pack

    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    s._remember(
        "n1",
        "ADDRESS",
        "Blk 512 Bedok North Street 3 #07-119, Singapore 460512",
        "Blk 963A Choa Chu Kang Avenue 4 #14-097, Singapore 685032",
        "surrogate",
    )
    r = restore("residing at Blk 963A Choa Chu Kang Avenue 4 #14-097, Singapore", vault, "n1")
    assert r.text == "residing at Blk 512 Bedok North Street 3 #07-119, Singapore", r.text
    assert not r.unrestored_surrogates and not r.partial
