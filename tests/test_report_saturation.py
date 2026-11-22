"""Final defensibility check, item 1: the judge-confidence saturation figure quoted in the
paper (177 of 288 flags at or above 0.95, on the 600 v1.1 drafts) traces to a computed row in
docs/metrics.md, not to a hand-counted number with no file behind it.

Also covers item 5: the cost figure cites the file that actually exists (cost-v1.1.json) and says
plainly that it was not re-measured on v1.2.
"""

from pathlib import Path

from socareguard.eval import report

ROOT = Path(__file__).parent.parent


def test_confidence_distribution_matches_the_shipped_v12_rows():
    dist = report._confidence_distribution("v1.2")
    assert dist is not None
    assert "600 drafts" in dist
    assert "288 judge flags" in dist
    assert "0.95 (81)" in dist
    assert "0.98 (2)" in dist
    assert "1 (94)" in dist
    assert "At or above 0.95: 177 of 288." in dist


def test_confidence_distribution_excludes_v12_external_drafts():
    import json

    rows = [
        json.loads(line)
        for line in (ROOT / "docs/metrics/screen-v1.2-rows.jsonl").read_text().splitlines()
        if line.strip()
    ]
    external = [r for r in rows if r.get("audience") == "external"]
    assert len(external) == 90
    non_external = [r for r in rows if r.get("audience") != "external"]
    assert len(non_external) == 600


def test_render_v12_reports_the_confidence_distribution_and_traces_the_cost_file():
    old = report.OUT
    try:
        report.OUT = ROOT / "docs/metrics"
        text = report.render("v1.2")
    finally:
        report.OUT = old
    assert "At or above 0.95: 177 of 288." in text
    assert "`docs/metrics/cost-v1.1.json` holds these figures" in text
    assert "measured at v1.1 and has not been re-run on v1.2" in text
    assert "cost-v1.2.json" not in text
