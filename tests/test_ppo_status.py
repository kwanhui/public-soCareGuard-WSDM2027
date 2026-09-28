"""Round-1 DV advocate F4 (2026-09-28): a PPO hearing date and venue survived the status-only rule."""

import re
from pathlib import Path

from socareguard.outbound.generalise import generalise_attribute
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack

DV_3 = (
    "Write a letter to the school principal to arrange a safety plan for pickup, since the mother"
    " is worried the father will turn up.\n\n"
    "Case note, 21 Sep 2026. Client Lakshmi d/o Rajan, 36, case ref FSC-2026-0921. Lakshmi's two"
    " children attend Damai Primary School. She has a protection order against her husband Arun"
    " s/o Subramaniam, hearing at the Family Justice Courts on 3 Oct 2026. She is worried he will"
    " show up at the school gate; the children's pickup authorisation has been changed to remove"
    " him."
)
DV_1_PPO = (
    "Contact note, 15 Sep 2026. A PPO was filed on 12 Sep; hearing set for 6 Oct 2026 at the Family"
    " Justice Courts. Client is coping."
)


def _sanitise(tmp_path: Path, pack_id: str, note: str, session: str = "r1"):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack_id), use_presidio=False, use_gliner=False)
    return s.sanitise(note, session=session, seed=1), vault


def _sentence(text: str, start: str) -> str:
    i = text.index(start)
    return text[i : text.index(".", i)]


def test_ppo_status_only_drops_hearing_date_and_venue(tmp_path: Path):
    for note in (DV_3, DV_1_PPO):
        out, _ = _sanitise(tmp_path, "domestic-violence", note, session=str(hash(note)))
        text = out.text
        assert not re.search(r"\b(?:3|6) Oct\b", text), text
        assert "Family Justice" not in text, text
        assert "protection order" in text, text
    got = generalise_attribute(
        "ppo",
        "She has a protection order against her husband, hearing at the Family Justice Courts on"
        " 3 Oct 2026",
        "status_only",
        "domestic-violence",
    )
    assert "Oct" not in got and "Family Justice" not in got and "protection order" in got, got


def test_ppo_not_filed_is_never_pending():
    """Round 1, dv-9 outbound: "Latifah has not filed a PPO" left as "A protection order
    application is pending"."""
    got = generalise_attribute(
        "ppo",
        "Latifah has not filed a PPO and says things have been quiet",
        "status_only",
        "domestic-violence",
    )
    # round 6 acceptance F3: the rule stops at the clause boundary and keeps the second clause
    assert got == (
        "no protection order application is on record and Latifah says things have been quiet"
    ), got
    for text in (
        "She has not applied for a PPO",
        "She never filed a PPO",
        "She is yet to apply for a PPO",
    ):
        got = generalise_attribute("ppo", text, "status_only", "domestic-violence")
        assert got == "no protection order application is on record", (text, got)


def test_a_bare_negative_stays_negative():
    """Round 3, WSDM N7: "No PPO yet" left as "Protection order status recorded", and "No PPO in
    place" would have read as an order in place."""
    for text in ("No PPO yet", "no PPO in place", "No protection order at present"):
        got = generalise_attribute("ppo", text, "status_only", "domestic-violence")
        assert got.startswith("no protection order") and got.endswith("is on record"), (text, got)
    got = generalise_attribute(
        "ppo", "No PPO yet, she is considering applying", "status_only", "domestic-violence"
    )
    assert got == "no protection order is on record; one is being considered", got
    got = generalise_attribute("ppo", "She no longer has a PPO", "status_only", "d")
    assert "no protection order is on record" != got, got
