# Run Results Contract

Meti writes each run under `runs/<run-id>/`. The machine-readable outcome is
`result.json`; logs are supporting diagnostics. Consumers should inspect
`result.json` for run state and use `publish-log.md` only to debug event order.

## Schema Version

Current schema: `schema_version: 2`.

Schema 2 separates observed outcome from the next action:

- `status`: what happened.
- `next_action`: what a user or agent should do next.

No top-level resume boolean is written. Resume is derived from target facts.

## Top-Level Fields

- `schema_version`: integer, currently `2`.
- `status`: one of `ok`, `partial`, `failed`, `empty`.
- `next_action`: one of `none`, `resume`, `review`, `fix_input`.
- `resume_targets`: target names safe for `meti resume` to retry.
- `review_targets`: target names that need manual review before retrying.
- `targets`: per-target result entries.
- `run_id`, `manifest_path`, `started_at`, `completed_at`, `mode`, `host`,
  `meti_version`: run metadata.

Run status values:

- `ok`: all targets completed successfully.
- `partial`: at least one target succeeded and at least one did not.
- `failed`: the run had targets but none succeeded.
- `empty`: no target result was recorded.

Run action values:

- `none`: no follow-up action is needed.
- `resume`: retry only `resume_targets`.
- `review`: inspect `review_targets`; Meti will not auto-retry them.
- `fix_input`: fix manifest, config, credentials, or unsupported mode input.

When both retryable and review-only targets exist, top-level `next_action` is
`resume`; `review_targets` still lists the manual-review work.

## Target Fields

Each target entry may include:

- `name`: provider target name, such as `x-article`.
- `status`: one of `ok`, `failed`, `skipped`, `partial`.
- `next_action`: one of `none`, `resume`, `review`, `fix_input`.
- `mode_actual`: actual execution result, such as `dry-run`,
  `draft-platform`, `draft-local`, `partial`, or `failed-needs-review`.
- `recoverable`: factual provider signal. This is not itself the retry policy.
- `error_code`, `error_kind`, `error`: failure facts when available.
- `manual_recovery`: human-readable recovery step when available.
- `external_id`, `draft_url`: durable draft evidence when safe.
- `extras`: provider diagnostics, sanitized before writing.
- `violations`: validation or rule violations when available.

Providers return factual fields. Core derives `next_action`.

## Resume Rules

`meti resume <run-dir>` retries only targets whose target `next_action` is
`resume`. A selected `--target` filters candidates only; it does not force
review-only or fix-input targets to run.

Review-needed targets are carried forward unchanged enough for inspection and
are logged with a skip reason. This avoids overwriting browser/editor state
that may need human review.

## Redaction

Before writing run artifacts, Meti recursively sanitizes strings, lists, and
objects. Sensitive URL query values are replaced with `[REDACTED]` for these
case-insensitive keys:

- `token`
- `access_token`
- `auth`
- `code`
- `state`
- `session`
- `key`
- `secret`

The denylist lives in `core/run.py` and is intentionally extensible.

## Example

```json
{
  "schema_version": 2,
  "status": "partial",
  "next_action": "resume",
  "resume_targets": ["x-article"],
  "review_targets": ["substack"],
  "targets": [
    {
      "name": "wechat-article",
      "status": "ok",
      "next_action": "none",
      "mode_actual": "draft-platform",
      "external_id": "draft-example"
    },
    {
      "name": "x-article",
      "status": "partial",
      "next_action": "resume",
      "mode_actual": "partial",
      "recoverable": true,
      "error_code": "selector_drift"
    },
    {
      "name": "substack",
      "status": "failed",
      "next_action": "review",
      "mode_actual": "failed-needs-review",
      "recoverable": true,
      "error_kind": "review_needed",
      "extras": {
        "current_url": "https://example.invalid/edit?state=[REDACTED]&safe=1"
      }
    }
  ]
}
```
