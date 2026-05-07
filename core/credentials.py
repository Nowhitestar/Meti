"""Credential vault: encrypted file backend (age) + ENV backend.

Vault layout (decrypted JSON):
  {
    "version": 1,
    "accounts": {
        "<provider>:<account>": {"KEY": "value", ...},
        ...
    }
  }

ENV always wins over the vault: any key already present in the vault is
overridden by an os.environ entry with the same name. To pull keys that
exist *only* in the environment (e.g. on CI with EnvBackend), callers must
pass ``required_keys=[...]`` explicitly.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from pathlib import Path

import pyrage  # type: ignore[import-untyped]

from core import host
from core.errors import MissingCredentialError, MMPError

_VAULT_VERSION = 1


class VaultIntegrityError(MMPError):
    """Vault file exists but cannot be decrypted with the available key.

    Most common cause: the age key file was deleted (or rotated) but the
    encrypted vault file remained. Auto-regenerating a new key would
    permanently lock the user out of their own credentials, so we refuse
    and surface this error with remediation guidance.
    """


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_or_create_key(
    key_path: Path,
    *,
    vault_path: Path | None = None,
) -> tuple[pyrage.x25519.Identity, pyrage.x25519.Recipient]:
    """Return (identity, recipient).

    Priority:
      1. ENV METI_VAULT_KEY (canonical for CI / one-shot use), with
         MMP_VAULT_KEY accepted as a deprecated fallback for one release
      2. existing key file at key_path
      3. generate a new key file — but ONLY when no encrypted vault exists.
         If ``vault_path`` is provided and points at an existing encrypted
         file, refuse to regenerate (would silently brick the vault) and
         raise ``VaultIntegrityError`` instead.
    """
    from core.host import _env_with_legacy

    env_key = (_env_with_legacy("METI_VAULT_KEY", "MMP_VAULT_KEY") or "").strip()
    if env_key:
        identity = pyrage.x25519.Identity.from_str(env_key)
        return identity, identity.to_public()
    if not key_path.exists():
        # Refuse to auto-regenerate when vault data is at risk.
        if vault_path is not None and vault_path.exists():
            raise VaultIntegrityError(
                f"vault key {key_path} is missing, but encrypted vault "
                f"{vault_path} exists. Auto-generating a new key would "
                f"permanently lock you out. Restore your age key file from "
                f"backup, or delete the vault to start over: "
                f"`rm {vault_path}`."
            )
        identity = pyrage.x25519.Identity.generate()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(str(identity), encoding="utf-8")
        os.chmod(key_path, 0o600)
        return identity, identity.to_public()
    text = key_path.read_text(encoding="utf-8").strip()
    identity = pyrage.x25519.Identity.from_str(text)
    return identity, identity.to_public()


@contextlib.contextmanager
def _vault_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive flock on ``lock_path`` for the duration of a write.

    Lock file is separate from the vault itself so we don't hold a handle
    on the file we're about to atomically replace. Created on first use,
    chmod 600.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 'a+' — open for read/write, create if missing, never truncate.
    with open(lock_path, "a+") as fh:
        os.chmod(lock_path, 0o600)
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (tmp + fsync + os.replace).

    A crash, OOM, or ^C between truncate and final write of a normal
    ``Path.write_bytes`` could leave the vault as a zero-byte file —
    every credential lost. Atomic-replace prevents that.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


class Backend(ABC):
    @abstractmethod
    def read_all(self) -> dict[str, dict[str, str]]: ...

    @abstractmethod
    def write_all(self, accounts: dict[str, dict[str, str]]) -> None: ...

    def update(
        self,
        mutator: Callable[[dict[str, dict[str, str]]], None],
    ) -> None:
        """Atomic read-modify-write.

        ``mutator`` is called with the current accounts dict and should mutate
        it in place. The default implementation is NOT atomic — subclasses
        with file-backed storage must override to wrap the entire operation
        in a file lock (see ``FileBackend.update``) so concurrent
        ``CredentialStore.set/delete`` callers don't lose updates.
        """
        accounts = self.read_all()
        mutator(accounts)
        self.write_all(accounts)


class FileBackend(Backend):
    """Age-encrypted JSON vault at host.vault_path()."""

    def __init__(self) -> None:
        self._vault = host.vault_path()
        self._key = host.vault_key_path()
        self._lock = self._vault.parent / "vault.lock"

    def read_all(self) -> dict[str, dict[str, str]]:
        if not self._vault.exists():
            return {}
        identity, _ = _read_or_create_key(self._key, vault_path=self._vault)
        ciphertext = self._vault.read_bytes()
        plaintext = pyrage.decrypt(ciphertext, [identity])
        data = json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            return {}
        accounts = data.get("accounts", {})
        if not isinstance(accounts, dict):
            return {}
        return accounts

    def write_all(self, accounts: dict[str, dict[str, str]]) -> None:
        _ensure_dir(self._vault.parent)
        with _vault_lock(self._lock):
            self._write_all_locked(accounts)

    def _write_all_locked(self, accounts: dict[str, dict[str, str]]) -> None:
        """Encrypt + atomic write. Caller MUST hold ``self._lock``."""
        _, recipient = _read_or_create_key(self._key, vault_path=self._vault)
        body = json.dumps(
            {"version": _VAULT_VERSION, "accounts": accounts}, ensure_ascii=False
        ).encode("utf-8")
        ciphertext = pyrage.encrypt(body, [recipient])
        _atomic_write_bytes(self._vault, ciphertext)

    def update(
        self,
        mutator: Callable[[dict[str, dict[str, str]]], None],
    ) -> None:
        """Atomic read-modify-write under the vault lock."""
        _ensure_dir(self._vault.parent)
        with _vault_lock(self._lock):
            accounts = self.read_all()
            mutator(accounts)
            self._write_all_locked(accounts)


class EnvBackend(Backend):
    """Read-only backend that pulls from os.environ. Used in CI."""

    def read_all(self) -> dict[str, dict[str, str]]:
        return {}

    def write_all(self, accounts: dict[str, dict[str, str]]) -> None:
        raise NotImplementedError("EnvBackend is read-only")


class CredentialStore:
    """Vault facade. ENV always overrides vault."""

    def __init__(self, backend: Backend | None = None) -> None:
        self._backend: Backend = backend or FileBackend()

    def set(self, provider: str, account: str, values: dict[str, str]) -> None:
        key = f"{provider}:{account}"
        new_values = dict(values)

        def _mutate(accounts: dict[str, dict[str, str]]) -> None:
            accounts[key] = new_values

        self._backend.update(_mutate)

    def get(
        self,
        provider: str,
        account: str = "default",
        required_keys: list[str] | None = None,
    ) -> dict[str, str]:
        key = f"{provider}:{account}"
        all_ = self._backend.read_all()
        vault_values = dict(all_.get(key, {}))

        # ENV override: any matching key in os.environ wins
        merged = dict(vault_values)
        for k in list(merged.keys()):
            if k in os.environ:
                merged[k] = os.environ[k]

        # Also pick up env-only keys when required_keys is given
        if required_keys:
            for k in required_keys:
                if k not in merged and k in os.environ:
                    merged[k] = os.environ[k]
            missing = [k for k in required_keys if k not in merged]
            if missing:
                raise MissingCredentialError(provider=provider, keys=missing)
            return {k: merged[k] for k in required_keys}

        if not merged:
            raise MissingCredentialError(provider=provider, keys=["*"])
        return merged

    def list_accounts(self, provider: str | None = None) -> list[str]:
        all_ = self._backend.read_all()
        if provider is None:
            return sorted(all_.keys())
        prefix = f"{provider}:"
        return [k.removeprefix(prefix) for k in sorted(all_.keys()) if k.startswith(prefix)]

    def delete(self, provider: str, account: str) -> None:
        key = f"{provider}:{account}"

        def _mutate(accounts: dict[str, dict[str, str]]) -> None:
            accounts.pop(key, None)

        self._backend.update(_mutate)
