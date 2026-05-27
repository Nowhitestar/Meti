# Browser-flow Provider Template

Use this template when the platform has no safe draft API, or the draft editor
requires web-only behavior. Browser-flow providers drive the user's real Chrome
through OpenCLI Bridge. They do not capture raw cookies or store browser session
files in Meti.

## Directory

```text
my_browser_platform/
├── __init__.py
├── provider.yaml
├── provider.py
├── rules.py
├── internal/
│   └── browser_flow.py
└── tests/
    └── test_provider.py
```

## `provider.yaml`

```yaml
name: my-browser-platform
display_name: My Browser Platform
media_types: [longform]
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials: []
entry: provider:ExampleBrowserProvider
schema_version: 1
```

Browser-flow providers usually keep `required_credentials: []` because login
state stays in the user's real Chrome profile. Do not add raw cookie, local
storage, or session-token credentials.

## `provider.py`

```python
from pathlib import Path

from core.provider import ExecutionResult, PreparedPayload, Provider, ValidationResult
from core.rules import PlatformRules

from .internal.browser_flow import create_draft


class ExampleBrowserProvider(Provider):
    name = "my-browser-platform"
    display_name = "My Browser Platform"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = []
    platform_rules = PlatformRules(title_max=120, body_max=20000)
    browser_login_url = "https://example.com/login"

    def validate(self, manifest, target):
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest, target, run_dir: Path):
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload_path = pack_dir / "content.md"
        payload_path.write_text(f"# {manifest.title}\n\n{manifest.body}", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(self, run_dir: Path, target, mode: str, credentials: dict[str, str]):
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run")
        if mode == "publish":
            raise NotImplementedError(
                "my-browser-platform publish is not supported; stop at draft review"
            )

        pack_dir = run_dir / "packs" / self.name
        try:
            draft_url = create_draft(pack_dir / "content.md")
        except RuntimeError as exc:
            todo = pack_dir / "TODO-connector.md"
            todo.write_text(str(exc), encoding="utf-8")
            return ExecutionResult(
                status="failed",
                mode_actual="stub",
                error_code="browser_flow_needs_review",
                error_kind="browser_flow",
                recoverable=True,
                manual_recovery=str(todo),
            )

        return ExecutionResult(
            status="ok",
            mode_actual="draft-platform",
            draft_url=draft_url,
        )
```

## `internal/browser_flow.py`

```python
from pathlib import Path

from core import browser


COMPOSE_URL = "https://example.com/new"
TITLE_SELECTORS = ["textarea[name='title']", "[data-testid='title']"]
BODY_SELECTORS = ["textarea[name='body']", "[contenteditable='true']"]
SAVE_DRAFT_SELECTORS = ["button[data-testid='save-draft']"]


def create_draft(content_path: Path) -> str:
    browser.open_url(COMPOSE_URL)
    diagnostic = browser.diagnose(platform_url=COMPOSE_URL)
    if not diagnostic.ready:
        raise RuntimeError("; ".join(diagnostic.next_actions) or diagnostic.message)

    content = content_path.read_text(encoding="utf-8")
    # Use existing core.browser/OpenCLI helpers here, isolate selector choices
    # as constants above, and stop at the platform's draft/review point.
    # Do not click final public publish controls.
    _ = content
    return "https://example.com/drafts/123"
```

Selectors belong in `internal/browser_flow.py` as constants so platform UI drift
is easy to patch. If the browser reaches an ambiguous state, return a recoverable
failure or manual fallback instead of guessing.

## Acceptance Tests

Provider-local tests should prove:

- `provider.yaml` has `required_credentials: []`.
- `browser_login_url` points to the platform login page.
- `execute(..., mode="dry-run")` does not open the browser.
- Browser helpers are mocked in automated tests.
- Draft success returns durable evidence: `draft_url` or `external_id`.
- Ambiguous browser states return a recoverable failure with manual fallback.

Browser-flow providers are draft-first. They must stop before final public
publish controls and leave review/publish decisions to the user.
