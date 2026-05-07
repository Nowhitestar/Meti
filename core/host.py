"""Host environment detection and XDG-compliant path resolution.

Single source of truth for any filesystem path that depends on user environment.
Pure functions: no mutation, no I/O beyond os.environ reads (and a one-shot
legacy-path migration on first call).
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

_APP = "meti"
_LEGACY_APP = "mmp"  # pre-rebrand name, kept for one-shot migration


def _migrate_legacy_dir(base: Path) -> None:
    """If the old ``~/.config/mmp/`` exists and the new ``~/.config/meti/``
    does not, rename it in place. One-shot, idempotent.
    """
    legacy = base / _LEGACY_APP
    target = base / _APP
    if legacy.exists() and not target.exists():
        try:
            legacy.rename(target)
        except OSError:
            # Permission / cross-device issues — leave both, let caller see
            # the new dir as empty and re-init. Don't fail boot.
            pass


def user_data_dir() -> Path:
    """Resolve user config root: $XDG_CONFIG_HOME/meti or ~/.config/meti.

    Auto-migrates from the pre-rebrand ``~/.config/mmp/`` on first call
    if the new dir doesn't exist yet.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    _migrate_legacy_dir(base)
    return base / _APP


def vault_path() -> Path:
    return user_data_dir() / "credentials.json.age"


def vault_key_path() -> Path:
    return user_data_dir() / "age-key.txt"


def user_providers_dir() -> Path:
    return user_data_dir() / "providers"


def settings_path() -> Path:
    return user_data_dir() / "settings.toml"


def _env_with_legacy(name: str, legacy_name: str) -> str | None:
    """Read ``name`` from env, falling back to ``legacy_name`` with a
    one-time DeprecationWarning.
    """
    val = os.environ.get(name)
    if val:
        return val
    legacy_val = os.environ.get(legacy_name)
    if legacy_val:
        warnings.warn(
            f"{legacy_name} is deprecated; rename to {name}.",
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy_val
    return None


def runs_dir() -> Path:
    """Where run dirs are written. ENV override > skill-relative default.

    Reads ``METI_RUNS_DIR``; falls back to ``MMP_RUNS_DIR`` (deprecated)
    for one release.
    """
    env = _env_with_legacy("METI_RUNS_DIR", "MMP_RUNS_DIR")
    if env:
        return Path(env)
    # default: <skill_root>/runs
    return Path(__file__).resolve().parent.parent / "runs"


def detect_host() -> str:
    """Best-effort host detection. Used only for telemetry in result.json."""
    if os.environ.get("CLAUDE_CODE_VERSION") or os.environ.get("CLAUDECODE"):
        return "claude-code"
    if os.environ.get("OPENCLAW_VERSION") or Path.home().joinpath(".openclaw").exists():
        return "openclaw"
    return "unknown"
