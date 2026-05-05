"""Host environment detection and XDG-compliant path resolution.

Single source of truth for any filesystem path that depends on user environment.
Pure functions: no mutation, no I/O beyond os.environ reads.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP = "mmp"


def user_data_dir() -> Path:
    """Resolve user config root: $XDG_CONFIG_HOME/mmp or ~/.config/mmp."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / _APP


def vault_path() -> Path:
    return user_data_dir() / "credentials.json.age"


def vault_key_path() -> Path:
    return user_data_dir() / "age-key.txt"


def user_providers_dir() -> Path:
    return user_data_dir() / "providers"


def settings_path() -> Path:
    return user_data_dir() / "settings.toml"


def runs_dir() -> Path:
    """Where run dirs are written. ENV override > skill-relative default."""
    env = os.environ.get("MMP_RUNS_DIR")
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
