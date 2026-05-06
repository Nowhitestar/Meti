import pytest

from core.errors import ManifestError
from core.wizard.commit import commit_manifest

VALID_YAML = """\
schema_version: "0.2"
type: longform
title: "Test"
body: "inline body"
mode: dry-run
targets:
  - wechat-article
"""


def test_commit_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    src = tmp_path / "src.yaml"
    src.write_text(VALID_YAML, encoding="utf-8")

    run_dir = commit_manifest(src)
    assert run_dir.exists()
    assert (run_dir / "manifest.yaml").read_text() == VALID_YAML
    assert (run_dir / "manifest.lock.json").exists()


def test_commit_invalid_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    src = tmp_path / "src.yaml"
    src.write_text("not valid yaml: ::", encoding="utf-8")
    with pytest.raises(ManifestError):
        commit_manifest(src)
