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


def test_vault_key_env_takes_a_key_file_path_or_the_key(tmp_path, monkeypatch):
    """Round 3, WSDM N4: the README called SOCAREGUARD_VAULT_KEY a key file and the code read it as
    a base64 key, so a path gave a binascii traceback."""
    import base64

    import pytest

    first = Vault(tmp_path / "a.sqlite")
    first.put(Mapping("s", "Tan Wei Ming", "Lim Jun Hao", "NAME", "surrogate", "e"))
    key_file = tmp_path / "a.key"
    # a path to the key file
    monkeypatch.setenv("SOCAREGUARD_VAULT_KEY", str(key_file))
    assert [m.original for m in Vault(tmp_path / "a.sqlite").mappings("s")] == ["Tan Wei Ming"]
    # the key itself, in base64
    monkeypatch.setenv("SOCAREGUARD_VAULT_KEY", key_file.read_text().strip())
    assert [m.original for m in Vault(tmp_path / "a.sqlite").mappings("s")] == ["Tan Wei Ming"]
    assert base64.b64decode(key_file.read_text()) == first.key
    # a path that names no file, or a value that is not a key, fails with a plain message
    monkeypatch.setenv("SOCAREGUARD_VAULT_KEY", str(tmp_path / "missing" / "v.key"))
    with pytest.raises(RuntimeError, match="not a file"):
        Vault(tmp_path / "b.sqlite")
    monkeypatch.setenv("SOCAREGUARD_VAULT_KEY", "not-a-key")
    with pytest.raises(RuntimeError, match="not a 256-bit key"):
        Vault(tmp_path / "c.sqlite")
