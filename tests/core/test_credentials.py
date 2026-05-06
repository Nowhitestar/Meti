import pytest

from core.credentials import CredentialStore, EnvBackend, FileBackend
from core.errors import MissingCredentialError


@pytest.fixture
def isolated_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MMP_VAULT_KEY", raising=False)
    return tmp_path


def test_env_vault_key_overrides_file(monkeypatch, tmp_path):
    """MMP_VAULT_KEY ENV is the canonical source when set; file is fallback."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # generate a key out-of-band
    import pyrage

    identity = pyrage.x25519.Identity.generate()
    monkeypatch.setenv("MMP_VAULT_KEY", str(identity))

    backend = FileBackend()
    store = CredentialStore(backend=backend)
    store.set("p", "default", {"K": "v"})

    # Key file should NOT have been created when ENV is set
    assert not (tmp_path / ".config" / "mmp" / "age-key.txt").exists()

    # And we can still read back
    assert store.get("p", "default") == {"K": "v"}


def test_file_backend_roundtrip(isolated_vault):
    backend = FileBackend()
    store = CredentialStore(backend=backend)
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "wx", "WECHAT_APP_SECRET": "s"})

    out = store.get("wechat-article", "default")
    assert out == {"WECHAT_APP_ID": "wx", "WECHAT_APP_SECRET": "s"}


def test_file_backend_persists_encrypted(isolated_vault):
    backend = FileBackend()
    store = CredentialStore(backend=backend)
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "wx"})

    vault_file = isolated_vault / ".config" / "mmp" / "credentials.json.age"
    assert vault_file.exists()
    raw = vault_file.read_bytes()
    assert b"WECHAT_APP_ID" not in raw  # encrypted, not visible


def test_get_missing_raises(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    with pytest.raises(MissingCredentialError):
        store.get("wechat-article", "default")


def test_env_overrides_vault(isolated_vault, monkeypatch):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "from_vault"})
    monkeypatch.setenv("WECHAT_APP_ID", "from_env")

    out = store.get("wechat-article", "default")
    assert out["WECHAT_APP_ID"] == "from_env"


def test_list_accounts(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"K": "v"})
    store.set("wechat-article", "lewis", {"K": "v2"})
    store.set("xiaohongshu", "default", {"K": "v3"})

    assert sorted(store.list_accounts("wechat-article")) == ["default", "lewis"]
    assert sorted(store.list_accounts(None)) == [
        "wechat-article:default",
        "wechat-article:lewis",
        "xiaohongshu:default",
    ]


def test_delete(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"K": "v"})
    store.delete("wechat-article", "default")
    with pytest.raises(MissingCredentialError):
        store.get("wechat-article", "default")


def test_env_only_backend(monkeypatch):
    monkeypatch.setenv("WECHAT_APP_ID", "ww")
    monkeypatch.setenv("WECHAT_APP_SECRET", "ss")
    store = CredentialStore(backend=EnvBackend())
    out = store.get(
        "wechat-article",
        "default",
        required_keys=["WECHAT_APP_ID", "WECHAT_APP_SECRET"],
    )
    assert out == {"WECHAT_APP_ID": "ww", "WECHAT_APP_SECRET": "ss"}


def test_required_keys_filtering(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "wx", "EXTRA": "x"})
    out = store.get("wechat-article", "default", required_keys=["WECHAT_APP_ID"])
    assert out == {"WECHAT_APP_ID": "wx"}
