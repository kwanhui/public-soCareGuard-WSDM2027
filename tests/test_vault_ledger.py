import json

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Mapping, Vault


def test_vault_roundtrip_and_isolation(tmp_path):
    v = Vault(tmp_path / "v.sqlite")
    v.put(Mapping("s1", "Tan Wei Ming", "Lim Jun Hao", "NAME", "surrogate", "e1"))
    v.put(Mapping("s2", "Other", "Someone", "NAME", "surrogate", "e1"))
    ms = v.mappings("s1")
    assert [(m.original, m.surrogate) for m in ms] == [("Tan Wei Ming", "Lim Jun Hao")]
    raw = (tmp_path / "v.sqlite").read_bytes()
    assert b"Tan Wei Ming" not in raw and b"Lim Jun Hao" in raw
    assert (tmp_path / "v.key").stat().st_mode & 0o777 == 0o600
    assert v.forget("s1") == 1 and v.mappings("s1") == []


def test_ledger_chain_and_tamper_detection(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    a = led.append({"event": "send", "n": 1})
    b = led.append({"event": "receive", "n": 2})
    assert b["prev_sha256"] == a["row_sha256"]
    assert led.verify() == (True, 2)
    rows = led.rows()
    rows[0]["n"] = 99
    (tmp_path / "l.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ok, idx = led.verify()
    assert not ok and idx == 0


def test_ledger_chain_survives_concurrent_appends(tmp_path):
    import threading

    led = Ledger(tmp_path / "l.jsonl")
    threads = [
        threading.Thread(target=lambda i=i: [led.append({"n": i, "k": j}) for j in range(20)])
        for i in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok, n = led.verify()
    assert ok and n == 120
