# API-flow Provider Template

Use this template when a platform exposes a real draft API and authentication
uses explicit API credentials. Keep the provider small: one directory, one class,
optional rules, optional internal client helpers, and provider-local tests.

## Directory

```text
my_platform/
├── __init__.py
├── provider.yaml
├── provider.py
├── rules.py
└── tests/
    └── test_provider.py
```

## `provider.yaml`

```yaml
name: my-platform
display_name: My Platform
media_types: [longform]
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: MY_PLATFORM_TOKEN
    description: "API token"
    secret: true
    setup_hint: "Create one in My Platform -> Developer settings"
entry: provider:ExampleApiProvider
schema_version: 1
```

## `provider.py`

```python
from pathlib import Path

from core.errors import ProviderExecutionError
from core.provider import (
    CredentialSpec,
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from core.rules import PlatformRules


class ExampleApiProvider(Provider):
    name = "my-platform"
    display_name = "My Platform"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="MY_PLATFORM_TOKEN",
            description="API token",
            secret=True,
            setup_hint="Create one in My Platform -> Developer settings",
        )
    ]
    platform_rules = PlatformRules(title_max=120, body_max=20000)

    def validate(self, manifest, target):
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest, target, run_dir: Path):
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(
            '{"title": %r, "body": %r}' % (manifest.title, manifest.body),
            encoding="utf-8",
        )
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(self, run_dir: Path, target, mode: str, credentials: dict[str, str]):
        if mode == "dry-run":
            # No upstream write, no network side effect.
            return ExecutionResult(status="ok", mode_actual="dry-run")
        if mode == "publish":
            raise NotImplementedError(
                "my-platform publish is not supported; use draft and confirm manually"
            )

        try:
            # Call your upstream draft API here. Return durable evidence from
            # the platform, not only "request succeeded".
            draft_id = "draft_123"
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name,
                step="create_draft",
                upstream=exc,
                retryable=True,
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-platform",
            external_id=draft_id,
        )

    def health_check(self, credentials: dict[str, str]):
        token = credentials.get("MY_PLATFORM_TOKEN")
        if not token:
            return HealthStatus.failed
        # Optionally call a cheap account endpoint. Never print the token.
        return HealthStatus.unknown
```

## `rules.py`

```python
from core.rules import PlatformRules, Severity, Violation


def _custom_lint(manifest, target_name):
    if "forbidden" in manifest.title.lower():
        return [
            Violation(
                code="TITLE_FORBIDDEN_WORD",
                message="Title contains a forbidden word",
                severity=Severity.error,
                target=target_name,
                field_path="title",
            )
        ]
    return []


MY_RULES = PlatformRules(
    title_max=120,
    body_max=20000,
    extra_lints=[_custom_lint],
)
```

## Acceptance Tests

Provider-local tests should prove:

- `validate()` returns no error for a minimal valid manifest.
- `prepare()` writes `packs/<provider>/payload.json`.
- `execute(..., mode="dry-run")` returns `mode_actual="dry-run"` and performs no upstream write.
- `execute(..., mode="draft")` wraps upstream failures as `ProviderExecutionError`.
- `health_check()` returns `HealthStatus.ok`, `failed`, or `unknown` without leaking credentials.

Public publish remains unsupported unless a future provider intentionally adds
`capabilities.publish: true` and preserves the active confirmation gate in
`docs/safety-policy.md`.
