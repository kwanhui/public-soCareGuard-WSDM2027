"""The panel states that the conduct screen is advisory (2026-11-23): the flag legend shown above
the flag cards and the closing line shown when there is no flag both carry the sentence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL_JS = ROOT / "src/socareguard/proxy/static/panel.js"
PANEL_HTML = ROOT / "src/socareguard/proxy/templates/panel.html"
ADVISORY = ("The conduct screen is advisory and can miss a violation, so you remain responsible "
            "for the reply.")


def test_the_flag_legend_says_the_screen_is_advisory():
    assert ADVISORY in PANEL_JS.read_text()


def test_the_no_flag_line_says_the_screen_is_advisory():
    assert ADVISORY in PANEL_HTML.read_text()
