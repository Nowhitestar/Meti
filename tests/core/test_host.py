from core import host


def test_user_data_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    p = host.user_data_dir()
    assert p == tmp_path / ".config" / "mmp"


def test_user_data_dir_xdg_override(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    p = host.user_data_dir()
    assert p == tmp_path / "xdg" / "mmp"


def test_vault_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert host.vault_path() == tmp_path / ".config" / "mmp" / "credentials.json.age"
    assert host.vault_key_path() == tmp_path / ".config" / "mmp" / "age-key.txt"


def test_runs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    assert host.runs_dir() == tmp_path / "runs"


def test_detect_host_returns_string():
    h = host.detect_host()
    assert h in {"claude-code", "openclaw", "unknown"}


def test_user_providers_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert host.user_providers_dir() == tmp_path / ".config" / "mmp" / "providers"


def test_settings_path(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert host.settings_path() == tmp_path / ".config" / "mmp" / "settings.toml"
