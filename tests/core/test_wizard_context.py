from pathlib import Path

import yaml

from core import settings
from core.wizard.context import build_context


def _write_provider(
    root: Path,
    name: str,
    snake: str,
    media_types: list[str],
    *,
    body: str | None = None,
) -> None:
    pdir = root / snake
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "display_name": name,
                "media_types": media_types,
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [],
                "entry": "provider:P",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    (pdir / "provider.py").write_text(
        body
        or (
            "from core.provider import Provider\n"
            "from core.rules import PlatformRules\n"
            "class P(Provider):\n"
            f"    name = '{name}'\n"
            f"    display_name = '{name}'\n"
            f"    media_types = {media_types}\n"
            "    capabilities = {'draft': True, 'publish': False, 'schedule': False}\n"
            "    required_credentials = []\n"
            "    platform_rules = PlatformRules()\n"
            "    def validate(self, m, t): return None\n"
            "    def prepare(self, m, t, r): return None\n"
            "    def execute(self, r, t, m, c): return None\n"
        )
    )


def test_context_lists_providers(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider(bundled, name="lf-only", snake="lf_only", media_types=["longform"])
    _write_provider(bundled, name="img-only", snake="img_only", media_types=["image-post"])

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled)
    assert any(p["name"] == "lf-only" for p in ctx["providers"])
    assert any(p["name"] == "img-only" for p in ctx["providers"])
    p = next(p for p in ctx["providers"] if p["name"] == "lf-only")
    assert p["source"] == "bundled"
    assert p["trusted"] is True
    assert p["trust_status"] == "bundled"
    assert p["overrides_bundled"] is False


def test_context_filters_by_type(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider(bundled, name="lf-only", snake="lf_only", media_types=["longform"])
    _write_provider(bundled, name="img-only", snake="img_only", media_types=["image-post"])

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled, media_type="longform")
    names = [p["name"] for p in ctx["providers"]]
    assert "lf-only" in names
    assert "img-only" not in names


def test_context_includes_accounts_and_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=tmp_path / "empty")
    assert "accounts" in ctx
    assert "settings" in ctx
    assert ctx["settings"]["default_mode"] == "draft"
    assert ctx["settings"]["trusted_user_providers"] == []


def test_context_marks_credential_status(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    pdir = bundled / "needy"
    pdir.mkdir()
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "needy",
                "display_name": "needy",
                "media_types": ["longform"],
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [{"key": "FOO", "description": "foo", "secret": True}],
                "entry": "provider:P",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    (pdir / "provider.py").write_text(
        "from core.provider import Provider\n"
        "from core.rules import PlatformRules\n"
        "class P(Provider):\n"
        "    name='needy'\n    display_name='needy'\n    media_types=['longform']\n"
        "    capabilities={'draft': True, 'publish': False, 'schedule': False}\n"
        "    required_credentials=[]\n    platform_rules=PlatformRules()\n"
        "    def validate(self,m,t): return None\n"
        "    def prepare(self,m,t,r): return None\n"
        "    def execute(self,r,t,m,c): return None\n"
    )
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled)
    p = next(p for p in ctx["providers"] if p["name"] == "needy")
    assert p["credential_status"] == "missing"


def test_context_per_account_credential_status(tmp_path, monkeypatch):
    """When the user has 'lewis' account configured but no 'default',
    the provider's overall status should reflect lewis being ok."""
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    pdir = bundled / "needy"
    pdir.mkdir()
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "needy",
                "display_name": "needy",
                "media_types": ["longform"],
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [{"key": "FOO", "description": "foo", "secret": True}],
                "entry": "provider:P",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    (pdir / "provider.py").write_text(
        "from core.provider import Provider\n"
        "from core.rules import PlatformRules\n"
        "class P(Provider):\n"
        "    name='needy'\n    display_name='needy'\n    media_types=['longform']\n"
        "    capabilities={'draft': True, 'publish': False, 'schedule': False}\n"
        "    required_credentials=[]\n    platform_rules=PlatformRules()\n"
        "    def validate(self,m,t): return None\n"
        "    def prepare(self,m,t,r): return None\n"
        "    def execute(self,r,t,m,c): return None\n"
    )
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Configure 'lewis' account (not 'default')
    from core.credentials import CredentialStore, FileBackend

    store = CredentialStore(backend=FileBackend())
    store.set("needy", "lewis", {"FOO": "bar"})

    ctx = build_context(bundled_dir=bundled)
    p = next(p for p in ctx["providers"] if p["name"] == "needy")

    # Provider-level: ok because at least one account has it
    assert p["credential_status"] == "ok"
    # Per-account list shows lewis specifically
    assert {"name": "lewis", "status": "ok"} in p["accounts"]
    # Top-level accounts dict has the per-provider grouping
    assert ctx["accounts"]["needy"] == ["lewis"]


def test_context_accounts_grouped_by_provider(tmp_path, monkeypatch):
    """Top-level accounts is a dict mapping provider name → list of account names."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    from core.credentials import CredentialStore, FileBackend

    store = CredentialStore(backend=FileBackend())
    store.set("p-one", "default", {"K": "v"})
    store.set("p-one", "alt", {"K": "v"})
    store.set("p-two", "default", {"K": "v"})

    ctx = build_context(bundled_dir=tmp_path / "no_bundled")
    accounts = ctx["accounts"]
    assert isinstance(accounts, dict)
    assert sorted(accounts["p-one"]) == ["alt", "default"]
    assert accounts["p-two"] == ["default"]


def test_context_includes_trusted_user_provider(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write_provider(bundled, name="bundled-only", snake="bundled_only", media_types=["longform"])
    _write_provider(user, name="trusted-one", snake="trusted_one", media_types=["longform"])

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    s = settings.load()
    s.trusted_user_providers = ["trusted-one"]
    settings.save(s)

    ctx = build_context(bundled_dir=bundled, user_dir=user)
    provider = next(p for p in ctx["providers"] if p["name"] == "trusted-one")
    assert provider["source"] == "user"
    assert provider["trusted"] is True
    assert provider["trust_status"] == "trusted"
    assert provider["overrides_bundled"] is False
    assert ctx["settings"]["trusted_user_providers"] == ["trusted-one"]


def test_context_includes_untrusted_user_provider_without_importing(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write_provider(bundled, name="bundled-only", snake="bundled_only", media_types=["longform"])
    _write_provider(
        user,
        name="untrusted-one",
        snake="untrusted_one",
        media_types=["longform"],
        body="raise RuntimeError('untrusted provider imported')\n",
    )

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled, user_dir=user)
    provider = next(p for p in ctx["providers"] if p["name"] == "untrusted-one")
    assert provider["source"] == "user"
    assert provider["trusted"] is False
    assert provider["trust_status"] == "untrusted"
    assert provider["credential_status"] == "unknown"
    assert provider["accounts"] == []
    assert provider["trust_command"] == "meti providers trust untrusted-one"


def test_context_marks_trusted_user_override(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write_provider(bundled, name="dup", snake="dup_b", media_types=["longform"])
    _write_provider(
        user,
        name="dup",
        snake="dup_u",
        media_types=["longform"],
        body=(
            "from core.provider import Provider\n"
            "from core.rules import PlatformRules\n"
            "class P(Provider):\n"
            "    name = 'dup'\n"
            "    display_name = 'user dup'\n"
            "    media_types = ['longform']\n"
            "    capabilities = {'draft': True, 'publish': False, 'schedule': False}\n"
            "    required_credentials = []\n"
            "    platform_rules = PlatformRules()\n"
            "    def validate(self, m, t): return None\n"
            "    def prepare(self, m, t, r): return None\n"
            "    def execute(self, r, t, m, c): return None\n"
        ),
    )

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    s = settings.load()
    s.trusted_user_providers = ["dup"]
    settings.save(s)

    ctx = build_context(bundled_dir=bundled, user_dir=user)
    providers = [p for p in ctx["providers"] if p["name"] == "dup"]
    assert len(providers) == 1
    assert providers[0]["source"] == "user"
    assert providers[0]["overrides_bundled"] is True
