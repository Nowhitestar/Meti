from pathlib import Path

import yaml

from core.wizard.context import build_context


def _write_provider(root: Path, name: str, snake: str, media_types: list[str]) -> None:
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
