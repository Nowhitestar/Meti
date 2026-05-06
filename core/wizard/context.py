"""Build a JSON context object describing current wizard state.

Claude reads this (via `mmp wizard --dump-context`) to know which providers
are available, which accounts have credentials, and what the user's settings
say. The context is the bridge between Python state and Claude conversation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import settings as settings_mod
from core.credentials import CredentialStore
from core.errors import MissingCredentialError
from core.provider import ProviderRegistry


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
    reg = ProviderRegistry(bundled_dir=bundled_dir, user_dir=user_dir)
    s = settings_mod.load()
    # TODO(plan-4): pass trust_user from settings.trusted_user_providers
    # to enable third-party providers from ~/.config/mmp/providers/.
    reg.discover(trust_user=False)

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
            cred_status = (
                "ok" if any(a["status"] == "ok" for a in accounts_detail) else "missing"
            )

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
            }
        )

    return {
        "providers": providers_out,
        "accounts": accounts_by_provider,
        "settings": {
            "default_mode": s.default_mode,
            "wizard_enabled": s.wizard_enabled,
            "auto_save_manifest": s.auto_save_manifest,
        },
    }
