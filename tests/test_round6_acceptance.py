"""Round 6 acceptance pass (2026-09-28): the instruction line, the bare age, the protection-order
clause boundary, the supervisor label and the "kept as typed" legend item.

F1 (session 04e3dad9eb06): "Write a short letter to the client's day activity centre about her
transport" left as "Write a short letter to an employer about her transport", because a detector
read the phrase as an employer and the pack's employer rule ran on the instruction line.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import socareguard.outbound.sanitise as sanitise_mod
from socareguard.detect.sg import Hit
from socareguard.outbound.generalise import generalise_attribute
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import _sanitise_message

ROOT = Path(__file__).resolve().parent.parent
PANEL_JS = ROOT / "src/socareguard/proxy/static/panel.js"

DAC = "Write a short letter to the client's day activity centre about her transport."
DAC_NOTE = (
    "Client Mdm Siti Aminah binti Yusof has an intellectual disability and attends the day"
    " activity centre in Tampines. She now travels by the centre's bus and needs a helper at the"
    " pick-up point."
)


def _run(tmp_path: Path, pack: str, audience: str, message: str, session: str = "acc"):
    vault = Vault(tmp_path / f"{session}-{audience}.sqlite")
    san = Sanitiser(vault, load_pack(pack), use_presidio=False, use_gliner=False, audience=audience)
    return _sanitise_message(san, message, session, 1, 1)


def restore_text(reply: str, session: str, tmp_path: Path, name: str) -> str:
    from socareguard.inbound.restore import restore

    return restore(reply, Vault(tmp_path / f"{name}-external.sqlite"), session).text


def _as_employer(monkeypatch, phrase: str):
    """Make a detector read ``phrase`` as an employer, as the one on the Space did."""
    real = sanitise_mod.detect

    def detect(text, **kw):
        det = real(text, **kw)
        i = text.find(phrase)
        if i >= 0:
            det.entities.append(Hit(i, i + len(phrase), phrase, "EMPLOYER", "gliner", 0.7))
        return det

    monkeypatch.setattr(sanitise_mod, "detect", detect)


@pytest.mark.parametrize("audience", ["care-team", "external", "internal"])
def test_the_care_team_recipient_in_the_instruction_is_kept(tmp_path, monkeypatch, audience):
    _as_employer(monkeypatch, "client's day activity centre")
    out = _run(tmp_path, "disability", audience, DAC + "\n\n" + DAC_NOTE)
    head = out.text.split("\n\n")[0]
    assert head == DAC, head
    assert "an employer" not in out.text, out.text


@pytest.mark.parametrize("audience", ["care-team", "external"])
@pytest.mark.parametrize(
    "instruction",
    [
        "Write a letter to the school counsellor about his attendance.",
        "Write a short note to her GP about the new medication.",
        "Email the DAC coordinator about his new timetable.",
    ],
)
def test_other_care_team_recipients_in_the_instruction_are_kept(
    tmp_path, monkeypatch, audience, instruction
):
    recipient = re.search(r"(?:to|Email) (?:the |her )?(.+?) about", instruction).group(1)
    _as_employer(monkeypatch, recipient)
    out = _run(tmp_path, "disability", audience, instruction + "\n\n" + DAC_NOTE)
    assert out.text.split("\n\n")[0] == instruction, out.text


def test_an_employer_in_the_instruction_is_never_generalised(tmp_path):
    """A recipient named by its kind is kept as typed. An organisation named by its own name takes
    a stand-in that the draft restores (round 3 COACH-F1 keeps "Ace Hardware" from leaving), and
    neither leaves as "an employer". The note's mention is still generalised."""
    ins = "Write a letter to her employer about her shifts."
    note = "Mdm Siti Aminah binti Yusof works part-time at Sheng Siong Holdings as a packer."
    out = _run(tmp_path, "disability", "external", ins + "\n\n" + note)
    assert out.text.split("\n\n")[0] == ins, out.text
    ins = "Write a letter to Sheng Siong Holdings about her shifts."
    out = _run(tmp_path, "disability", "external", ins + "\n\n" + note, session="named")
    head, body = out.text.split("\n\n")
    assert "an employer" not in head and "Sheng Siong" not in head, head
    assert re.fullmatch(r"Write a letter to [A-Z]\w+ Holdings about her shifts\.", head), head
    assert "Sheng Siong" not in body and "employer" in body, body
    stand_in = next(new for h, new, k in out.replacements if h.start < len(ins))
    assert restore_text(f"Dear {stand_in},", out.session, tmp_path, "named") == (
        "Dear Sheng Siong Holdings,"
    )


def test_a_client_named_in_the_instruction_still_gets_a_stand_in(tmp_path):
    ins = "Write a letter for Mdm Siti Aminah binti Yusof to the client's day activity centre."
    for audience in ("care-team", "external", "internal"):
        out = _run(tmp_path, "disability", audience, ins + "\n\n" + DAC_NOTE)
        head = out.text.split("\n\n")[0]
        assert "Siti Aminah" not in head and "Yusof" not in head, head
        assert "day activity centre" in head, head


def test_a_named_school_in_the_instruction_takes_a_stand_in_not_its_kind(tmp_path):
    ins = "Write to the counsellor at Bedok Green Secondary School about his attendance."
    note = "Client Amirul bin Rashid attends Bedok Green Secondary School."
    out = _run(tmp_path, "youth-offending", "care-team", ins + "\n\n" + note)
    head = out.text.split("\n\n")[0]
    assert "Bedok Green" not in out.text, out.text
    assert "a secondary school" not in head and "Secondary" in head, head


# ---------- F2: a bare age set off by commas ----------


def test_a_bare_age_after_the_name_is_banded(tmp_path):
    note = "Client Amirul bin Rashid, 15, Secondary 3, lives with his mother in a rental flat."
    out = _run(tmp_path, "youth-offending", "external", note).text
    assert ", 15," not in out and "15 to 17" in out, out
    for kept in ("Last seen in Sep, 15, at the centre", "The lift to Level, 12, is out of order"):
        text = _run(tmp_path, "youth-offending", "external", kept, session=kept[:3]).text
        assert re.search(r", 1[25],", text), text


# ---------- F3: the protection-order rule stops at the clause boundary ----------


def test_the_ppo_rule_keeps_the_second_clause():
    got = generalise_attribute(
        "ppo",
        "Farhana has not applied for a protection order and wants to keep the sessions fortnightly",
        "status_only",
        "domestic-violence",
    )
    assert got == (
        "no protection order application is on record and Farhana wants to keep the sessions"
        " fortnightly"
    ), got


def test_the_ppo_sentence_keeps_the_clients_wish_in_what_leaves(tmp_path):
    note = (
        "Farhana has not applied for a protection order and wants to keep the sessions fortnightly."
    )
    out = _run(tmp_path, "domestic-violence", "internal", note).text
    assert "no protection order application is on record" in out.lower(), out
    assert "wants to keep the sessions fortnightly" in out, out
    assert "applied" not in out, out


# ---------- cosmetic: the supervisor label and the legend item ----------


def _actor_label(actor: str, attested):
    js = PANEL_JS.read_text()
    fn = re.search(r"  function actorLabel\(actor, attested\) \{.*?\n  \}", js, re.DOTALL).group(0)
    script = f"{fn}\nconsole.log(JSON.stringify(actorLabel({json.dumps(actor)}, {json.dumps(attested)})));"
    return json.loads(
        subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_sandbox_login_reads_as_one_parenthesis():
    assert _actor_label("admin (sandbox login)", False) == "admin (sandbox login, typed in)"
    assert _actor_label("sw-042 (self-asserted)", None) == "sw-042 (typed in)"
    assert _actor_label("sup-007", True) == "sup-007 (checked by a person)"


def test_the_kept_as_typed_legend_item_says_what_it_means():
    js = PANEL_JS.read_text()
    assert 'KEPT: "kept as typed"' in js
    assert 'id="legend-kept" title="${KEPT_TITLE}"' in js
    title = re.search(r'const KEPT_TITLE = "([^"]+)"', js).group(1)
    assert "leave as written, such as a public body" in title, title
    assert "(sandbox login) (" not in js
