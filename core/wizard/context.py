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


def build_context(
    bundled_dir: Path | None = None,
    user_dir: Path | None = None,
    media_type: str | None = None,
) -> dict[str, Any]:
    reg = ProviderRegistry(bundled_dir=bundled_dir, user_dir=user_dir)
    s = settings_mod.load()
    reg.discover(trust_user=False)

    store = CredentialStore()
    accounts = store.list_accounts()

    providers_out: list[dict[str, Any]] = []
    for info in reg.list(media_type=media_type):
        # credential status
        if not info.required_credentials:
            cred_status = "n/a"
        else:
            keys = [c.key for c in info.required_credentials]
            try:
                store.get(info.name, "default", required_keys=keys)
                cred_status = "ok"
            except MissingCredentialError:
                cred_status = "missing"

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
                "source": info.source,
            }
        )

    return {
        "providers": providers_out,
        "accounts": accounts,
        "settings": {
            "default_mode": s.default_mode,
            "wizard_enabled": s.wizard_enabled,
            "auto_save_manifest": s.auto_save_manifest,
        },
    }
