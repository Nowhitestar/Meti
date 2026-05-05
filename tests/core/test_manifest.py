from pathlib import Path

import pytest

from core.errors import ManifestError
from core.manifest import Manifest, Target, load_manifest


FIXTURE = Path(__file__).parent.parent / "fixtures" / "longform-wechat.yaml"


def test_load_minimal(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\n'
        "type: image-post\n"
        'title: "Hi"\n'
        'body: "inline content"\n'
        "mode: dry-run\n"
        "targets:\n"
        "  - xiaohongshu\n"
    )
    m = load_manifest(p)
    assert m.schema_version == "0.2"
    assert m.type == "image-post"
    assert m.title == "Hi"
    assert m.body == "inline content"
    assert m.mode == "dry-run"
    assert len(m.targets) == 1
    assert m.targets[0].name == "xiaohongshu"
    assert m.targets[0].mode == "dry-run"  # inherits top-level
    assert m.targets[0].account == "default"


def test_load_fixture_full_form():
    m = load_manifest(FIXTURE)
    assert m.type == "longform"
    assert m.title == "Test Article"
    # body got resolved from path
    assert m.body.startswith("# Hello")
    assert m.tags == ["test"]
    assert len(m.targets) == 2

    t1 = m.targets[0]
    assert t1.name == "wechat-article"
    assert t1.mode == "dry-run"  # inherited
    assert t1.account == "default"

    t2 = m.targets[1]
    assert t2.name == "x-article"
    assert t2.mode == "draft"  # explicit override
    assert t2.account == "lewis"


def test_missing_required_field_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("schema_version: '0.2'\ntype: longform\nmode: dry-run\ntargets: [foo]\n")
    with pytest.raises(ManifestError, match="title"):
        load_manifest(p)


def test_invalid_mode_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\nbody: x\n'
        'mode: nuke\ntargets: [wechat-article]\n'
    )
    with pytest.raises(ManifestError, match="mode"):
        load_manifest(p)


def test_invalid_type_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: weird\ntitle: x\nbody: x\n'
        'mode: dry-run\ntargets: [wechat-article]\n'
    )
    with pytest.raises(ManifestError, match="type"):
        load_manifest(p)


def test_to_lock_dict_normalized():
    m = load_manifest(FIXTURE)
    lock = m.to_lock_dict()
    assert lock["schema_version"] == "0.2"
    assert lock["mode"] == "dry-run"
    # targets always full-form in lock
    assert all(isinstance(t, dict) for t in lock["targets"])
    assert lock["targets"][0]["name"] == "wechat-article"
    assert lock["targets"][0]["mode"] == "dry-run"
    assert lock["targets"][0]["account"] == "default"


def test_target_short_form_inherits_top_mode(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\nbody: x\n'
        'mode: draft\ntargets: [wechat-article, x-article]\n'
    )
    m = load_manifest(p)
    assert all(t.mode == "draft" for t in m.targets)


def test_defaults_block_applied(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\nbody: x\n'
        'mode: dry-run\ndefaults:\n  account: lewis\n  options:\n    digest: hi\n'
        'targets:\n  - wechat-article\n'
    )
    m = load_manifest(p)
    assert m.targets[0].account == "lewis"
    assert m.targets[0].options == {"digest": "hi"}


def test_body_path_explicit_missing_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\n'
        'body: ./missing.md\nmode: dry-run\ntargets: [wechat-article]\n'
    )
    with pytest.raises(ManifestError, match="body path not found"):
        load_manifest(p)
