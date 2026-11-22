"""/healthz reports the public commit that the deployed build was made from (2026-11-22).

The Space is built from a copy of the public repository without .git, so the deploy workflow
writes the commit into src/socareguard/build_commit.txt. A local run has no such file, and
/healthz then reports null."""

from pathlib import Path

from fastapi.testclient import TestClient

from socareguard import build_info
from tests.test_proxy import make_guard

ROOT = Path(__file__).resolve().parent.parent
SHA = "0123456789abcdef0123456789abcdef01234567"


def _healthz(tmp_path):
    from socareguard.proxy.app import create_app

    return TestClient(create_app(make_guard(tmp_path))).get("/healthz").json()


def test_a_local_run_reports_no_commit(tmp_path, monkeypatch):
    monkeypatch.delenv(build_info.BUILD_COMMIT_ENV, raising=False)
    monkeypatch.setattr(build_info, "BUILD_COMMIT_FILE", tmp_path / "absent.txt")
    h = _healthz(tmp_path)
    assert h["ok"] is True and h["build_commit"] is None


def test_the_deployed_commit_is_read_from_the_package(tmp_path, monkeypatch):
    monkeypatch.delenv(build_info.BUILD_COMMIT_ENV, raising=False)
    baked = tmp_path / "build_commit.txt"
    baked.write_text(SHA + "\n")
    monkeypatch.setattr(build_info, "BUILD_COMMIT_FILE", baked)
    assert _healthz(tmp_path)["build_commit"] == SHA


def test_the_setting_overrides_the_file_and_a_malformed_value_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_COMMIT_FILE", tmp_path / "absent.txt")
    monkeypatch.setenv(build_info.BUILD_COMMIT_ENV, SHA[:7])
    assert build_info.build_commit() == SHA[:7]
    monkeypatch.setenv(build_info.BUILD_COMMIT_ENV, "not a commit <script>")
    assert build_info.build_commit() is None


def test_the_file_is_never_committed():
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert "src/socareguard/build_commit.txt" in lines


DEPLOY = ROOT / ".github/workflows/deploy-hf.yml"


def test_the_deploy_workflow_writes_the_public_commit_into_the_package():
    import pytest

    if not DEPLOY.exists():
        pytest.skip("the deploy workflow lives in the development repository only")
    text = DEPLOY.read_text()
    assert 'echo "$src_sha_full" > src/socareguard/build_commit.txt' in text
    assert "git add -f src/socareguard/build_commit.txt" in text
    assert text.index("build_commit.txt") < text.index("git commit -q")
