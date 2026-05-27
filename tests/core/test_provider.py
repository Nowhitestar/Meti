from pathlib import Path

import pytest
import yaml

from core.errors import ProviderNotFoundError
from core.provider import (
    ExecutionResult,
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
    info = next(i for i in reg.list() if i.name == "dup")
    assert info.source == "user"
    assert info.overrides_bundled is True


def test_selective_trusted_user_provider_loading(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()

    _write_provider_dir(bundled, name="bundled-only", snake="bundled_only")
    _write_provider_dir(user, name="trusted-one", snake="trusted_one")
    _write_provider_dir(
        user,
        name="untrusted-one",
        snake="untrusted_one",
        body="raise RuntimeError('untrusted provider imported')\n",
    )

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=user)
    reg.discover(trusted_user_providers={"trusted-one"})

    names = [info.name for info in reg.list()]
    assert "bundled-only" in names
    assert "trusted-one" in names
    assert "untrusted-one" not in names
    assert reg.resolve("trusted-one").name == "trusted-one"


def test_selective_user_provider_override_sets_info_flag(tmp_path):
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
    reg.discover(trusted_user_providers={"dup"})

    info = next(i for i in reg.list() if i.name == "dup")
    assert reg.resolve("dup").display_name == "user-version"
    assert info.source == "user"
    assert info.overrides_bundled is True


def test_filter_by_media_type(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="lf-only", snake="lf_only")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "x")
    reg.discover()

    longform = reg.list(media_type="longform")
    info = next(i for i in longform if i.name == "lf-only")
    assert info.overrides_bundled is False

    images = reg.list(media_type="image-post")
    assert all(i.name != "lf-only" for i in images)


def test_execution_result_stub_is_not_successful_platform_draft():
    result = ExecutionResult(status="ok", mode_actual="stub")
    assert result.status == "failed"
    assert result.error_code == "stub"
    assert result.error_kind == "review_needed"
    assert result.recoverable is True


def test_execution_result_partial_and_failed_needs_review_are_recoverable_failures():
    partial = ExecutionResult(status="ok", mode_actual="partial")
    review = ExecutionResult(status="ok", mode_actual="failed-needs-review")
    assert partial.status == "failed"
    assert partial.error_code == "partial"
    assert review.status == "failed"
    assert review.error_code == "failed_needs_review"


def test_execution_result_draft_platform_requires_evidence():
    result = ExecutionResult(status="ok", mode_actual="draft-platform")
    assert result.status == "failed"
    assert result.mode_actual == "failed-needs-review"
    assert result.error_code == "missing_draft_evidence"


def test_execution_result_draft_platform_with_evidence_stays_ok():
    result = ExecutionResult(
        status="ok",
        mode_actual="draft-platform",
        draft_url="https://example.com/drafts/1",
    )
    assert result.status == "ok"
    assert result.error_code is None


def test_bundled_provider_metadata_matches_provider_classes():
    reg = ProviderRegistry()
    reg.discover()

    assert reg.list()
    for info in reg.list():
        provider = reg.resolve(info.name)
        assert info.display_name == provider.display_name
        assert info.media_types == provider.media_types
        assert info.capabilities == provider.capabilities
        assert [c.key for c in info.required_credentials] == [
            c.key for c in provider.required_credentials
        ]
