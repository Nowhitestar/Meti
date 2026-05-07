# Wizard Stage 3 — Manifest Assembly

You now have a Stage 1 draft and a Stage 2 target list. Time to render the
manifest, validate it, get user approval, and persist.

## Goal of this stage

1. Render `manifest.yaml` from collected info.
2. Validate via `python3 scripts/meti.py validate <tmp>`.
3. Show the user the rendered YAML AND the violation report.
4. On approval, commit via `python3 scripts/meti.py wizard --commit <path>`.

## Render rules

- Always include `schema_version: "0.2"` at the top.
- Use full-form targets when modes/accounts/options differ; short-form (string)
  when all defaults apply.
- For body: if the user pasted file content, write the file out to a sibling
  path and reference it with `./<file>.md`. If body is short and inline, embed.
- Cover and images: keep absolute paths if user gave absolute; otherwise
  relative to the manifest file.

## Validation flow

1. Write the rendered YAML to a temp path:

   ```bash
   tmp=$(mktemp -d)/manifest.yaml
   # write yaml content to $tmp
   ```

2. Run validate:

   ```bash
   python3 scripts/meti.py validate "$tmp"
   ```

3. Parse the output:
   - Exit 0 + "OK" → green light.
   - Exit 2 with "ERROR" lines → blocking violations; surface each as
     "violation: <code> — <message>" and tell the user how to fix.
   - Lines starting with "WARN" → soft warnings; show them but allow continue.

## Approval gate

Show the user:

```
Manifest:
<rendered yaml>

Validation: <OK | N errors, M warnings>
[errors and warnings listed]

Confirm? (y/n/edit)
```

- `y` → commit.
- `n` → return to Stage 2 to revise targets, or Stage 1 to revise content.
- `edit` → ask which field to change, modify, re-render, re-validate.

## Publish-mode safety gate

If ANY target has `mode: publish`, after the user says `y`, ask one more time:

> The following targets will publish PUBLICLY (not just draft):
>   - wechat-article (account: default)
>   - x-article (account: lewis)
>
> Confirm public publish? (yes/no)

Only proceed on exact match `yes`. Anything else → downgrade to `draft` for
safety and inform the user.

## Commit

```bash
python3 scripts/meti.py wizard --commit /tmp/manifest.yaml
```

The CLI prints `RUN_DIR <path>`. The manifest is now at `<RUN_DIR>/manifest.yaml`
and a `manifest.lock.json` is generated.

## Hand-off

Tell the user the run dir and ask whether to also execute now:

> Manifest ready at `<RUN_DIR>/manifest.yaml`. Execute now?
>   yes    → run `meti publish <RUN_DIR>/manifest.yaml`
>   later  → I'll stop here; run `meti publish` when you're ready.
