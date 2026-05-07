import pytest

from core import settings


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_default_when_missing(isolated):
    s = settings.load()
    assert s.default_mode == "draft"
    assert s.wizard_enabled is True
    assert s.auto_save_manifest is True
    assert s.trusted_user_providers == []


def test_set_and_reload(isolated):
    s = settings.load()
    s.default_mode = "dry-run"
    s.trusted_user_providers = ["my-thing"]
    settings.save(s)

    s2 = settings.load()
    assert s2.default_mode == "dry-run"
    assert s2.trusted_user_providers == ["my-thing"]


def test_settings_file_path(isolated):
    s = settings.load()
    settings.save(s)
    assert (isolated / ".config" / "meti" / "settings.toml").exists()
