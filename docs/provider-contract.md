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

User providers under `~/.config/meti/providers/` are not loaded automatically
in v0.2. The `ProviderRegistry.discover()` defaults to `trust_user=False`,
so user folders are detected but skipped.

To load a user provider in v0.2, you must explicitly call
`ProviderRegistry.discover(trust_user=True)` from Python — primarily intended
for tests or power-user scripts. The CLI never enables trust automatically.

v0.3 will add:
- A first-encounter trust prompt
- `settings.toml.providers.trusted_user_providers` whitelist
- Optional signature verification

See `docs/safety-policy.md` for the full third-party provider policy.

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
