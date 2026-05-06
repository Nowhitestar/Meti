from pathlib import Path

import pytest
import yaml

from core.errors import ProviderNotFoundError
from core.provider import (
    ProviderRegistry,
)


def _write_provider_dir(root: Path, name: str, snake: str, body: str | None = None) -> Path:
    """Write a fake provider package to disk and return its dir."""
    pdir = root / snake
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "display_name": name,
                "media_types": ["longform"],
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [{"key": "FAKE_KEY", "description": "x", "secret": True}],
                "entry": "provider:FakeProvider",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    pdir_body = (
        body
        or f'''
from core.provider import Provider
from core.rules import PlatformRules


class FakeProvider(Provider):
    name = "{name}"
    display_name = "{name}"
    media_types = ["longform"]
    capabilities = {{"draft": True, "publish": False, "schedule": False}}
    required_credentials = []
    platform_rules = PlatformRules()

    def validate(self, manifest, target):
        return None

    def prepare(self, manifest, target, run_dir):
        return None

    def execute(self, run_dir, target, mode, credentials):
        return None
'''
    )
    (pdir / "provider.py").write_text(pdir_body)
    return pdir


def test_registry_discovers_bundled(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="fake-one", snake="fake_one")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "no_user")
    reg.discover()

    info = reg.list()
    assert any(i.name == "fake-one" for i in info)


def test_registry_resolve_by_kebab_name(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="fake-two", snake="fake_two")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "no_user")
    reg.discover()

    p = reg.resolve("fake-two")
    assert p.name == "fake-two"


def test_resolve_missing_raises(tmp_path):
    reg = ProviderRegistry(bundled_dir=tmp_path / "empty", user_dir=tmp_path / "empty2")
    reg.discover()
    with pytest.raises(ProviderNotFoundError):
        reg.resolve("does-not-exist")


def test_user_provider_overrides_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()

    _write_provider_dir(bundled, name="dup", snake="dup_b")
    _write_provider_dir(
        user,
        name="dup",
        snake="dup_u",
        body=(
            "from core.provider import Provider\n"
            "from core.rules import PlatformRules\n"
            "class FakeProvider(Provider):\n"
            "    name = 'dup'\n"
            "    display_name = 'user-version'\n"
            "    media_types = ['longform']\n"
            "    capabilities = {'draft': True, 'publish': False, 'schedule': False}\n"
            "    required_credentials = []\n"
            "    platform_rules = PlatformRules()\n"
            "    def validate(self, m, t): return None\n"
            "    def prepare(self, m, t, r): return None\n"
            "    def execute(self, r, t, m, c): return None\n"
        ),
    )

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=user)
    reg.discover(trust_user=True)

    p = reg.resolve("dup")
    assert p.display_name == "user-version"


def test_filter_by_media_type(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="lf-only", snake="lf_only")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "x")
    reg.discover()

    longform = reg.list(media_type="longform")
    assert any(i.name == "lf-only" for i in longform)

    images = reg.list(media_type="image-post")
    assert all(i.name != "lf-only" for i in images)
