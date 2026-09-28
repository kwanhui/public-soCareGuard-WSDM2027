"""Round 6 (2026-10-01): household-consistent surrogates.

Two people share a surrogate surname (Chinese, Eurasian, Western) or father-name (Malay, Indian)
when their original surname or father-name matches. A relation word before a name fixes the
relative's naming convention but never makes a surname shared. A titled surname that two
household members share is restored to the shared surname and marked, whereas a surrogate that
stands for two different people is never restored.

The reviewers' notes run with the NER hits recorded on them (tests/recorded_round5.py and
tests/recorded_round6.py)."""

import re
from pathlib import Path

from socareguard.inbound.leakcheck import leak_check
from socareguard.inbound.restore import ambiguous_person_flag, restore
from socareguard.ledger import Ledger
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.surrogates import (
    Kin,
    SurrogateFactory,
    household_key,
    households,
    shared_part,
    title_token,
)
from socareguard.outbound.vault import Mapping, Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import Guard, _sanitise_message
from tests import recorded_round5 as rec5
from tests import recorded_round6 as rec6


def _run(monkeypatch, tmp_path: Path, rec, name: str, session: str = "s"):
    note = rec.use(monkeypatch, name)
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(note["pack"]), audience="internal")
    return _sanitise_message(s, note["text"], session, 7, 1), vault, note


def _names(res) -> dict[str, str]:
    return {h.text: new for h, new, kind in res.replacements if h.category == "NAME"}


def _spans(text: str, names: list[str]) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), n) for n in names for m in re.finditer(re.escape(n), text)]


# households(): the unit the sanitiser computes over the whole message


def test_household_keys_by_surname_and_father_name():
    assert household_key("Tan Wei Ling") == ("surname", "tan")
    assert household_key("Mdm Tan") == ("surname", "tan")
    assert household_key("Jasmine Tan Hui Min") == ("surname", "tan")
    assert household_key("Melissa Pereira") == ("surname", "pereira")
    for spelling in ("binti", "bte", "binte", "bin", "bt"):
        assert household_key(f"Aishah {spelling} Karim") == ("father", "karim"), spelling
    assert household_key("Priya d/o Suresh") == ("father", "suresh")
    # a given name alone belongs to no household
    assert household_key("Wei Ming") is None
    assert household_key("Aishah") is None


def test_households_links_relatives_without_inventing_a_surname():
    text = (
        "Client Farhana binti Rosli, 34. Her husband Ridzwan works nights. Her grandmother "
        "Rosnah binti Rosli lives with them. Her father Rosli bin Osman visits."
    )
    names = ["Farhana binti Rosli", "Ridzwan", "Rosnah binti Rosli", "Rosli bin Osman"]
    kin = households(text, _spans(text, names))
    assert kin["Farhana binti Rosli"].key == kin["Rosnah binti Rosli"].key == ("father", "rosli")
    # the husband's name shows no convention: the relation word gives him the client's, and no
    # household
    assert kin["Ridzwan"] == Kin(key=None, origin="malay")
    # a named father is linked to the father-name his children carry
    assert kin["Rosli bin Osman"].father_of == ("father", "rosli")
    assert kin["Rosli bin Osman"].key == ("father", "osman")


def test_households_relation_word_leaves_own_convention_alone():
    text = "Client Mdm Lim Siew Hoon. Her husband Mr Wong Kok Leong. Their son Kai visits."
    kin = households(text, _spans(text, ["Mdm Lim Siew Hoon", "Mr Wong Kok Leong", "Kai"]))
    assert kin["Mr Wong Kok Leong"].key == ("surname", "wong")
    assert kin["Mr Wong Kok Leong"].origin is None  # his own name shows the convention
    assert kin["Kai"].origin == "chinese" and kin["Kai"].key is None


# The reviewers' notes


def test_fsc_same_surname_as_the_client_stays_true(monkeypatch, tmp_path):
    """FSC round-2 F3: "Grandmother Rosnah binti Rosli, same surname as the client" left as
    "Nadiah binti Rashid" beside a client "binti Rahman", so the sentence the model read was
    false."""
    res, _, _ = _run(monkeypatch, tmp_path, rec6, "fsc_household")
    names = _names(res)
    client, grandmother = names["Farhana binti Rosli"], names["Rosnah binti Rosli"]
    husband = names["Zulkifli bin Hassan"]
    assert shared_part(client, "malay") == shared_part(grandmother, "malay"), (client, grandmother)
    assert client != grandmother
    # the husband's father-name is his own
    assert shared_part(husband, "malay") != shared_part(client, "malay"), (husband, client)
    assert "same surname as the client" in res.text
    sentence = next(s for s in res.text.split(". ") if "same surname" in s)
    assert grandmother in sentence and shared_part(client, "malay") in sentence, sentence
    for original in ("Rosli", "Farhana", "Rosnah", "Zulkifli", "Hassan"):
        assert not re.search(rf"\b{original}\b", res.text), (original, res.text)


def test_dv_mother_as_safe_contact_shares_the_father_name_and_restores_in_full(
    monkeypatch, tmp_path
):
    """DV round-4: the client and her mother, the safe contact, are both "binti Karim". The
    surrogates now share a father-name too, and the model's reply restores 10 of 10 with the
    leak check passed."""
    note = rec6.use(monkeypatch, "dv_safe_contact")
    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
    )
    msgs = [{"role": "user", "content": note["text"]}]
    out = g.outbound(msgs, note["pack"], "dv4", seed=7)
    payload = out[4]
    client = re.search(r"Client (Mdm [\w ]+?), 28", payload).group(1)
    mother = re.search(r"her mother, (Mdm [\w ]+?), who", payload).group(1)
    husband = re.search(r"husband ([\w ]+?)\. ", payload).group(1)
    ref = re.search(r"case ref (\S+?)\.", payload).group(1)
    assert shared_part(client, "malay") == shared_part(mother, "malay"), (client, mother)
    c, m = client.split()[1], mother.split()[1]
    # the model's reply as recorded in round 4, over this run's surrogates
    reply = (
        f"**Case Note:**  \n**Date:** 27 Sep 2026  \n**Client:** {client}, 28  \n"
        f"**Case Ref:** {ref}  \n\nContact made to confirm emergency contacts. {c} identified her "
        f"mother, {mother}, as her safe contact in emergencies. {m} lives separately and is "
        f"unknown to {c}’s husband, {husband}. {c} has provided the centre with {m}’s "
        f"contact number to be used if {c} cannot be reached.  \n\n**Assessment:** Safe contact "
        f"confirmed and documented in client file."
    )
    res = g.run(
        msgs, note["pack"], "openai/gpt-4.1-mini", session="dv4", reply_fixture=reply, seed=7
    )
    assert res.reply == (
        "**Case Note:**  \n**Date:** 27 Sep 2026  \n**Client:** Mdm Aishah binti Karim, 28  \n"
        "**Case Ref:** FSC-2026-5512  \n\nContact made to confirm emergency contacts. Aishah "
        "identified her mother, Mdm Zainab binti Karim, as her safe contact in emergencies. Zainab "
        "lives separately and is unknown to Aishah’s husband, Hafiz bin Nordin. Aishah has "
        "provided the centre with Zainab’s contact number to be used if Aishah cannot be "
        "reached.  \n\n**Assessment:** Safe contact confirmed and documented in client file."
    ), res.reply
    assert res.ledger_row["n_restored"] == 10
    assert res.ledger_row["leakcheck_passed"]
    assert res.ledger_row["leakcheck_detail"]["ambiguous_people"] == []


def test_chinese_household_distinct_given_names_and_injective_forms(monkeypatch, tmp_path):
    """The disability case manager's care plan: the client, her sister and her brother are all
    Tan. They share a surrogate surname, have distinct given names, and no two share a full
    name or a short form. The neurologist, Koh, keeps a surname of his own."""
    res, vault, _ = _run(monkeypatch, tmp_path, rec5, "dcm_careplan")
    names = _names(res)
    fam = [names["Ms Tan Wei Ling"], names["Ms Tan Wei Hui"], names["Mr Tan Jun Wei"]]
    surnames = {title_token(n) for n in fam}
    assert len(surnames) == 1, fam
    assert title_token(names["Dr Lionel Koh"]) not in surnames, names
    givens = [n.split(maxsplit=2)[-1] for n in fam]
    assert len(set(givens)) == 3, givens
    # injective over full names and short forms, across every name in the session
    maps = [m for m in vault.mappings("s") if m.category == "NAME"]
    by_surrogate: dict[str, set[str]] = {}
    for m in maps:
        by_surrogate.setdefault(m.surrogate, set()).add(m.original)
    shared = {s for s, o in by_surrogate.items() if len(o) > 1}
    # only the household surname itself stands for more than one original form, and it stands
    # for the one surname "Tan"
    assert shared <= surnames, by_surrogate
    for s in shared:
        assert {o.lower() for o in by_surrogate[s]} == {"tan"}, by_surrogate[s]


def test_spouse_with_another_surname_keeps_another_surrogate_surname(tmp_path):
    note = (
        "Draft a case note.\n\nClient Mdm Lim Siew Hoon, 45, lives with her husband Mr Wong Kok"
        " Leong and her son Master Wong Jun Hao."
    )
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    res = s.sanitise(note, session="sp", seed=3)
    names = _names(res)
    wife, husband, son = (
        names["Mdm Lim Siew Hoon"],
        names["Mr Wong Kok Leong"],
        names["Master Wong Jun Hao"],
    )
    # same convention, different surnames for the spouses; father and son share one
    assert title_token(wife) != title_token(husband), (wife, husband)
    assert title_token(husband) == title_token(son), (husband, son)
    for n in (wife, husband, son):
        assert household_key(n) is not None and household_key(n)[0] == "surname", n


def test_relation_word_fixes_the_convention_of_a_bare_given_name(tmp_path):
    f = SurrogateFactory(5)
    text = "Client Nurul Aini binti Rahmat. Her husband Ridzwan works nights."
    kin = households(text, _spans(text, ["Nurul Aini binti Rahmat", "Ridzwan"]))
    f.name("Nurul Aini binti Rahmat", household=kin["Nurul Aini binti Rahmat"])
    f.name("Ridzwan", gender_hint="male", household=kin["Ridzwan"])
    person = f.persons["ridzwan"]
    assert person.origin == "malay", person
    assert " bin " in person.full, person


def test_title_token_is_shared_only_within_a_household():
    for seed in range(30):
        f = SurrogateFactory(seed)
        people = [
            ("Tan Wei Ling", ("surname", "tan")),
            ("Tan Wei Hui", ("surname", "tan")),
            ("Tan Jun Wei", ("surname", "tan")),
            ("Lee Kok Wai", ("surname", "lee")),
            ("Wong Mei Ling", ("surname", "wong")),
            ("Ng Siew Lan", ("surname", "ng")),
            ("Goh Boon Huat", ("surname", "goh")),
        ]
        out = {o: f.name(o, household=Kin(key=k)) for o, k in people}
        owners: dict[str, set[tuple[str, str]]] = {}
        for o, k in people:
            owners.setdefault(title_token(out[o]).lower(), set()).add(k)
        assert all(len(v) == 1 for v in owners.values()), (seed, out)
        assert len({title_token(out[o]) for o, k in people if k[1] == "tan"}) == 1, out
        fulls = [v.lower() for v in out.values()]
        shorts = [f.persons[o.lower()].short.lower() for o, _ in people]
        assert len(set(fulls)) == len(fulls) and len(set(shorts)) == len(shorts), (seed, out)
        assert f.title_owner[title_token(out["Tan Wei Ling"]).lower()] == ("surname", "tan")


def test_named_father_gives_his_surrogate_given_name_as_the_father_name(tmp_path):
    note = "Client Mdm Aishah binti Karim, 28. Her father Karim lives nearby."
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    res = s.sanitise(note, session="fa", seed=1)
    names = _names(res)
    assert shared_part(names["Mdm Aishah binti Karim"], "malay") == names["Karim"], names
    assert restore(res.text, vault, "fa").text == note


# Restoration


def _household_session(monkeypatch, tmp_path):
    res, vault, _ = _run(monkeypatch, tmp_path, rec5, "dcm_careplan")
    names = _names(res)
    return vault, title_token(names["Ms Tan Wei Ling"]), names


def test_ambiguous_titled_surname_is_restored_and_marked(monkeypatch, tmp_path):
    vault, sur, names = _household_session(monkeypatch, tmp_path)
    # two women of the household share "Ms <surname>": either could be meant
    reply = f"Ms {sur} will attend the review. Mr {sur} will bring the deputy papers."
    r = restore(reply, vault, "s")
    assert r.text == "Ms Tan will attend the review. Mr Tan will bring the deputy papers.", r.text
    assert r.ambiguous_people == [f"Ms {sur}"]  # the brother is the only man: not ambiguous
    lk = leak_check(reply, r, vault, "s", set(), use_presidio=False, use_gliner=False)
    assert lk.passed and lk.ambiguous_people == [f"Ms {sur}"]
    assert lk.event(9).ambiguous_people == [f"Ms {sur}"]
    card = ambiguous_person_flag(reply, r.ambiguous_people)
    assert card is not None and card.severity == "info"
    assert "could be either of two people" in card.reason
    assert card.evidence == f"Ms {sur} will attend the review."
    # a full form names one person and is not marked
    full = names["Ms Tan Wei Hui"]
    r2 = restore(f"{full} will attend.", vault, "s")
    assert r2.text == "Ms Tan Wei Hui will attend." and r2.ambiguous_people == []


def test_ambiguous_person_card_reaches_the_flag_list(monkeypatch, tmp_path):
    note = rec5.use(monkeypatch, "dcm_careplan")
    g = Guard(vault=Vault(tmp_path / "v.sqlite"), ledger=Ledger(tmp_path / "l.jsonl"))
    msgs = [{"role": "user", "content": note["text"]}]
    out = g.outbound(msgs, note["pack"], "amb", seed=7)
    sur = re.search(r"Client Ms (\w+) ", out[4]).group(1)
    res = g.run(
        msgs,
        note["pack"],
        "openai/gpt-4.1-mini",
        session="amb",
        reply_fixture=f"Summary. Ms {sur} attends the centre.",
        seed=7,
    )
    assert res.reply == "Summary. Ms Tan attends the centre."
    card = next(f for f in res.flags if f.label == "AMBIGUOUS_PERSON")
    assert card.evidence == "Ms Tan attends the centre."
    assert "Ms Tan" in card.reason and "could be either of two people" in card.reason
    leak = next(e for e in res.events if e.kind == "leakcheck")
    assert leak.passed and leak.ambiguous_people == [f"Ms {sur}"]
    assert res.ledger_row["leakcheck_detail"]["ambiguous_people"] == [f"Ms {sur}"]
    assert res.decision == "pass"


def test_one_surrogate_for_two_people_is_never_restored(tmp_path):
    vault = Vault(tmp_path / "v.sqlite")
    for original, eid in (("Tan Wei Ling", "NAME:0001"), ("Lee Kok Wai", "NAME:0002")):
        vault.put(Mapping("hb", original, "Soh Mei Ling", "NAME", "surrogate", eid))
    vault.put(Mapping("hb", "Ang Mo Kio", "Pasir Ris", "ESTATE", "surrogate", "E:1"))
    reply = "Soh Mei Ling lives in Pasir Ris."
    r = restore(reply, vault, "hb")
    assert r.text == "Soh Mei Ling lives in Ang Mo Kio.", r.text
    assert r.ambiguous_surrogates == ["Soh Mei Ling"]
    assert r.n_restored == 1
    lk = leak_check(reply, r, vault, "hb", set(), use_presidio=False, use_gliner=False)
    assert not lk.passed and "Soh Mei Ling" in lk.unrestored


def test_short_and_full_forms_of_one_person_still_restore(tmp_path):
    vault = Vault(tmp_path / "v.sqlite")
    vault.put(Mapping("sp", "Suriaty", "Farah", "NAME", "surrogate", "NAME:1"))
    vault.put(Mapping("sp", "Suriati", "Farah", "NAME", "surrogate", "NAME:2"))
    assert restore("Farah called.", vault, "sp").text == "Suriaty called."


# Across turns


def test_household_persists_across_turns(tmp_path):
    vault = Vault(tmp_path / "v.sqlite")
    pack = load_pack("disability")
    s1 = Sanitiser(vault, pack, use_presidio=False, use_gliner=False)
    t1 = s1.sanitise("Client Ms Tan Wei Ling, 42, attends the centre.", session="mt", seed=4)
    first = _names(t1)["Ms Tan Wei Ling"]
    s2 = Sanitiser(vault, pack, use_presidio=False, use_gliner=False)
    t2 = s2.sanitise(
        "Her sister Ms Tan Wei Hui and Mr Lee Kok Wai came to the review.", session="mt", seed=4
    )
    names = _names(t2)
    sister, other = names["Ms Tan Wei Hui"], names["Mr Lee Kok Wai"]
    assert title_token(sister) == title_token(first), (first, sister)
    assert sister != first and sister.split()[-2:] != first.split()[-2:]
    # an unrelated person does not take the household's surname
    assert title_token(other) != title_token(first), (first, other)
    back = restore(f"{first} and {sister} met {other}.", vault, "mt").text
    assert back == "Ms Tan Wei Ling and Ms Tan Wei Hui met Mr Lee Kok Wai.", back
