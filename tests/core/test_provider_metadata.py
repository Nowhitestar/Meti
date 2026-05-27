from pathlib import Path

import pytest
import yaml

from core.provider_metadata import discover_provider_manifests, load_provider_manifest


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


def test_non_colon_entry_is_rejected(tmp_path: Path) -> None:
    provider_dir = _write_manifest(tmp_path, extra={"entry": "provider"})

    with pytest.raises(ValueError, match="module:ClassName"):
        load_provider_manifest(provider_dir, source="user")
