from pathlib import Path
from typing import Any

import pytest
import yaml

from core.provider import Provider, ProviderRegistry
from core.provider_metadata import (
    ProviderManifest,
    discover_provider_manifests,
    load_provider_manifest,
)

BUNDLED_PROVIDER_DIR = Path(__file__).resolve().parents[2] / "providers"

# metadata exception list: keep empty unless a provider has a documented,
# temporary drift reason in docs/provider-contract.md.
METADATA_CONSISTENCY_EXCEPTIONS: dict[str, dict[str, str]] = {}


def _write_manifest(
    root: Path,
    *,
    name: str = "local-demo",
    snake: str = "local_demo",
    body: str = "raise RuntimeError('provider.py imported')\n",
    extra: dict | None = None,
) -> Path:
    provider_dir = root / snake
    provider_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "display_name": "Local Demo",
        "media_types": ["longform"],
        "capabilities": {"draft": True, "publish": False, "schedule": False},
        "required_credentials": [{"key": "LOCAL_TOKEN", "description": "x", "secret": True}],
        "entry": "provider:LocalDemoProvider",
        "schema_version": 1,
    }
    if extra:
        manifest.update(extra)
    (provider_dir / "provider.yaml").write_text(
        yaml.safe_dump(manifest),
        encoding="utf-8",
    )
    (provider_dir / "provider.py").write_text(body, encoding="utf-8")
    return provider_dir


def _valid_provider_body(name: str, display_name: str = "Local Demo") -> str:
    return f'''
from core.provider import CredentialSpec, Provider
from core.rules import PlatformRules


class LocalDemoProvider(Provider):
    name = "{name}"
    display_name = "{display_name}"
    media_types = ["longform"]
    capabilities = {{"draft": True, "publish": False, "schedule": False}}
    required_credentials = [CredentialSpec(key="LOCAL_TOKEN", description="x", secret=True)]
    platform_rules = PlatformRules()

    def validate(self, manifest, target):
        return None

    def prepare(self, manifest, target, run_dir):
        return None

    def execute(self, run_dir, target, mode, credentials):
        return None
'''


def _credential_dicts(provider: Provider) -> list[dict[str, Any]]:
    return [
        {
            "key": credential.key,
            "description": credential.description,
            "secret": credential.secret,
            "setup_hint": credential.setup_hint,
        }
        for credential in provider.required_credentials
    ]


def _manifest_credential_dicts(raw_credentials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": str(credential["key"]),
            "description": str(credential.get("description", "")),
            "secret": bool(credential.get("secret", True)),
            "setup_hint": str(credential.get("setup_hint", "")),
        }
        for credential in raw_credentials
    ]


def _assert_metadata_field(provider_name: str, field: str, actual: Any, expected: Any) -> None:
    if field in METADATA_CONSISTENCY_EXCEPTIONS.get(provider_name, {}):
        return
    assert actual == expected, f"{provider_name}.{field} drifted from provider.yaml"


def _assert_manifest_matches_provider(manifest: ProviderManifest, provider: Provider) -> None:
    _assert_metadata_field(manifest.name, "name", provider.name, manifest.name)
    _assert_metadata_field(
        manifest.name,
        "display_name",
        provider.display_name,
        manifest.display_name,
    )
    _assert_metadata_field(manifest.name, "media_types", provider.media_types, manifest.media_types)
    _assert_metadata_field(
        manifest.name,
        "capabilities",
        provider.capabilities,
        manifest.capabilities,
    )
    _assert_metadata_field(
        manifest.name,
        "required_credentials",
        _credential_dicts(provider),
        _manifest_credential_dicts(manifest.required_credentials),
    )
    _assert_metadata_field(manifest.name, "entry_module", manifest.module_name, "provider")
    _assert_metadata_field(
        manifest.name,
        "entry_class",
        provider.__class__.__name__,
        manifest.class_name,
    )
    _assert_metadata_field(manifest.name, "schema_version", manifest.schema_version, 1)


def test_load_provider_manifest_reads_yaml_without_importing_provider(tmp_path: Path) -> None:
    provider_dir = _write_manifest(tmp_path)

    manifest = load_provider_manifest(provider_dir, source="user")

    assert manifest.name == "local-demo"
    assert manifest.display_name == "Local Demo"
    assert manifest.media_types == ["longform"]
    assert manifest.required_credentials[0]["key"] == "LOCAL_TOKEN"
    assert manifest.entry == "provider:LocalDemoProvider"
    assert manifest.module_name == "provider"
    assert manifest.class_name == "LocalDemoProvider"
    assert manifest.schema_version == 1
    assert manifest.path == provider_dir
    assert manifest.source == "user"


def test_discover_provider_manifests_sorts_by_directory_name(tmp_path: Path) -> None:
    _write_manifest(tmp_path, name="zeta", snake="zeta")
    _write_manifest(tmp_path, name="alpha", snake="alpha")

    manifests = discover_provider_manifests(tmp_path, source="user")

    assert [manifest.name for manifest in manifests] == ["alpha", "zeta"]


def test_missing_required_manifest_key_names_the_key(tmp_path: Path) -> None:
    provider_dir = _write_manifest(tmp_path)
    data = yaml.safe_load((provider_dir / "provider.yaml").read_text(encoding="utf-8"))
    data.pop("entry")
    (provider_dir / "provider.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ValueError, match="entry"):
        load_provider_manifest(provider_dir, source="user")


def test_missing_schema_version_names_the_key(tmp_path: Path) -> None:
    provider_dir = _write_manifest(tmp_path)
    data = yaml.safe_load((provider_dir / "provider.yaml").read_text(encoding="utf-8"))
    data.pop("schema_version")
    (provider_dir / "provider.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        load_provider_manifest(provider_dir, source="user")


def test_non_colon_entry_is_rejected(tmp_path: Path) -> None:
    provider_dir = _write_manifest(tmp_path, extra={"entry": "provider"})

    with pytest.raises(ValueError, match="module:ClassName"):
        load_provider_manifest(provider_dir, source="user")


def test_registry_fails_when_entry_class_is_missing(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_manifest(
        bundled,
        body="class OtherProvider:\n    pass\n",
        extra={"entry": "provider:MissingProvider"},
    )

    registry = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "no_user")
    with pytest.raises(AttributeError, match="MissingProvider"):
        registry.discover()


def test_trusted_user_metadata_loads_without_importing_untrusted_providers(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write_manifest(
        bundled,
        name="bundled-only",
        snake="bundled_only",
        body=_valid_provider_body("bundled-only"),
    )
    _write_manifest(
        user,
        name="trusted-one",
        snake="trusted_one",
        body=_valid_provider_body("trusted-one"),
    )
    _write_manifest(
        user,
        name="untrusted-one",
        snake="untrusted_one",
        body="raise RuntimeError('untrusted provider imported')\n",
    )

    registry = ProviderRegistry(bundled_dir=bundled, user_dir=user)
    registry.discover(trusted_user_providers={"trusted-one"})

    names = [info.name for info in registry.list()]
    assert names == ["bundled-only", "trusted-one"]
    trusted_manifest = next(
        manifest
        for manifest in discover_provider_manifests(user, source="user")
        if manifest.name == "trusted-one"
    )
    _assert_manifest_matches_provider(trusted_manifest, registry.resolve("trusted-one"))


def test_trusted_user_metadata_consistency_fails_on_class_drift(tmp_path: Path) -> None:
    user = tmp_path / "user"
    user.mkdir()
    _write_manifest(
        user,
        name="trusted-one",
        snake="trusted_one",
        body=_valid_provider_body("trusted-one", display_name="Drifted Display Name"),
    )

    registry = ProviderRegistry(bundled_dir=tmp_path / "no_bundled", user_dir=user)
    registry.discover(trusted_user_providers={"trusted-one"})
    trusted_manifest = discover_provider_manifests(user, source="user")[0]

    with pytest.raises(AssertionError, match="display_name drifted"):
        _assert_manifest_matches_provider(trusted_manifest, registry.resolve("trusted-one"))


def test_bundled_provider_manifests_match_provider_classes() -> None:
    registry = ProviderRegistry()
    registry.discover()
    manifests = discover_provider_manifests(BUNDLED_PROVIDER_DIR, source="bundled")

    assert manifests
    assert METADATA_CONSISTENCY_EXCEPTIONS == {}
    for manifest in manifests:
        _assert_manifest_matches_provider(manifest, registry.resolve(manifest.name))
