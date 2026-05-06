"""Load and render markdown prompt fragments for the wizard.

Templating: tiny {{var}} substitution, KeyError on missing var. Not Jinja —
prompts should stay simple and human-editable.
"""

from __future__ import annotations

import re
from pathlib import Path

_STAGES = ["source_extraction", "target_selection", "manifest_assembly", "credential_setup"]
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FRAGMENT_DIR = Path(__file__).resolve().parent


def list_stages() -> list[str]:
    return list(_STAGES)


def render(stage_or_path: str | Path, **vars: object) -> str:
    if isinstance(stage_or_path, Path):
        path = stage_or_path
    else:
        path = _FRAGMENT_DIR / f"{stage_or_path}.md"
    text = path.read_text(encoding="utf-8")

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in vars:
            raise KeyError(f"missing wizard variable: {key}")
        return str(vars[key])

    return _PLACEHOLDER.sub(_sub, text)
