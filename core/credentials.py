"""Credential vault: encrypted file backend (age) + ENV backend.

Vault layout (decrypted JSON):
  {
    "version": 1,
    "accounts": {
        "<provider>:<account>": {"KEY": "value", ...},
        ...
    }
  }

ENV-only fallback: when neither the vault nor required_keys give us anything,
we scan os.environ for keys whose name starts with the provider's prefix
(uppercase of the first hyphen-segment, e.g. ``wechat-article`` -> ``WECHAT_``)
and return those. ENV always wins over the vault.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

import pyrage  # type: ignore[import-untyped]

from core import host
from core.errors import MissingCredentialError

_VAULT_VERSION = 1


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _provider_env_prefix(provider: str) -> str:
    """Derive the ENV-var prefix for a provider name.

    ``wechat-article`` -> ``WECHAT_``
    ``xiaohongshu`` -> ``XIAOHONGSHU_``
    """
    head = provider.split("-", 1)[0]
    return f"{head.upper()}_"


def _env_scan(provider: str) -> dict[str, str]:
    """Return all os.environ entries whose key starts with the provider prefix."""
    prefix = _provider_env_prefix(provider)
    return {k: v for k, v in os.environ.items() if k.startswith(prefix)}


def _read_or_create_key(key_path: Path) -> tuple[pyrage.x25519.Identity, pyrage.x25519.Recipient]:
    """Return (identity, recipient).

    Priority:
      1. ENV MMP_VAULT_KEY (canonical for CI / one-shot use)
      2. existing key file at key_path
      3. generate a new key file (first use)
    """
    env_key = os.environ.get("MMP_VAULT_KEY", "").strip()
    if env_key:
        identity = pyrage.x25519.Identity.from_str(env_key)
        return identity, identity.to_public()
    if not key_path.exists():
        identity = pyrage.x25519.Identity.generate()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(str(identity), encoding="utf-8")
        os.chmod(key_path, 0o600)
        return identity, identity.to_public()
    text = key_path.read_text(encoding="utf-8").strip()
    identity = pyrage.x25519.Identity.from_str(text)
    return identity, identity.to_public()


class Backend(ABC):
    @abstractmethod
    def read_all(self) -> dict[str, dict[str, str]]: ...

    @abstractmethod
    def write_all(self, accounts: dict[str, dict[str, str]]) -> None: ...


class FileBackend(Backend):
    """Age-encrypted JSON vault at host.vault_path()."""

    def __init__(self) -> None:
        self._vault = host.vault_path()
        self._key = host.vault_key_path()

    def read_all(self) -> dict[str, dict[str, str]]:
        if not self._vault.exists():
            return {}
        identity, _ = _read_or_create_key(self._key)
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
        _, recipient = _read_or_create_key(self._key)
        body = json.dumps(
            {"version": _VAULT_VERSION, "accounts": accounts}, ensure_ascii=False
        ).encode("utf-8")
        ciphertext = pyrage.encrypt(body, [recipient])
        self._vault.write_bytes(ciphertext)
        os.chmod(self._vault, 0o600)


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
        all_ = self._backend.read_all()
        all_[f"{provider}:{account}"] = dict(values)
        self._backend.write_all(all_)

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

        # No vault hit + no required_keys: fall back to provider-prefixed env scan.
        if not merged:
            merged = _env_scan(provider)

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
        all_ = self._backend.read_all()
        all_.pop(f"{provider}:{account}", None)
        self._backend.write_all(all_)
