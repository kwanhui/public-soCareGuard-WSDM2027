"""Round-1 review finding F1 (2026-09-28): the DV disclosure rule turned a negated assessment and a
neighbour's report into client disclosures and replaced the whole assessment sentence. Each
sub-clause is now generalised on its own, with its polarity."""

from pathlib import Path

from socareguard.outbound.generalise import generalise_attribute
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack

WSDM_11 = (
    "Summarise this home visit for my own case record and list two next steps.\n\n"
    "Home visit, 3 Sep 2026. Client Mdm Siti Nurhaliza binti Rahman, NRIC S8123456C, 38, case ref"
    " FSC-2026-0412, Blk 512 Bedok North Street 3 #07-119, Singapore 460512, hp 91234567. Two"
    " children: Aisyah (9, Damai Primary School) and Irfan (5). Siti said her husband Razak bin"
    " Osman 'always scold until I cannot tahan lah, but he never hit me one'. She denies any"
    " physical violence and has not applied for a PPO. Neighbour reported shouting last week. Siti"
    " works part-time at a bakery in Tampines. Assessment: emotional abuse indicators present, no"
    " disclosed physical violence, client not ready for shelter. Plan: safety planning, follow up"
    " in two weeks."
)


def _sanitise(tmp_path: Path, pack_id: str, note: str, session: str = "r1"):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack_id), use_presidio=False, use_gliner=False)
    return s.sanitise(note, session=session, seed=1), vault


def _sentence(text: str, start: str) -> str:
    i = text.index(start)
    return text[i : text.index(".", i)]


def test_dv_negation_and_third_party_report_keep_their_polarity(tmp_path: Path):
    out, _ = _sanitise(tmp_path, "domestic-violence", WSDM_11)
    text = out.text
    assessment = _sentence(text, "Assessment:")
    assert "Disclosed family violence" not in assessment and "disclosed family" not in assessment
    assert "no physical violence disclosed" in assessment, assessment
    # the assessment and the readiness statement survive
    assert "client not ready for shelter" in assessment, assessment
    assert "emotional" in assessment, assessment
    assert "Denied physical violence" in text, text
    assert "a third-party report of possible family violence" in text.lower(), text
    assert text.count("isclosed family violence") == 0, text


def test_dv_statement_polarity_cases():
    cases = [
        ("She denies any physical violence", "denied physical violence"),
        ("he never hit me one", "denied physical violence"),
        ("no disclosed physical violence", "no physical violence disclosed"),
        (
            "Neighbour reported shouting last week",
            "a third-party report of possible family violence",
        ),
        ("Her teacher said the boy saw his father hit his mother", "a third-party report"),
        ("She said her husband slapped her twice", "disclosed physical violence by her husband"),
        (
            "She said her husband hit her last Friday, no injuries seen",
            "physical violence by her husband, no visible injury noted",
        ),
    ]
    for text, expected in cases:
        got = generalise_attribute(
            "dv_disclosure", text, "keep_event_drop_specifics", "domestic-violence"
        )
        assert expected in got, (text, got)
        assert not ("denied" in expected and "disclosed" in got), (text, got)


def test_a_kept_sub_clause_never_carries_another_attribute():
    """Full-corpus check after the round-1 fix: a sub-clause kept as written must not carry a
    safety plan, a protection order or a diagnosis past its own rule."""
    for key, rule, text, gone in (
        (
            "dv_disclosure",
            "keep_event_drop_specifics",
            "Client disclosed that her partner hit her, and has an existing PPO in place obtained after the incident",
            "existing PPO",
        ),
        (
            "dv_disclosure",
            "keep_event_drop_specifics",
            "She said he threatened her, agreed a contingency safety plan with a code word",
            "code word",
        ),
        (
            "capacity",
            "status_only",
            "Capacity for money matters is in question, diagnosed with mild intellectual disability",
            "intellectual disability",
        ),
    ):
        got = generalise_attribute(key, text, rule, "domestic-violence")
        assert gone not in got, (text, got)
