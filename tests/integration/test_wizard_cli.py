import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _write_user_provider(
    xdg_root: Path,
    *,
    name: str,
    snake: str,
    body: str | None = None,
) -> Path:
    provider_dir = xdg_root / "meti" / "providers" / snake
    provider_dir.mkdir(parents=True, exist_ok=True)
    (provider_dir / "__init__.py").write_text("", encoding="utf-8")
    (provider_dir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "display_name": name,
                "media_types": ["longform"],
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [],
                "entry": "provider:P",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    (provider_dir / "provider.py").write_text(
        body
        or (
            "from core.provider import Provider\n"
            "from core.rules import PlatformRules\n"
            "class P(Provider):\n"
            f"    name='{name}'\n"
            f"    display_name='{name}'\n"
            "    media_types=['longform']\n"
            "    capabilities={'draft': True, 'publish': False, 'schedule': False}\n"
            "    required_credentials=[]\n"
            "    platform_rules=PlatformRules()\n"
            "    def validate(self,m,t): return None\n"
            "    def prepare(self,m,t,r): return None\n"
            "    def execute(self,r,t,m,c): return None\n"
        ),
        encoding="utf-8",
    )
    return provider_dir


def test_dump_context_returns_json(tmp_path):
    p = _run(
        "wizard",
        "--dump-context",
        env_extra={
            "METI_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert "providers" in data
    assert "accounts" in data
    assert "settings" in data
    assert "trusted_user_providers" in data["settings"]


def test_dump_context_filters_by_type(tmp_path):
    p = _run(
        "wizard",
        "--dump-context",
        "--type",
        "longform",
        env_extra={
            "METI_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0
    data = json.loads(p.stdout)
    for prov in data["providers"]:
        assert "longform" in prov["media_types"]


def test_commit_writes_run_dir(tmp_path):
    src = tmp_path / "m.yaml"
    src.write_text(
        'schema_version: "0.2"\n'
        "type: longform\n"
        'title: "X"\n'
        'body: "hi"\n'
        "mode: dry-run\n"
        "targets: [wechat-article]\n",
        encoding="utf-8",
    )
    p = _run(
        "wizard",
        "--commit",
        str(src),
        env_extra={
            "METI_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0, p.stderr
    assert "RUN_DIR" in p.stdout
    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "manifest.yaml").exists()
    assert (runs[0] / "manifest.lock.json").exists()


def test_providers_help_lists_provider_management() -> None:
    p = _run("--help")
    assert p.returncode == 0
    assert "providers" in p.stdout


def test_providers_trust_and_untrust_static_manifest_only(tmp_path):
    xdg = tmp_path / "xdg"
    _write_user_provider(
        xdg,
        name="local-demo",
        snake="local_demo",
        body="raise RuntimeError('provider.py imported')\n",
    )
    env = {"METI_RUNS_DIR": str(tmp_path / "runs"), "XDG_CONFIG_HOME": str(xdg)}

    trusted = _run("providers", "trust", "local-demo", env_extra=env)
    assert trusted.returncode == 0, trusted.stderr
    trusted_again = _run("providers", "trust", "local-demo", env_extra=env)
    assert trusted_again.returncode == 0, trusted_again.stderr

    settings_path = xdg / "meti" / "settings.toml"
    data = tomllib.loads(settings_path.read_text(encoding="utf-8"))
    assert data["providers"]["trusted_user_providers"] == ["local-demo"]

    untrusted = _run("providers", "untrust", "local-demo", env_extra=env)
    assert untrusted.returncode == 0, untrusted.stderr
    data = tomllib.loads(settings_path.read_text(encoding="utf-8"))
    assert data["providers"]["trusted_user_providers"] == []


def test_providers_trust_missing_does_not_mutate_settings(tmp_path):
    xdg = tmp_path / "xdg"
    env = {"METI_RUNS_DIR": str(tmp_path / "runs"), "XDG_CONFIG_HOME": str(xdg)}

    result = _run("providers", "trust", "missing-demo", env_extra=env)

    assert result.returncode == 2
    assert "missing-demo" in result.stderr
    assert not (xdg / "meti" / "settings.toml").exists()


def test_providers_list_shows_trust_state_without_importing_untrusted(tmp_path):
    xdg = tmp_path / "xdg"
    _write_user_provider(xdg, name="trusted-demo", snake="trusted_demo")
    _write_user_provider(
        xdg,
        name="untrusted-demo",
        snake="untrusted_demo",
        body="raise RuntimeError('untrusted provider imported')\n",
    )
    env = {"METI_RUNS_DIR": str(tmp_path / "runs"), "XDG_CONFIG_HOME": str(xdg)}

    trusted = _run("providers", "trust", "trusted-demo", env_extra=env)
    assert trusted.returncode == 0, trusted.stderr
    listed = _run("providers", "list", env_extra=env)

    assert listed.returncode == 0, listed.stderr
    assert "wechat-article  (bundled)" in listed.stdout
    assert "trusted-demo  (user trusted)" in listed.stdout
    assert "untrusted-demo  (user untrusted)" in listed.stdout
    assert "meti providers trust untrusted-demo" in listed.stdout
    legacy = _run("list", "providers", env_extra=env)
    assert legacy.returncode == 0
