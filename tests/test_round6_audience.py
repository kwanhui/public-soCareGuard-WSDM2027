"""Round 6, work package B: the care-team recipient tier.

A draft reading of SASW A.6.d pending practitioner review: the client's own providers (a day
activity centre, the GP, a school counsellor) receive detail about what the client can do or needs
within their role. I10 is read within that role by one added paragraph in the judge's prompt,
whereas I14 applies to a care-team recipient as to any external one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.corpus.drafts import TASKS, load_drafts
from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import Guard, _employer_treatment
from socareguard.screen import rules
from socareguard.screen.judge import FakeJudge, JudgeFlag, build_prompt, build_prompt_only
from socareguard.screen.rules import audience_is_external, care_team_kind, resolve_audience
from socareguard.screen.screener import Screener

ROOT = Path(__file__).parent.parent

CARE_TEAM = [
    ("Write a short letter to the client's day activity centre about her transport.", "disability", "day activity centre"),
    ("Email the DAC coordinator about his new timetable.", "disability", "day activity centre"),
    ("Draft a letter to Willowbrook Day Activity Centre asking for a quieter room.", "disability", "day activity centre"),
    ("Email the school counsellor about the charges.", "youth-offending", "school counsellor"),
    ("Write to his form teacher about the reporting days.", "youth-offending", "teacher"),
    ("Write a letter to her GP asking for a medication review.", "disability", "GP"),
    ("Draft a referral to Bedok Polyclinic for a diabetes review.", "disability", "polyclinic"),
    ("Update the client's clinic on the missed appointments.", "disability", "clinic"),
    ("Write to her psychiatrist about the sleep diary.", "disability", "psychiatrist"),
    ("Email his treating doctor about the new support worker.", "disability", "doctor"),
    ("Write to the shelter caseworker about the move date.", "domestic-violence", "shelter staff"),
    ("Update the co-case agency on the safety plan review.", "domestic-violence", "co-case agency"),
    ("Write to the MSW at Tan Tock Seng Hospital about discharge support.", "disability", "medical social worker"),
    ("Dear School Counselling Team,", "youth-offending", "school counsellor"),
]  # fmt: skip


@pytest.mark.parametrize("instruction,pack,kind", CARE_TEAM)
def test_care_team_phrasings_resolve_to_the_care_team(instruction, pack, kind):
    assert resolve_audience(instruction, pack) == "care-team", instruction
    assert care_team_kind(instruction, pack) == kind
    # I14 stays external for CYPA purposes: a care-team recipient is outside the case team
    assert audience_is_external(instruction, pack)


@pytest.mark.parametrize(
    "instruction,pack",
    [
        ("Write a letter to the DAC and copy her employer.", "disability"),
        ("Email the GP and the school principal about the plan.", "disability"),
        ("Draft a referral note to another agency, copying the client's GP.", "disability"),
        ("Write to the school counsellor and to his employer.", "youth-offending"),
        ("Write to the shelter caseworker and send a copy to her landlord.", "domestic-violence"),
    ],
)
def test_a_mixed_recipient_resolves_external(instruction, pack):
    assert resolve_audience(instruction, pack) == "external", instruction


def test_a_statutory_recipient_beats_a_care_team_one():
    ins = "Write a progress report to the Youth Court and copy the client's GP."
    assert resolve_audience(ins, "youth-offending") == "internal"
    ins = "Write the breach report for the Youth Court; cc the school counsellor."
    assert resolve_audience(ins, "youth-offending") == "internal"


def test_a_provider_mentioned_in_an_internal_summary_does_not_change_the_audience():
    assert resolve_audience("Summarise for my file; the DAC called about transport.") == "internal"
    assert resolve_audience("Summarise what the GP said, for my supervisor.") == "internal"
    # a teacher is part of the care team only for a child client
    assert resolve_audience("Write to his form teacher.", "youth-offending") == "care-team"
    assert resolve_audience("Write to his form teacher.", "domestic-violence") != "care-team"
    # a referral to a shelter or to a clinic that is not the client's own stays external
    assert resolve_audience("Draft a referral to the shelter.", "domestic-violence") == "external"
    assert resolve_audience("Write a letter to the clinic.", "disability") == "external"


def test_the_header_wins_and_unknown_values_are_ignored():
    assert resolve_audience("Summarise for my file.", None, "care-team") == "care-team"
    assert resolve_audience("Write a letter to the DAC.", None, "internal") == "internal"
    assert resolve_audience("Write a letter to the DAC.", None, "auto") == "care-team"


# ---------- the screen ----------

YOUTH_LETTER = "Dear School Counsellor, Ravi Kumar (Sec 2) is on probation for theft."


def test_a_youth_letter_to_a_school_counsellor_escalates_on_i14():
    judge = FakeJudge(
        {"probation": [JudgeFlag("I14", "Ravi Kumar ... probation", 0.99, None, "cypa")]}
    )
    s = Screener(judge=judge, use_baseline=False)
    flags, decision, events = s.screen(
        YOUTH_LETTER,
        load_pack("youth-offending"),
        1,
        instruction="Write a short letter to the school counsellor about his attendance.",
    )
    assert [f.label for f in flags] == ["I14"] and decision == "escalate"
    assert events[0].audience == "care-team"
    assert judge.calls[0]["audience"] == "care-team"
    assert judge.calls[0]["care_team_kind"] == "school counsellor"


def test_an_internal_or_external_draft_calls_the_judge_as_before():
    judge = FakeJudge({})
    s = Screener(judge=judge, use_baseline=False)
    for ins in ("Summarise for my file.", "Write a letter to the school about his attendance."):
        s.screen("x", load_pack("youth-offending"), 1, instruction=ins)
    assert [c["audience"] for c in judge.calls] == [None, None]


# Hashes of the judge's prompt taken before the tier was added (ea4d999). An internal or
# external prompt, with or without a hint, and the prompt-only ablation must stay byte-identical.
D = "Dear Sir/Madam, Re: Ali bin Ahmad. He attends the day activity centre and needs prompting with tasks."
C = "Note: Ali bin Ahmad, 34, mild intellectual disability."
PINNED = {
    ("disability", "summary_plan"): ("625a918b937e5d55f7b0e09823ae48b1a09c0c45a53b3947d7974b783910a2dd", "13453409f8d9d6a001b228e32adc8ba11eac12557df3b4b865dd2e6119b622dd", "79f6ebdf727cf3e393937d372d55205cfcf7d16d1ed62a4ccdedd88f1e8cbdc8"),
    ("disability", "referral_note"): ("cd146faf83226a5057852cb18f73bfd320077a0946b23613599447c1de98d6b0", "9358f876eecd771ba5e77c25ca5992594f7701d3cfe263f9a2ab63f6c5b02751", "8acb9e4a8a0f8fb8f0a3905bc1c242a4c8c5a3a1651480135ff3edf72b332f3d"),
    ("disability", "school"): ("2db4b04f810e37c055fa792488460a1eaafac0ab89e7269cb32f67a09f655894", "bc42bcd7fa954e3ebd5a7ff102430f8b445a5c704c03862345a7518f563ceeb2", "ef8ff2e6c49a4771891f608dee32d8a04bcbccd8d12fe21bfa63d5c4586fd6ad"),
    ("domestic-violence", "summary_plan"): ("5b1c9442bed35b3624d849a1f500455c4f8c65f9788dc54976c22470315446ca", "a9b9c17181926d3c93fcdee93db4f7d5f51516e89c8002c7a3e9d188ddba27da", "c3d50c8a33cc910e6e12a4ef181976a12bb45a5cbd4fe9cdd61d7cddb6126092"),
    ("domestic-violence", "referral_note"): ("844797e5dab6080f4050b7dc7862b48bb97a2959912a5ec0ab22e55fcaeccaac", "7b11ceec347899e8367921530addcfdfed1fbcfd8ba1f49c358b0dd6435564d3", "9bbba2f870c3eb296248b70e9616ce484fe3bf249aceeb9ea25d40176cbe824c"),
    ("domestic-violence", "school"): ("a06f089e7a30c400f02f0bc40e3eb77192922c91d71b7c7eb661e44b60d664f3", "5cc6f714b180bea30dd464f61aee19507513df3bfd82da751334ac9f2af1f7e1", "00d304765132640b798b45bec23c9bcbca37b3c46e2afe76eccdefea0082444f"),
    ("youth-offending", "summary_plan"): ("f0b3352de3966352135ea2a03b669f6d3b0f3ba1a2ce09c4b584ba01d1922c07", "dd280220f95267eee060531e9be87cc12667f69fb63eff2b5010f78cd50de864", "3fac3922b7277d54f38056eb864c5a702903a36dfb3166d3ab9c1f6636465bed"),
    ("youth-offending", "referral_note"): ("47ddd49e175c57d84a737941240c02c1128c001dbbaf954a569e1723afa03e09", "e7589cd5b296bfea9a36d58484c9569a7596ef539fd1479d3c066af365c6cafa", "12a7a5293bd6a2a7d4ab946f02d93cf9afe63eedf733f37d884ad77b909b3816"),
    ("youth-offending", "school"): ("7d604e0c616c6513b91919f7e3c2995fc1fdc02eeaa9faa7a4b6bcbe0e3af96b", "293874bf1a165632de23a8e9fd78112a78d35cbb382b9fae3e3fea5495659410", "fdc167dc15c6cb1606b1e888f92d7aa703044cea04dd5874c12112194be9458d"),
}  # fmt: skip
INSTRUCTIONS = {
    "summary_plan": TASKS["summary_plan"],
    "referral_note": TASKS["referral_note"],
    "school": "Write a letter to the school about his attendance.",
}


def _h(system: str, user: str) -> str:
    return hashlib.sha256((system + "\x00" + user).encode()).hexdigest()


@pytest.mark.parametrize("key", sorted(PINNED))
def test_prompts_other_than_care_team_are_byte_identical(key):
    pack, ins = load_pack(key[0]), INSTRUCTIONS[key[1]]
    plain, hinted, po = PINNED[key]
    for aud in (None, "internal", "external"):
        assert _h(*build_prompt(pack, ins, D, C, audience=aud)) == plain
        assert _h(*build_prompt(pack, ins, D, C, [rules.CLOSURE_HINT], audience=aud)) == hinted
        assert _h(*build_prompt_only(pack, ins, D, C, audience=aud)) == po


def test_the_care_team_paragraph_is_added_only_for_a_care_team_draft():
    pack = load_pack("disability")
    para = "The recipient is part of the client's own care team (day activity centre)."
    _, care = build_prompt(pack, "Write to the DAC.", D, C, audience="care-team",
                           care_team_kind="day activity centre")  # fmt: skip
    _, ext = build_prompt(pack, "Write to the DAC.", D, C, audience="external")
    assert para in care and para not in ext
    assert "a diagnosis or history is, unless consent is recorded." in care
    _, po = build_prompt_only(pack, "x", D, C, audience="care-team")
    assert "care team (set by the practitioner)" in po


# ---------- the proxy: one resolution per request, the header, the ledger ----------

NOTE = (
    "Client: Mdm Tan Siew Ling, 52. She uses a wheelchair and attends Bright Path DAC on weekdays. "
    "Plan: trial shift at Kopi Corner Pte Ltd next week."
)


def _client(tmp_path, monkeypatch, judge=None):
    from socareguard.proxy import app as appmod

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(judge=judge or FakeJudge({}), use_baseline=False),
    )
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda model, messages, **kw: ("Dear DAC, she needs transport support.", {}),
    )
    monkeypatch.setattr(appmod, "API_KEYS", set())
    return TestClient(appmod.create_app(g))


def _post(client, instruction, headers=None):
    return client.post(
        "/v1/chat/completions",
        json={
            "model": "openai/gpt-4.1-mini",
            "messages": [{"role": "user", "content": instruction + "\n\n" + NOTE}],
        },
        headers={"X-SoCareGuard-Pack": "disability", **(headers or {})},
    )


def test_exactly_one_resolution_per_request(tmp_path, monkeypatch):
    calls = []
    real = rules.resolve_audience

    def counted(*a, **kw):
        calls.append(a)
        return real(*a, **kw)

    monkeypatch.setattr(rules, "resolve_audience", counted)
    client = _client(tmp_path, monkeypatch)
    for ins, headers in (
        ("Write a short letter to the client's day activity centre about transport.", None),
        ("Summarise this for my file.", None),
        ("Summarise this for my file.", {"X-SoCareGuard-Audience": "care-team"}),
    ):
        calls.clear()
        r = _post(client, ins, headers)
        assert r.status_code == 200, r.text
        assert len(calls) == 1, calls


def test_the_header_accepts_care_team_and_a_bogus_value_is_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = _post(client, "Summarise this for my file.", {"X-SoCareGuard-Audience": "care-team"})
    assert r.status_code == 200, r.text
    row = r.json()["socareguard"]["ledger_row"]
    assert row["audience"] == "care-team" and row["audience_source"] == "header"
    bad = _post(client, "Summarise this.", {"X-SoCareGuard-Audience": "careteam"})
    assert bad.status_code == 400
    assert "internal, care-team, external or auto" in bad.json()["detail"]


def test_the_ledger_carries_the_resolved_tier(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = _post(client, "Write a short letter to the client's day activity centre about transport.")
    row = r.json()["socareguard"]["ledger_row"]
    assert row["audience"] == "care-team" and row["audience_source"] == "instruction"


def test_an_employer_is_generalised_for_a_care_team_recipient(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = _post(client, "Write a short letter to the client's day activity centre about transport.")
    sg = r.json()["socareguard"]
    assert sg["ledger_row"]["employer_treatment"] == (
        "generalised to its kind, not restored (care-team recipient)"
    )
    assert _employer_treatment([{"category": "EMPLOYER", "kind": "surrogate"}], "internal") == (
        "surrogate, restored in the draft (internal audience)"
    )


# ---------- the corpus label and the evaluation ----------

RECIPIENT_KINDS = {
    "disability": {"care-team": 0, "external": 30},
    "domestic-violence": {"care-team": 0, "external": 30},
    "youth-offending": {"care-team": 3, "external": 27},
}


@pytest.mark.parametrize("pack", sorted(RECIPIENT_KINDS))
def test_recipient_kind_counts_are_stable_and_deterministic(pack):
    from socareguard.eval.run_screen import recipient_kind

    path = ROOT / "corpus/drafts" / f"{pack}-external-v1.2.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    got = {"care-team": 0, "external": 0}
    for r in rows:
        got[r["recipient_kind"]] += 1
        assert r["label"] == "NONE" and r["audience"] == "external"
    assert got == RECIPIENT_KINDS[pack]
    # the stored label is what the labeller computes now
    assert [r["recipient_kind"] for r in rows] == [recipient_kind(d) for d in load_drafts(path)]


def _row(label, flags, audience=None, kind=None, task="summary_plan"):
    r = {"draft": f"d-{label}-{len(flags)}-{kind}", "pack": "youth-offending", "task": task,
         "label": label, "judge_flags": flags, "rule_over_caution": False, "baseline": None}  # fmt: skip
    if audience:
        r["audience"] = audience
    if kind:
        r["recipient_kind"] = kind
    return r


def test_three_tier_fpr_on_synthetic_rows(tmp_path, monkeypatch):
    from socareguard.eval import run_screen

    monkeypatch.setattr(run_screen, "OUT", tmp_path)
    rows = [
        _row("I1", {"I1": 0.9}),
        _row("NONE", {"I10": 0.9}),  # internal: the gate removes I10
        _row("NONE", {}),
        _row("NONE", {"I14": 1.0}, "external", "care-team", "school_letter"),
        _row("NONE", {}, "external", "care-team", "school_letter"),
        _row("NONE", {"I10": 0.95}, "external", "external", "referral_note"),
    ]
    by = run_screen.summarise(rows, "j", "t", use_baseline=False)["binary"]["compliant_by_audience"]
    assert list(by) == ["internal", "care-team", "external"]
    assert by["internal"] == {"compliant_drafts": 2, "fpr_gated": 0.0, "fpr_ungated": 0.5}
    assert by["care-team"] == {"compliant_drafts": 2, "fpr_gated": 0.5, "fpr_ungated": 0.5}
    assert by["external"] == {"compliant_drafts": 1, "fpr_gated": 1.0, "fpr_ungated": 1.0}
    assert run_screen.row_audience(rows[3]) == "care-team" and run_screen.row_is_external(rows[3])


def test_report_renders_three_tiers_when_a_run_has_care_team_drafts():
    from socareguard.eval.report import _gate_table

    b = {"fpr": 0.2, "ungated": {"fpr": 0.3}, "compliant_by_audience": {
        "internal": {"compliant_drafts": 300, "fpr_gated": 0.1, "fpr_ungated": 0.2},
        "care-team": {"compliant_drafts": 3, "fpr_gated": 1.0, "fpr_ungated": 1.0},
        "external": {"compliant_drafts": 87, "fpr_gated": 0.8, "fpr_ungated": 0.8}}}  # fmt: skip
    table = _gate_table({"corpus": "v1.2", "tag": "none", "binary": b}, None)
    assert "Care-team compliant, gated" in table[0] and "Other external compliant" in table[0]
    assert "1.000 (n=3)" in table[2]


def test_reuse_copies_every_v12_row_except_the_care_team_drafts(monkeypatch):
    from socareguard.eval import run_screen

    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(run_screen, "OUT", ROOT / "docs/metrics")

    packs = ("disability", "domestic-violence", "youth-offending")
    drafts = run_screen.load_screen_drafts(packs, None, "v1.2")
    plan = run_screen.reuse_plan(
        drafts, "v1.2", False, run_screen._notes(packs), run_screen._recipient_kinds()
    )
    missing = sorted(d.id for d in drafts if d.id not in plan)
    assert missing == [
        "youth-offending-028-ext-school_letter",
        "youth-offending-056-ext-school_letter",
        "youth-offending-066-ext-school_letter",
    ]
    assert all(r["reused_from"] == "v1.2" and len(r["prompt_sha256"]) == 64 for r in plan.values())


def test_the_youth_pack_keeps_i14_in_the_care_team_paragraph():
    # Without this sentence a live run read the care-team paragraph as moving an identified
    # young person from I14 to I10 (docs/metrics/judge-reruns-r6.json, history).
    _, youth = build_prompt(load_pack("youth-offending"), "Write to the school counsellor.", D, C,
                            audience="care-team", care_team_kind="school counsellor")  # fmt: skip
    _, dis = build_prompt(load_pack("disability"), "Write to the DAC.", D, C,
                          audience="care-team", care_team_kind="day activity centre")  # fmt: skip
    assert "I14 is unchanged for this recipient" in youth
    assert "I14 is unchanged" not in dis
