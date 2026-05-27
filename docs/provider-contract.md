# Writing a Provider

A provider is a directory containing `provider.yaml` + a Python module that
implements the `Provider` ABC.

## Where it lives

- **Bundled** (first-party): `providers/<snake_name>/`
- **User** (third-party): `~/.config/meti/providers/<snake_name>/`

The directory name uses snake_case (Python module name). The
`provider.yaml.name` is the kebab-case identifier referenced in manifests
and pack folders.

## Required files

```
<snake_name>/
├── __init__.py
├── provider.yaml
├── provider.py
├── rules.py        # optional: platform rules
└── tests/          # optional but encouraged
```

## Copyable templates

- `docs/provider-api-template.md` - API-flow provider with explicit
  credentials, `CredentialSpec`, `health_check()`, dry-run behavior, draft
  execution, and `ProviderExecutionError` wrapping.
- `docs/provider-browser-template.md` - browser-flow provider using OpenCLI
  Bridge, `browser_login_url`, selector isolation in `internal/browser_flow.py`,
  no raw cookie capture, and draft-first stopping points.

## `provider.yaml`

```yaml
name: my-platform                      # kebab-case; appears in manifests
display_name: My Platform              # human-readable
media_types: [longform]                # subset of {image-post, longform, video-post}
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: MYPLATFORM_TOKEN
    description: "API token"
    secret: true
    setup_hint: "Get one from https://..."
entry: provider:MyPlatformProvider     # python_module:ClassName, relative to the dir
schema_version: 1
```

`provider.yaml` is public metadata, but the provider class is the behavior
source of truth. For bundled providers, `name`, `display_name`, `media_types`,
`capabilities`, `required_credentials`, `entry`, and `schema_version` must be
machine-checkable against the class attributes. Default pytest includes a
consistency guard for those fields.

Browser-flow providers normally declare `required_credentials: []` because
authentication lives in the user's real Chrome session through OpenCLI Bridge.
Do not add raw cookie/token keys such as browser session cookies unless the
provider class actually reads those keys and the credential storage risk is
explicitly documented.

## `provider.py`

Implement `Provider` from `core.provider`. Methods you must define:

```python
class MyPlatformProvider(Provider):
    name = "my-platform"
    display_name = "My Platform"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [...]       # CredentialSpec list
    platform_rules = MY_RULES          # PlatformRules instance

    def validate(self, manifest, target) -> ValidationResult: ...
    def prepare(self, manifest, target, run_dir) -> PreparedPayload: ...
    def execute(self, run_dir, target, mode, credentials) -> ExecutionResult: ...
    def health_check(self, credentials) -> HealthStatus: ...   # optional
```

### `validate(manifest, target) -> ValidationResult`

- Run `self.platform_rules.lint(manifest, self.name)` and wrap in
  `ValidationResult(violations=...)`.
- Optional: append your own checks beyond `PlatformRules`.

### `prepare(manifest, target, run_dir) -> PreparedPayload`

- Write `<run_dir>/packs/<self.name>/payload.json` with what your `execute`
  step needs.
- Optional: also write `content.md`, screenshots, browser-flow guides.
- Return a `PreparedPayload(pack_dir=..., payload_path=...)`.

### `execute(run_dir, target, mode, credentials) -> ExecutionResult`

- `mode` is one of `dry-run`, `draft`, `publish`.
- For `dry-run`, do nothing real; return
  `ExecutionResult(status="ok", mode_actual="dry-run")`.
- For `draft`, perform the platform-side draft action; return
  `ExecutionResult(status="ok", mode_actual="draft-platform" | "draft-local",
  external_id=...)`.
- For `publish`, raise `NotImplementedError` unless your provider explicitly
  supports it AND you have re-confirmed with the user.

Wrap upstream failures in `ProviderExecutionError(target=..., step=...,
upstream=exc, retryable=True/False)`. The framework writes a checkpoint and
allows `meti resume`.

### `health_check(credentials) -> HealthStatus`

Return `HealthStatus.ok | failed | unknown`. Used by `meti doctor` and the
wizard to surface "your token works" before a run starts.

## `rules.py`

```python
from core.rules import PlatformRules, Severity, Violation

def _custom_lint(manifest, target_name):
    # ...
    return [Violation(code="MY_CHECK", message="...", severity=Severity.warning)]

MY_RULES = PlatformRules(
    title_max=100,
    body_max=10000,
    cover_required=False,
    extra_lints=[_custom_lint],
)
```

## Trust model for user-installed providers

User providers under `~/.config/meti/providers/` are not loaded automatically.
They are arbitrary Python, so Meti static-scans `provider.yaml` first and only
imports user code after explicit trust.

Inspect what Meti can see:

```bash
meti providers list
```

Trust a user provider by its `provider.yaml.name`:

```bash
meti providers trust my-platform
```

This writes the manifest name to
`settings.toml.providers.trusted_user_providers`. Remove trust with:

```bash
meti providers untrust my-platform
```

The wizard and registry reuse the same whitelist. Untrusted user providers may
be shown as discovered, but their `provider.py` is not imported. Trusted user
providers stay in the same manifest target namespace, so a trusted user
provider with the same `name` as a bundled provider intentionally overrides the
bundled one and is reported as `overrides_bundled`.

Future hardening may add a first-encounter trust prompt or optional signature
verification.

See `docs/safety-policy.md` for the full third-party provider policy.

## Metadata drift exceptions

Metadata/class drift should not be silent. If a provider intentionally differs
from its `provider.yaml`, add an explicit test exception with provider name,
field, reason, and revisit note, and document the same metadata exception here.
Current bundled providers should not rely on exceptions.

## Testing

Put tests under `<your-dir>/tests/`. Pytest auto-discovers them when run from
the project root. The reference shape:

```python
import json
from core.manifest import Manifest, Target
from providers.my_platform.provider import MyPlatformProvider

def test_validate_passes():
    p = MyPlatformProvider()
    m = Manifest(...)
    res = p.validate(m, m.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)
```
