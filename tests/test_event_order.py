"""Round 1, review finding F5 (2026-09-28): the event stream listed re-identification before the
screen, although the screen reads the pseudonymised reply. The stream now follows the code path:
receive, screen, reidentify, leakcheck, action, with contiguous sequence numbers."""

from pathlib import Path

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.screen.judge import FakeJudge
from socareguard.screen.screener import Screener


def test_screen_is_emitted_before_reidentify(tmp_path: Path):
    guard = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(judge=FakeJudge({}), use_baseline=False),
    )
    res = guard.run(
        [{"role": "user", "content": "Summarise.\n\nClient Mdm Tan Mei Ling, NRIC S1234567D."}],
        "disability",
        "openai/gpt-4.1-mini",
        reply_fixture="Summary for Mdm Tan.",
    )
    kinds = [e.kind for e in res.events]
    assert kinds.index("receive") < kinds.index("screen") < kinds.index("reidentify")
    assert kinds.index("reidentify") < kinds.index("leakcheck") < kinds.index("action")
    seqs = [e.seq for e in res.events]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), list(zip(kinds, seqs, strict=True))
