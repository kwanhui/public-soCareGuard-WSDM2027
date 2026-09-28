"""The compliance auditor's four tamper cases (round 1, COMP-F1) against the sequenced chain.

T1 edit a row without re-hashing, T2 edit a row and re-hash that row only, T3 rewrite every row
from the edit to the end, T4 cut the tail. T3 is the documented limit of a local chain: the file
verifies on its own, and only the head hash logged at append time shows the rewrite.
"""

import hashlib
import json
import logging

from socareguard.ledger import Ledger, _canon


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")


def _rehash_from(rows, start, renumber=False):
    prev = rows[start - 1]["row_sha256"] if start > 0 else None
    for i in range(start, len(rows)):
        body = {k: v for k, v in rows[i].items() if k != "row_sha256"}
        body["prev_sha256"] = prev
        if renumber:
            body["seq"] = i
        rows[i] = {**body, "row_sha256": hashlib.sha256(_canon(body).encode()).hexdigest()}
        prev = rows[i]["row_sha256"]
    return rows


def _ledger(tmp_path, n=10):
    led = Ledger(tmp_path / "l.jsonl")
    for i in range(n):
        led.append({"session": f"s{i}", "decision": "escalate" if i == 5 else "pass"})
    return led


def test_rows_carry_their_sequence_number_inside_the_hash(tmp_path):
    led = _ledger(tmp_path, 3)
    assert [r["seq"] for r in led.rows()] == [0, 1, 2]
    r = led.report()
    assert r["ok"] and r["rows"] == 3 and r["head_sha256"] == led.rows()[-1]["row_sha256"]
    assert r["first_seq_gap"] is None and r["first_bad_row"] is None


def test_t1_partial_edit_is_detected(tmp_path):
    led = _ledger(tmp_path)
    rows = led.rows()
    rows[5]["decision"] = "pass"
    _write(led.path, rows)
    r = led.report()
    assert not r["ok"] and r["first_bad_row"] == 5


def test_t2_edit_with_own_rehash_is_detected_at_the_next_row(tmp_path):
    led = _ledger(tmp_path)
    rows = led.rows()
    rows[5]["decision"] = "pass"
    body = {k: v for k, v in rows[5].items() if k != "row_sha256"}
    rows[5]["row_sha256"] = hashlib.sha256(_canon(body).encode()).hexdigest()
    _write(led.path, rows)
    r = led.report()
    assert not r["ok"] and r["first_bad_row"] == 6


def test_t3_suffix_rewrite_passes_the_file_check_but_not_the_logged_head(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="socareguard.ledger")
    led = _ledger(tmp_path)
    logged = [m.split() for m in caplog.messages if m.startswith("ledger head ")]
    assert len(logged) == 10
    shipped_head, shipped_rows = logged[-1][2], int(logged[-1][4])
    assert shipped_head == led.rows()[-1]["row_sha256"] and shipped_rows == 10
    rows = led.rows()
    rows[5]["decision"] = "pass"
    _write(led.path, _rehash_from(rows, 5))
    r = led.report(expected_rows=shipped_rows)
    # the known limit: a full rewrite from row 5 onwards verifies on the file alone
    assert r["ok"] and r["rows"] == 10
    # the head hash shipped off the host at append time no longer matches the file
    assert r["head_sha256"] != shipped_head


def test_t4_truncation_is_detected_with_the_expected_row_count(tmp_path):
    led = _ledger(tmp_path)
    _write(led.path, led.rows()[:-5])
    assert led.report()["ok"]  # without an external count, a cut tail is invisible
    r = led.report(expected_rows=10)
    assert not r["ok"] and r["truncated"] and r["rows"] == 5


def test_deleted_middle_row_is_a_sequence_gap_even_after_rehashing(tmp_path):
    led = _ledger(tmp_path)
    rows = led.rows()
    del rows[4]
    _write(led.path, _rehash_from(rows, 4))  # chain re-linked, seq left as written
    r = led.report()
    assert r["first_bad_row"] is None and r["first_seq_gap"] == 4 and not r["ok"]
    assert led.verify() == (False, 4)


def test_verify_route_reports_head_gap_and_truncation(tmp_path):
    from fastapi.testclient import TestClient

    from socareguard.outbound.vault import Vault
    from socareguard.proxy.app import create_app
    from socareguard.proxy.core import Guard

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
    )
    for i in range(4):
        g.ledger.append({"session": f"s{i}", "decision": "pass"})
    client = TestClient(create_app(g))
    v = client.get("/v1/ledger/verify").json()
    assert v["ok"] and v["rows"] == 4 and v["head_sha256"] == g.ledger.rows()[-1]["row_sha256"]
    assert "anchoring the head hash outside the host" in v["scope"]
    _write(g.ledger.path, g.ledger.rows()[:2])
    v = client.get("/v1/ledger/verify?expected_rows=4").json()
    assert not v["ok"] and v["truncated"] and v["message"] == "4 rows expected, 2 found"
