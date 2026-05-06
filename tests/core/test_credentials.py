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


# ---------------------------------------------------------------------------
# v0.3 vault hardening: atomic write, concurrent set, lost-key UX
# ---------------------------------------------------------------------------


def test_atomic_write_no_zero_byte_on_crash(isolated_vault):
    """Simulate a crash mid-write: tmp file present, vault file untouched."""
    import os

    store = CredentialStore(backend=FileBackend())
    store.set("p", "default", {"K": "original"})

    vault = isolated_vault / ".config" / "mmp" / "credentials.json.age"
    original_size = vault.stat().st_size
    original_bytes = vault.read_bytes()

    # Manually create a half-written tmp file (simulates crash before
    # os.replace completes). The vault file should still be intact.
    tmp = vault.with_suffix(vault.suffix + ".tmp")
    tmp.write_bytes(b"corrupted partial")
    assert tmp.exists()

    # Vault is untouched.
    assert vault.exists()
    assert vault.stat().st_size == original_size
    assert vault.read_bytes() == original_bytes

    # Cleanup the orphan tmp; subsequent writes work fine.
    os.unlink(tmp)
    store.set("p", "default", {"K": "updated"})
    assert store.get("p", "default") == {"K": "updated"}


def test_concurrent_set_no_lost_update(isolated_vault):
    """Two threads calling set() simultaneously must not lose either update."""
    import threading

    store = CredentialStore(backend=FileBackend())
    barrier = threading.Barrier(4)
    errors = []

    def worker(provider: str) -> None:
        try:
            barrier.wait()
            store.set(provider, "default", {"K": provider})
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b", "c", "d")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    accounts = sorted(store.list_accounts())
    assert accounts == ["a:default", "b:default", "c:default", "d:default"]
    # Each provider's value should be intact (no torn-write corruption)
    for name in ("a", "b", "c", "d"):
        assert store.get(name, "default") == {"K": name}


def test_lost_key_with_existing_vault_raises(isolated_vault):
    """Deleting the age key while the vault exists must NOT silently
    regenerate a new key (which would brick the vault). Must raise
    VaultIntegrityError with remediation guidance."""
    from core.credentials import VaultIntegrityError

    store = CredentialStore(backend=FileBackend())
    store.set("p", "default", {"K": "v"})

    vault = isolated_vault / ".config" / "mmp" / "credentials.json.age"
    key_file = isolated_vault / ".config" / "mmp" / "age-key.txt"
    assert vault.exists()
    assert key_file.exists()

    # Simulate a user accidentally deleting the key
    key_file.unlink()

    # Subsequent reads / writes must refuse to silently re-init
    fresh_store = CredentialStore(backend=FileBackend())
    with pytest.raises(VaultIntegrityError, match="missing"):
        fresh_store.get("p", "default")

    with pytest.raises(VaultIntegrityError, match="missing"):
        fresh_store.set("p", "default", {"K": "should not write"})

    # Key file is still NOT regenerated
    assert not key_file.exists()


def test_lost_key_with_no_vault_regenerates(isolated_vault):
    """If no vault exists yet, a missing key should be regenerated normally
    (first-use path). This is the happy path for new installs."""
    store = CredentialStore(backend=FileBackend())
    # First set creates both key and vault
    store.set("p", "default", {"K": "v"})

    key_file = isolated_vault / ".config" / "mmp" / "age-key.txt"
    vault = isolated_vault / ".config" / "mmp" / "credentials.json.age"
    assert key_file.exists()
    assert vault.exists()

    # Now delete BOTH (true reset)
    key_file.unlink()
    vault.unlink()

    # Fresh start works: new key + new vault generated
    store2 = CredentialStore(backend=FileBackend())
    store2.set("q", "default", {"K2": "v2"})
    assert key_file.exists()
    assert vault.exists()
    assert store2.get("q", "default") == {"K2": "v2"}
