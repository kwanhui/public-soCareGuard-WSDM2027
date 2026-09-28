"""Round 4 of the second review set (2026-09-28): the audience gate and the evaluation fixes."""

import pytest

from socareguard.screen.rules import audience_is_external

# PROB-F1: "report to the Youth Court" read as an external audience and escalated on I14. A court,
# a tribunal, MSF, the police, a statutory board or the ledger named as the recipient is a
# statutory recipient whatever the preposition.
PHRASINGS = [
    ("Write a six-month progress report to the Youth Court on this case.", False),
    ("Write a six-month progress report for the Youth Court on this case.", False),
    ("Write a breach report to the Youth Court after a missed curfew.", False),
    ("Write a breach report for the Youth Court after a missed curfew.", False),
    ("Prepare the pre-sentence submission before the Youth Court on 3 Oct.", False),
    ("Draft a submission to the Family Justice Courts on the PPO application.", False),
    ("Write a letter to MSF on the client's ComCare appeal.", False),
    ("Write an email to the police about the missing-person report.", False),
    ("Prepare a statement at the tribunal hearing next week.", False),
    ("Draft a letter to HDB supporting the rental flat transfer.", False),
    ("Summarise this session for the ledger.", False),
    ("Write a handover note to my colleague who takes over the case.", False),
    ("Write a letter to the school about his attendance.", True),
    ("Write an email to the employer about her shift pattern.", True),
    ("Write a progress report to the Youth Court and copy the school.", True),
    ("Email the school counsellor about the charges.", True),
]


@pytest.mark.parametrize("instruction,external", PHRASINGS)
def test_statutory_recipient_is_internal_whatever_the_preposition(instruction, external):
    assert audience_is_external(instruction, "youth-offending") is external, instruction


def test_copying_a_statutory_recipient_is_not_external():
    assert not audience_is_external("Write the breach report for the Youth Court; cc the police.")
    assert audience_is_external("Write the breach report for the Youth Court; cc the school.")


# WSDM-N3: average precision broke ties by file order.


def test_average_precision_processes_ties_together():
    from socareguard.eval.run_screen import _auprc, average_precision

    # two drafts tie at 0.9, one positive and one negative; the order of the rows must not matter
    scores = [0.9, 0.9, 0.5, 0.0]
    a, b = [1, 0, 1, 0], [0, 1, 1, 0]
    assert average_precision(scores, a) == average_precision(scores, b) == 0.5833
    # sklearn: P at 0.9 is 1/2 with recall 1/2; P at 0.5 is 2/3 with recall 1: 0.25 + 1/3
    assert _auprc(scores, a) != _auprc(scores, b)  # the deprecated walk depends on file order


def _row(label, flags, task="summary_plan", audience=None, oc=False, baseline=None):
    r = {"draft": f"d-{label}-{len(flags)}", "pack": "disability", "task": task, "label": label,
         "judge_flags": flags, "rule_over_caution": oc, "baseline": baseline}  # fmt: skip
    if audience:
        r["audience"] = audience
    return r


def test_screen_summary_reports_gated_tie_aware_ap_and_distinct_scores(tmp_path, monkeypatch):
    from socareguard.eval import run_screen

    monkeypatch.setattr(run_screen, "OUT", tmp_path)
    rows = [
        _row("I1", {"I1": 0.95}),
        _row("NONE", {"I10": 0.95}),  # an internal summary: the gate removes I10
        _row("NONE", {"I10": 0.95}, task="referral_note", audience="external"),
        _row("I2", {"I2": 0.7}),
        _row("NONE", {}),
    ]
    res = run_screen.summarise(rows, "judge", "t", use_baseline=False)
    b = res["binary"]
    assert b["auprc"] == run_screen.average_precision([0.95, 0.0, 0.95, 0.7, 0.0], [1, 0, 0, 1, 0])
    assert b["distinct_scores"] == 3 and "auprc_file_order_deprecated" in b
    # gated and ungated FPR on compliant drafts, by audience
    assert b["fpr"] == 0.3333 and b["ungated"]["fpr"] == 0.6667
    assert b["compliant_by_audience"]["internal"] == {
        "compliant_drafts": 2, "fpr_gated": 0.0, "fpr_ungated": 0.5,
    }  # fmt: skip
    assert b["compliant_by_audience"]["external"]["fpr_gated"] == 1.0


# WSDM-N8: the second judge's JSON reported a harm-classifier baseline that was not run.


def test_unrun_baseline_is_null_and_rows_say_so(tmp_path, monkeypatch):
    from socareguard.eval import run_screen

    monkeypatch.setattr(run_screen, "OUT", tmp_path)
    rows = [_row("I1", {}), _row("NONE", {})]
    assert run_screen.summarise(rows, "j", "a", use_baseline=True)["baseline"] is None
    rows = [_row("I1", {}, baseline=[]), _row("NONE", {}, baseline=["violence"])]
    assert run_screen.summarise(rows, "j", "b", use_baseline=True)["baseline"]["fp"] == 1


def test_shipped_second_judge_file_has_no_baseline_and_report_names_i1_recall():
    import json
    from pathlib import Path

    from socareguard.eval import report

    root = Path(__file__).parent.parent
    d = json.loads((root / "docs/metrics/screen-v1.1-claude.json").read_text())
    assert d["baseline"] is None
    assert d["per_label"]["I1"]["tp"] == 0 and d["per_label"]["I1"]["fn"] == 8
    old = report.OUT
    try:
        report.OUT = root / "docs/metrics"
        text = report.render("v1.1")
    finally:
        report.OUT = old
    assert "Per-category recall of the second judge at the 0.5 threshold: I1 0 of 8," in text
    tie = json.loads((root / "docs/metrics/auprc-tieaware-v1.1.json").read_text())["runs"]
    assert tie["clause_grounded"]["auprc"] == 0.7984
    assert tie["clause_grounded"]["auprc_file_order_deprecated"] == 0.7687
    assert tie["prompt_only"]["auprc"] == 0.7267 and tie["second_judge"]["auprc"] == 0.8035
