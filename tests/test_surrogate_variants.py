"""Round-1 DV advocate F5 (2026-09-28): one person received two surrogates in one note, and a
four-token titled name left its last token behind."""

import re
from pathlib import Path

from socareguard.inbound.restore import restore
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.surrogates import SurrogateFactory
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack

DV_5 = (
    "Draft a referral letter to the programme intake coordinator for this client.\n\n"
    "Referral note, 23 Sep 2026. Client (referred party): Mr Jason Lim Wei Kiat, 40, case ref"
    " FSC-2026-0923. Jason has admitted to physically assaulting his wife Serene Tan Bee Choo on"
    " two occasions in the past year. Serene and their daughter (age 7) are currently at an"
    " undisclosed location for safety. A protection order is in place. Jason has agreed to attend"
    " the programme as a condition and wants to know if this will help him see his daughter again."
)

WSDM_B2 = (
    "Draft a short letter to the HDB branch officer asking to renew Mr Lee's rental tenancy,"
    " explaining his situation.\n\n"
    "Review, 4 Sep 2026. Client Lee Kok Wai, NRIC S6543210H, 58, lives alone at Blk 88 Toa Payoh"
    " Lorong 4 #03-221. Diagnosis: schizophrenia, stable on clozapine, IMH follow-up. Capacity"
    " fluctuates: today he could not hold the options for the tenancy renewal across the session;"
    " last month he could. His sister Lee Mei Ling is his court-appointed deputy for property"
    " matters. He receives ComCare $600 per month. He wants to stay in the flat. Plan: liaise with"
    " the HDB officer on the tenancy renewal with the deputy present."
)


def _sanitise(tmp_path: Path, pack_id: str, note: str, session: str = "r1"):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack_id), use_presidio=False, use_gliner=False)
    return s.sanitise(note, session=session, seed=1), vault


def _sentence(text: str, start: str) -> str:
    i = text.index(start)
    return text[i : text.index(".", i)]


def test_one_person_one_surrogate_across_name_variants(tmp_path: Path):
    out, vault = _sanitise(tmp_path, "domestic-violence", DV_5)
    text = out.text
    names = {h.text: new for h, new, kind in out.replacements if h.category == "NAME"}
    for token in ("Jason", "Lim", "Wei", "Kiat"):
        assert not re.search(rf"\b{token}\b", text), (token, text)
    full = names["Mr Jason Lim Wei Kiat"]
    given = names["Jason"]
    # the given name alone is the given name of the same surrogate
    assert given in full.split(), (full, given)
    # a reply that uses either form restores to the one person
    back = restore(f"{full} and {given}", vault, "r1").text
    assert back == "Mr Jason Lim Wei Kiat and Jason", back


def _core(name: str) -> set[str]:
    skip = {"Mdm", "Mr", "Encik", "binti", "bin", "bte"}
    return {t for t in name.split() if t not in skip}


def test_titled_malay_names_share_one_surrogate(tmp_path: Path):
    note = (
        "Client Mdm Rosnah binti Karim, 30. Rosnah bte Karim was seen with her son. Mdm Rosnah"
        " said her husband Encik Salleh bin Kassim works nights. Salleh did not attend."
    )
    out, _ = _sanitise(tmp_path, "domestic-violence", note)
    names = {h.text: new for h, new, kind in out.replacements if h.category == "NAME"}
    for person, full_key in (
        ("Rosnah", "Mdm Rosnah binti Karim"),
        ("Salleh", "Encik Salleh bin Kassim"),
    ):
        full = _core(names[full_key])
        variants = [v for k, v in names.items() if person in k]
        assert len(variants) >= 2, names
        for v in variants:
            assert _core(v) <= full, (person, v, names[full_key])


def test_a_surname_shared_by_two_people_follows_the_title():
    f = SurrogateFactory(7)
    him = f.name("Tan Wei Ming")
    her = f.name("Tan Mei Ling")
    assert him.split()[0] != her.split()[0]
    assert f.name("Mr Tan") == f"Mr {him.split()[0]}"
    assert f.name("Mdm Tan") == f"Mdm {her.split()[0]}"
    assert f.name("Wei Ming") == him and f.name("Tan Wei Ming") == him


def test_a_later_turn_keeps_the_person(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    first = s.sanitise("Client Mr Jason Lim Wei Kiat, 40, attended.", session="t", seed=1)
    full = next(new for h, new, _ in first.replacements if h.text == "Mr Jason Lim Wei Kiat")
    second = s.sanitise("Mr Lim said that Jason Lim will attend.", session="t", seed=1)
    forms = {h.text: new for h, new, _ in second.replacements if h.category == "NAME"}
    assert forms, second.text
    for v in forms.values():
        assert set(v.replace("Mr ", "").split()) <= set(full.replace("Mr ", "").split()), (
            full,
            forms,
        )


def test_titled_form_followed_by_the_full_name_stays_two_spans():
    from socareguard.detect.sg import find_title_names

    assert [h.text for h in find_title_names("Mr Jason Lim Wei Kiat, 40")] == [
        "Mr Jason Lim Wei Kiat"
    ]
    assert [h.text for h in find_title_names("concern: Mr Ong Ong Kian Hock, male")] == ["Mr Ong"]


def test_father_name_spellings_share_one_surrogate_father_name(tmp_path: Path):
    """Round 6: "bin", "binti", "binte" and "bte" before the same father-name are one household.
    The siblings share a surrogate father-name; the spouse keeps his own."""

    def shared_part(name: str, _origin: str) -> str | None:
        m = re.search(r"\b(?:bin|binti|binte|bte)\s+(.+)$", name)
        return m.group(1) if m else None

    note = (
        "Client Mdm Nurul Aini bte Rahmat, 34. Her brother Encik Hafiz bin Rahmat and her sisters"
        " Cik Siti Aminah binte Rahmat and Mdm Rosnah binti Rahmat help at home. Her husband"
        " Encik Salleh bin Kassim works nights."
    )
    out, vault = _sanitise(tmp_path, "domestic-violence", note, session="bte")
    names = {h.text: new for h, new, kind in out.replacements if h.category == "NAME"}
    sibs = [
        "Mdm Nurul Aini bte Rahmat",
        "Encik Hafiz bin Rahmat",
        "Cik Siti Aminah binte Rahmat",
        "Mdm Rosnah binti Rahmat",
    ]
    fathers = {shared_part(names[n], "malay") for n in sibs}
    assert len(fathers) == 1 and None not in fathers, names
    assert len({names[n] for n in sibs}) == 4, names
    assert shared_part(names["Encik Salleh bin Kassim"], "malay") not in fathers, names
    assert "Rahmat" not in out.text
    assert restore(out.text, vault, "bte").text == note
