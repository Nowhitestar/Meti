#!/usr/bin/env python3
"""Meti unified CLI entry.

Subcommands: validate, publish, setup, list, resume, doctor, wizard.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meti", description="Meti — one manifest, every platform")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub_validate = sub.add_parser("validate", help="Validate a manifest without executing")
    sub_validate.add_argument("manifest", help="Path to manifest.yaml")

    sub_publish = sub.add_parser("publish", help="Run prepare+execute for a manifest")
    sub_publish.add_argument("manifest", help="Path to manifest.yaml")
    sub_publish.add_argument(
        "--mode-override",
        choices=["dry-run", "draft", "publish"],
        default=None,
        help="Override manifest top-level mode (CAUTION with publish)",
    )

    sub_setup = sub.add_parser("setup", help="Configure credentials for a provider")
    sub_setup.add_argument("provider", help="Provider name (e.g. wechat-article)")
    sub_setup.add_argument("--account", default="default")

    sub_list = sub.add_parser("list", help="List providers / accounts / runs")
    sub_list.add_argument("kind", choices=["providers", "accounts", "runs"])

    sub_resume = sub.add_parser("resume", help="Resume a previously failed run")
    sub_resume.add_argument("run_dir")
    sub_resume.add_argument("--target", default=None)

    sub.add_parser("doctor", help="Self-check: vault, providers, health")

    sub_browser = sub.add_parser(
        "browser",
        help="Browser bridge status (uses your real Chrome via OpenCLI extension)",
    )
    sub_browser.add_argument(
        "action",
        choices=["status", "login", "doctor", "bind", "unbind"],
        help="status: extension connectivity check; "
        "bind: anchor meti to your CURRENT Chrome tab/window (run from a regular tab); "
        "unbind: detach meti without closing your tab; "
        "login: open provider's login URL in your Chrome (informational only — "
        "your Chrome session is what meti drives); "
        "doctor: full opencli diagnostic",
    )
    sub_browser.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="Provider name (required for login)",
    )

    sub_wizard = sub.add_parser("wizard", help="Conversational manifest wizard")
    sub_wizard.add_argument("--type", choices=["image-post", "longform", "video-post"])
    sub_wizard.add_argument("--targets", default=None, help="Comma-separated target names")
    sub_wizard.add_argument(
        "--dump-context",
        action="store_true",
        help="Dump current context as JSON for Claude to read",
    )
    sub_wizard.add_argument(
        "--commit",
        metavar="MANIFEST_PATH",
        default=None,
        help="Validate a manifest YAML and persist as a new run dir",
    )

    return p


def cmd_validate(args: argparse.Namespace) -> int:
    from core.errors import MetiError
    from core.manifest import load_manifest
    from core.provider import ProviderRegistry
    from core.rules import Severity, Violation

    try:
        m = load_manifest(args.manifest)
        reg = ProviderRegistry()
        reg.discover()
        all_violations = []
        for t in m.targets:
            provider = reg.resolve(t.name)
            # Capability gate: target.mode must be supported by provider
            cap_key = "publish" if t.mode == "publish" else ("draft" if t.mode == "draft" else None)
            if cap_key and not provider.capabilities.get(cap_key, False):
                all_violations.append(
                    Violation(
                        code="MODE_NOT_SUPPORTED",
                        message=(
                            f"provider does not support mode={t.mode} "
                            f"(caps={provider.capabilities})"
                        ),
                        severity=Severity.error,
                        target=t.name,
                        field_path="targets[].mode",
                    )
                )
                continue
            res = provider.validate(m, t)
            if res:
                all_violations.extend(res.violations)
        errs = [v for v in all_violations if v.severity.value == "error"]
        warns = [v for v in all_violations if v.severity.value == "warning"]
        for v in errs:
            print(f"ERROR  {v.target}  {v.code}  {v.message}", file=sys.stderr)
        for v in warns:
            print(f"WARN   {v.target}  {v.code}  {v.message}", file=sys.stderr)
        if errs:
            return 2
        print(f"OK  {len(m.targets)} targets validated.")
        return 0
    except MetiError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2


def cmd_publish(args: argparse.Namespace) -> int:
    from core import __version__
    from core.credentials import CredentialStore
    from core.errors import MetiError
    from core.manifest import load_manifest, write_lock
    from core.provider import ProviderRegistry
    from core.run import Run

    try:
        m = load_manifest(args.manifest)
        if args.mode_override:
            m.mode = args.mode_override
            for t in m.targets:
                t.mode = args.mode_override

        reg = ProviderRegistry()
        reg.discover()
        store = CredentialStore()

        run = Run.create(title=m.title, meti_version=__version__, host="cli", mode=m.mode)
        # Write a self-contained manifest: inline the body so the run dir
        # doesn't depend on the source dir for resume / forensics.
        import yaml as _yaml

        src_yaml = _yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
        src_yaml["body"] = m.body  # inlined / loaded content
        (run.dir / "manifest.yaml").write_text(
            _yaml.safe_dump(src_yaml, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        write_lock(m, run.dir)

        for t in m.targets:
            run.log("TARGET_START", target=t.name, account=t.account)
            try:
                provider = reg.resolve(t.name)
                cap_key = (
                    "publish" if t.mode == "publish" else ("draft" if t.mode == "draft" else None)
                )
                if cap_key and not provider.capabilities.get(cap_key, False):
                    run.add_target_result(
                        name=t.name,
                        account=t.account,
                        status="failed",
                        mode_actual="dry-run",
                        error=f"capability: provider does not support mode={t.mode}",
                    )
                    run.log("CAPABILITY_FAIL", target=t.name, mode=t.mode)
                    continue
                v_res = provider.validate(m, t)
                errs = [
                    v for v in (v_res.violations if v_res else []) if v.severity.value == "error"
                ]
                if errs:
                    run.add_target_result(
                        name=t.name,
                        account=t.account,
                        status="failed",
                        mode_actual="dry-run",
                        error=f"validation: {[v.code for v in errs]}",
                        violations=[v.__dict__ for v in errs],
                    )
                    run.log("VALIDATE_FAIL", target=t.name, codes=[v.code for v in errs])
                    continue

                provider.prepare(m, t, run.dir)
                run.log("PREPARE_OK", target=t.name)

                creds: dict[str, str] = {}
                if t.mode != "dry-run":
                    required = [c.key for c in provider.required_credentials]
                    if required:
                        # Only consult the vault when the provider actually needs creds.
                        # Providers with empty required_credentials (e.g. local-only flows)
                        # get an empty creds dict.
                        creds = store.get(t.name, t.account, required_keys=required)

                exec_res = provider.execute(run.dir, t, t.mode, creds)
                run.add_target_result(
                    name=t.name,
                    account=t.account,
                    status=exec_res.status,
                    mode_actual=exec_res.mode_actual,
                    external_id=exec_res.external_id,
                    draft_url=exec_res.draft_url,
                )
                run.log(
                    "EXECUTE_OK",
                    target=t.name,
                    mode_actual=exec_res.mode_actual,
                    external_id=exec_res.external_id,
                )
            except Exception as exc:
                run.add_target_result(
                    name=t.name,
                    account=t.account,
                    status="failed",
                    mode_actual=t.mode,
                    error=str(exc),
                )
                run.log("TARGET_FAIL", target=t.name, error=str(exc))

        run.finalize()
        print(f"RUN_DIR  {run.dir}")
        _print_publish_checklist(run.targets)
        return 0
    except MetiError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2


# Per-provider hints for the "next step" line in the publish checklist.
_NEXT_STEP_LABELS = {
    "wechat-article": "review at the URL above; click 发表 in MP when ready",
    "wechat-image": "draft saved to your 草稿箱; click 发表 when ready",
    "xiaohongshu": "draft saved; finalize in 创作服务平台 → 草稿箱",
    "x-article": "X auto-saved; click Publish when ready",
    "substack": "Substack auto-saved; click Publish when ready",
}


def _print_publish_checklist(targets) -> None:
    """Print a per-target action checklist after a publish run.

    By contract, meti drafts; the user reviews and clicks the platform's
    own publish/save button. The checklist surfaces each draft URL and
    the corresponding next-step instruction.
    """
    if not targets:
        return
    okays = [t for t in targets if t.status == "ok"]
    fails = [t for t in targets if t.status != "ok"]
    if okays:
        print(f"\n{len(okays)} draft(s) staged:\n")
        for t in okays:
            mode_tag = {
                "draft-platform": "platform draft",
                "draft-local": "local draft",
                "stub": "stub (manual)",
                "dry-run": "dry-run only",
            }.get(t.mode_actual, t.mode_actual)
            url = t.draft_url or "(no URL)"
            label = _NEXT_STEP_LABELS.get(t.name, "review and finalize in your browser")
            print(f"  ✓ {t.name:<18} [{mode_tag}]")
            print(f"    {url}")
            print(f"    → {label}")
    if fails:
        print(f"\n{len(fails)} target(s) failed:\n")
        for t in fails:
            print(f"  ✗ {t.name}: {t.error}")
    print("\nMeti drafts; you publish. Tabs are left open by design.")


def cmd_setup(args: argparse.Namespace) -> int:
    from core.credentials import CredentialStore
    from core.provider import ProviderRegistry

    reg = ProviderRegistry()
    reg.discover()
    try:
        provider = reg.resolve(args.provider)
    except Exception as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2

    store = CredentialStore()
    values: dict[str, str] = {}
    print(
        f"Configure {args.provider} (account: {args.account}). "
        "Press Enter to skip a key.\n"
        "(For Claude-driven setup, see core/wizard/credential_setup.md.)"
    )
    for spec in provider.required_credentials:
        prompt = f"  {spec.key}"
        if spec.description:
            prompt += f" ({spec.description})"
        if spec.setup_hint:
            prompt += f"  hint: {spec.setup_hint}"
        prompt += ": "
        if spec.secret:
            import getpass

            v = getpass.getpass(prompt)
        else:
            v = input(prompt)
        if v:
            values[spec.key] = v
    if values:
        store.set(args.provider, args.account, values)
        print(f"OK  saved {len(values)} keys to vault.")
    else:
        print("nothing to save.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if args.kind == "providers":
        from core.provider import ProviderRegistry

        reg = ProviderRegistry()
        reg.discover()
        for info in reg.list():
            caps = ",".join(k for k, v in info.capabilities.items() if v)
            print(f"  {info.name}  ({info.source})  media={info.media_types}  caps={caps}")
    elif args.kind == "accounts":
        from core.credentials import CredentialStore

        store = CredentialStore()
        for acc in store.list_accounts():
            print(f"  {acc}")
    elif args.kind == "runs":
        from core import host as h

        rd = h.runs_dir()
        if rd.exists():
            for d in sorted(rd.iterdir()):
                if d.is_dir():
                    print(f"  {d.name}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Re-execute targets that didn't reach status=ok in a previous run.

    v0.3 baseline: target-level resume. Re-runs `prepare + execute` for any
    target whose previous status was failed/skipped/partial. Targets already
    at status=ok are skipped (logged as RESUME_SKIP).

    Future (v0.4+): step-level resume using `Run.checkpoint()` for finer
    granularity (e.g. skip already-uploaded thumbs).
    """
    import json

    from core.credentials import CredentialStore
    from core.errors import MetiError
    from core.manifest import load_manifest
    from core.provider import ProviderRegistry
    from core.run import Run

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"ERROR  run dir not found: {run_dir}", file=sys.stderr)
        return 2

    manifest_path = run_dir / "manifest.yaml"
    result_path = run_dir / "result.json"
    if not manifest_path.exists() or not result_path.exists():
        print(
            f"ERROR  run dir missing manifest.yaml or result.json: {run_dir}",
            file=sys.stderr,
        )
        return 2

    try:
        m = load_manifest(manifest_path)
        prev_result = json.loads(result_path.read_text(encoding="utf-8"))
        prev_targets = {t["name"]: t for t in prev_result.get("targets", [])}

        run = Run.from_dir(run_dir)
        run.log("RESUME_START", run_id=run.run_id, run_dir=str(run_dir))

        reg = ProviderRegistry()
        reg.discover()
        store = CredentialStore()

        only = set(args.target.split(",")) if args.target else None

        for t in m.targets:
            if only and t.name not in only:
                continue
            prev = prev_targets.get(t.name, {})
            prev_status = prev.get("status")
            if prev_status == "ok":
                run.log("RESUME_SKIP", target=t.name, reason="already-ok")
                # Carry forward the previous successful result so finalize()
                # writes a coherent result.json (don't lose the external_id).
                run.add_target_result(
                    name=prev.get("name", t.name),
                    account=prev.get("account", t.account),
                    status="ok",
                    mode_actual=prev.get("mode_actual", "dry-run"),
                    external_id=prev.get("external_id"),
                    draft_url=prev.get("draft_url"),
                )
                continue

            run.log("RESUME_RETRY", target=t.name, prev_status=prev_status)
            try:
                provider = reg.resolve(t.name)
                cap_key = (
                    "publish" if t.mode == "publish" else ("draft" if t.mode == "draft" else None)
                )
                if cap_key and not provider.capabilities.get(cap_key, False):
                    run.add_target_result(
                        name=t.name,
                        account=t.account,
                        status="failed",
                        mode_actual="dry-run",
                        error=f"capability: provider does not support mode={t.mode}",
                    )
                    run.log("CAPABILITY_FAIL", target=t.name, mode=t.mode)
                    continue

                provider.prepare(m, t, run.dir)
                run.log("PREPARE_OK", target=t.name)

                creds: dict[str, str] = {}
                if t.mode != "dry-run":
                    required = [c.key for c in provider.required_credentials]
                    if required:
                        creds = store.get(t.name, t.account, required_keys=required)

                exec_res = provider.execute(run.dir, t, t.mode, creds)
                run.add_target_result(
                    name=t.name,
                    account=t.account,
                    status=exec_res.status,
                    mode_actual=exec_res.mode_actual,
                    external_id=exec_res.external_id,
                    draft_url=exec_res.draft_url,
                )
                run.log(
                    "EXECUTE_OK",
                    target=t.name,
                    mode_actual=exec_res.mode_actual,
                    external_id=exec_res.external_id,
                )
            except Exception as exc:
                run.add_target_result(
                    name=t.name,
                    account=t.account,
                    status="failed",
                    mode_actual=t.mode,
                    error=str(exc),
                )
                run.log("TARGET_FAIL", target=t.name, error=str(exc))

        run.finalize()
        print(f"RUN_DIR  {run.dir}")
        _print_publish_checklist(run.targets)
        return 0
    except MetiError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2


def cmd_doctor(args: argparse.Namespace) -> int:
    from core import host as h
    from core.credentials import CredentialStore
    from core.provider import ProviderRegistry

    print(f"host: {h.detect_host()}")
    print(f"vault: {h.vault_path()}  exists={h.vault_path().exists()}")
    reg = ProviderRegistry()
    reg.discover()
    print(f"providers: {len(reg.list())}")
    store = CredentialStore()
    print(f"accounts: {len(store.list_accounts())}")
    return 0


def cmd_wizard(args: argparse.Namespace) -> int:
    if args.dump_context:
        from core.wizard.context import build_context

        ctx = build_context(media_type=args.type)
        print(json.dumps(ctx, indent=2, ensure_ascii=False))
        return 0
    if args.commit:
        from core.errors import MetiError
        from core.wizard.commit import commit_manifest

        try:
            run_dir = commit_manifest(args.commit)
            print(f"RUN_DIR  {run_dir}")
            return 0
        except MetiError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 2
    # interactive (no flags) — Claude is expected to drive via SKILL.md prompts
    print(
        "wizard interactive mode is driven by Claude reading core/wizard/*.md.\n"
        "Run with --dump-context to fetch state, or --commit <path> to persist a manifest.",
        file=sys.stderr,
    )
    return 1


def cmd_browser(args: argparse.Namespace) -> int:
    """Browser bridge status & login pointer.

    The OpenCLI Chrome extension drives the user's real Chrome, so meti
    no longer manages session state. ``login`` just navigates to the
    provider's login URL — the user logs in normally in Chrome, meti
    detects logged-in state via the extension on subsequent runs.
    """
    from core import browser as br
    from core.errors import MetiError
    from core.provider import ProviderRegistry

    action = args.action

    if action == "doctor":
        result = br.doctor()
        if result["stdout"]:
            print(result["stdout"])
        if result["stderr"]:
            print(result["stderr"], file=sys.stderr)
        return 0 if result["ok"] else 2

    if action == "status":
        try:
            connected = br.is_connected()
        except br.BrowserNotInstalledError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 2
        if not connected:
            print(
                "✖  Browser Bridge extension not connected.\n"
                "Install: https://chromewebstore.google.com/detail/opencli/"
                "ildkmabpimmkaediidaifkhjpohdnifk\n"
                "Then make sure Chrome is open and the extension is enabled.",
                file=sys.stderr,
            )
            return 2
        bound = br.is_bound()
        print(f"OK  Browser Bridge connected. Workspace `{br.WORKSPACE}` bound: {bound}")
        if bound:
            try:
                tabs = br.tab_list()
                print(f"    {len(tabs)} tab(s) in the bound window")
                for t in tabs[:5]:
                    print(f"      - {t.get('url', '?')[:90]}")
            except br.MetiError as e:
                print(f"    (could not list tabs: {e})")
        else:
            print("    Run `meti browser bind` from a Chrome tab to anchor meti there.")
        return 0

    if action == "bind":
        try:
            br.bind()
        except br.MetiError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 2
        try:
            tabs = br.tab_list()
            current = next((t for t in tabs if t.get("active")), None) or (tabs[0] if tabs else {})
            url = current.get("url", "?")
        except br.MetiError:
            url = "(unknown)"
        print(f"OK  Bound `{br.WORKSPACE}` to your Chrome window.")
        print(f"    Current tab: {url}")
        print("    Subsequent meti operations will run in this window.")
        return 0

    if action == "unbind":
        br.unbind()
        print(f"OK  Detached `{br.WORKSPACE}`. Your Chrome tab(s) are untouched.")
        return 0

    if action == "login":
        if not args.provider:
            print("ERROR  `meti browser login` requires a provider name", file=sys.stderr)
            return 2
        reg = ProviderRegistry()
        reg.discover()
        try:
            provider = reg.resolve(args.provider)
        except MetiError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 2
        login_url = getattr(provider, "browser_login_url", None)
        if not login_url:
            print(
                f"ERROR  provider {args.provider!r} has no browser_login_url; "
                f"this provider doesn't use a browser session.",
                file=sys.stderr,
            )
            return 2
        try:
            br.open_url(login_url)
        except br.MetiError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 2
        print(f"OK  Opened {login_url} in your Chrome.")
        print(
            "  Log in normally if you aren't already. meti uses your real Chrome\n"
            "  session; no separate state to manage."
        )
        return 0

    print(f"ERROR  unknown browser action: {action}", file=sys.stderr)
    return 2


_DISPATCH = {
    "validate": cmd_validate,
    "publish": cmd_publish,
    "setup": cmd_setup,
    "list": cmd_list,
    "resume": cmd_resume,
    "doctor": cmd_doctor,
    "wizard": cmd_wizard,
    "browser": cmd_browser,
}


def main(argv: list[str] | None = None) -> int:
    p = _build_parser()
    args = p.parse_args(argv)
    return _DISPATCH[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
