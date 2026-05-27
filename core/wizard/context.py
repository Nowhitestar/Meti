"""Build a JSON context object describing current wizard state.

Claude reads this (via `meti wizard --dump-context`) to know which providers
are available, which accounts have credentials, and what the user's settings
say. The context is the bridge between Python state and Claude conversation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import host
from core import settings as settings_mod
from core.credentials import CredentialStore
from core.errors import MissingCredentialError
from core.provider import ProviderRegistry
from core.provider_metadata import ProviderManifest, discover_provider_manifests


def _account_status(
    store: CredentialStore,
    provider_name: str,
    account: str,
    required_keys: list[str],
) -> str:
    if not required_keys:
        return "n/a"
    try:
        store.get(provider_name, account, required_keys=required_keys)
        return "ok"
    except MissingCredentialError:
        return "missing"


def build_context(
    bundled_dir: Path | None = None,
    user_dir: Path | None = None,
    media_type: str | None = None,
) -> dict[str, Any]:
    s = settings_mod.load()
    trusted_user_providers = set(s.trusted_user_providers)
    effective_user_dir = user_dir or host.user_providers_dir()

    reg = ProviderRegistry(bundled_dir=bundled_dir, user_dir=effective_user_dir)
    reg.discover(trusted_user_providers=trusted_user_providers)

    store = CredentialStore()
    flat_accounts = store.list_accounts()  # ["provider:account", ...]

    # Group accounts by provider name for the JSON output
    accounts_by_provider: dict[str, list[str]] = {}
    for entry in flat_accounts:
        if ":" not in entry:
            continue
        prov, acct = entry.split(":", 1)
        accounts_by_provider.setdefault(prov, []).append(acct)

    providers_out: list[dict[str, Any]] = []
    for info in reg.list(media_type=media_type):
        keys = [c.key for c in info.required_credentials]

        # Determine accounts to inspect for this provider
        provider_accounts = accounts_by_provider.get(info.name, [])

        if not keys:
            # Provider needs no credentials — always ok
            cred_status = "n/a"
            accounts_detail: list[dict[str, str]] = []
        elif not provider_accounts:
            # Needs credentials but vault has no accounts for this provider
            cred_status = "missing"
            accounts_detail = []
        else:
            accounts_detail = [
                {"name": acct, "status": _account_status(store, info.name, acct, keys)}
                for acct in sorted(provider_accounts)
            ]
            cred_status = "ok" if any(a["status"] == "ok" for a in accounts_detail) else "missing"

        providers_out.append(
            {
                "name": info.name,
                "display_name": info.display_name,
                "media_types": info.media_types,
                "capabilities": info.capabilities,
                "required_credentials": [
                    {"key": c.key, "description": c.description, "secret": c.secret}
                    for c in info.required_credentials
                ],
                "credential_status": cred_status,
                "accounts": accounts_detail,
                "source": info.source,
                "trusted": True,
                "trust_status": "trusted" if info.source == "user" else "bundled",
                "overrides_bundled": info.overrides_bundled,
            }
        )

    loaded_user_names = {
        provider["name"]
        for provider in providers_out
        if provider["source"] == "user" and provider["trusted"]
    }

    def _untrusted_provider_entry(manifest: ProviderManifest) -> dict[str, Any]:
        return {
            "name": manifest.name,
            "display_name": manifest.display_name,
            "media_types": manifest.media_types,
            "capabilities": manifest.capabilities,
            "required_credentials": [
                {
                    "key": str(c.get("key", "")),
                    "description": str(c.get("description", "")),
                    "secret": bool(c.get("secret", True)),
                }
                for c in manifest.required_credentials
            ],
            "credential_status": "unknown",
            "accounts": [],
            "source": "user",
            "trusted": False,
            "trust_status": "untrusted",
            "overrides_bundled": False,
            "trust_command": f"meti providers trust {manifest.name}",
        }

    for manifest in discover_provider_manifests(effective_user_dir, source="user"):
        if manifest.name in trusted_user_providers or manifest.name in loaded_user_names:
            continue
        if media_type and media_type not in manifest.media_types:
            continue
        providers_out.append(_untrusted_provider_entry(manifest))

    return {
        "providers": providers_out,
        "accounts": accounts_by_provider,
        "settings": {
            "default_mode": s.default_mode,
            "wizard_enabled": s.wizard_enabled,
            "auto_save_manifest": s.auto_save_manifest,
            "trusted_user_providers": sorted(s.trusted_user_providers),
        },
    }
