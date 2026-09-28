"""Round 6: the interface uses one word per concept (docs/terminology.md).

The text nodes and visible attributes of the templates, and the string and template literals of
the panel's scripts, are read with the prose checker's own extraction (scripts/check_prose.py).
A banned term fails the test unless it is a code identifier (a literal with no space, such as an
event kind or a CSS class, or a header name in a <code> span), or it stands inside parentheses as
the one technical word that a first mention may add ("stand-in (surrogate)").
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "src/socareguard/proxy/templates/panel.html",
    "src/socareguard/proxy/templates/supervisor.html",
    "src/socareguard/proxy/static/panel.js",
    "src/socareguard/proxy/static/supervisor.js",
    "src/socareguard/proxy/static/rewrite.js",
]
BANNED = {
    "quasi-identifier": r"quasi-identifiers?",
    "audience": r"audiences?",
    "judge": r"judges?|judge's",
    "attested": r"attested",
    "self-asserted": r"self-asserted",
    "annotate": r"annotated?|annotates|annotation",
    "surrogate": r"surrogates?",
}
_spec = importlib.util.spec_from_file_location("check_prose", ROOT / "scripts/check_prose.py")
check_prose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_prose)


def _ui_text(rel: str) -> list[tuple[int, str]]:
    path = ROOT / rel
    if path.suffix == ".html":
        raw = path.read_text()
        # code spans hold header names and paths, not words for the reader
        blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))
        raw = re.sub(r"<(code|pre)\b.*?</\1>", blank, raw, flags=re.DOTALL)
        return check_prose._html_prose(raw)
    return check_prose._js_strings(path.read_text())


def hits(text: str) -> list[str]:
    """Banned terms in one piece of interface text, outside identifiers and parentheses."""
    out = []
    if not re.search(r"\s", text.strip()):
        return out  # one token: an identifier, a class name, a kind
    bare = re.sub(r"\([^()]*\)", " ", text)  # the parenthetical first mention is allowed
    bare = re.sub(r"\b[\w-]*SoCareGuard-[\w-]+", " ", bare)  # header names
    for term, pat in BANNED.items():
        if re.search(rf"(?i)(?<![\w-])(?:{pat})(?![\w-])", bare):
            out.append(term)
    return out


@pytest.mark.parametrize("rel", FILES)
def test_no_banned_term_in_the_interface(rel):
    found = [(n, t, text[:120]) for n, text in _ui_text(rel) for t in hits(text)]
    assert not found, found


@pytest.mark.parametrize("rel", FILES)
def test_a_parenthetical_technical_word_appears_at_most_once(rel):
    text = " ".join(t for _, t in _ui_text(rel))
    for term, pat in BANNED.items():
        n = len(re.findall(rf"(?i)\([^()]*\b(?:{pat})\b[^()]*\)", text))
        assert n <= 1, (rel, term, n)


def test_the_rendered_pages_carry_no_banned_term(tmp_path, monkeypatch):
    from tests.test_round6_interface import _client

    client = _client(tmp_path, monkeypatch)
    pages = {"panel": client.get("/").text}
    client.post("/supervisor/login", data={"username": "admin", "password": "demo1234"})
    pages["supervisor"] = client.get("/supervisor").text
    for name, html in pages.items():
        html = re.sub(r"<(script|style|code|pre)\b.*?</\1>", " ", html, flags=re.DOTALL)
        for n, text in check_prose._html_prose(html):
            assert not hits(text), (name, n, text[:160])


def test_the_checker_itself():
    assert hits("Names are replaced by stand-ins (surrogates).") == []
    assert hits("replaced by a surrogate") == ["surrogate"]
    assert hits("annotate") == []  # a decision kind in code
    assert hits("Decision: ANNOTATE for the external audience") == ["audience", "annotate"]
    assert hits("the judge's own confidence") == ["judge"]
    assert hits("in their professional judgement") == []
    assert hits("sets X-SoCareGuard-Audience on the request") == []
    assert hits("sw-042 (self-asserted)") == []
    assert hits("sw-042 self-asserted") == ["self-asserted"]
