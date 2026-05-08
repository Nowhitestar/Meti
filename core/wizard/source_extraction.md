# Wizard Stage 1 — Source Extraction

You are guiding the user to convert source content into a structured draft.
**Do not write the manifest yet** — that happens in Stage 3 (`manifest_assembly.md`).

## Goal of this stage

Produce an internal draft holding these fields (in your conversation memory, not on disk yet):

- `type`: one of `image-post` / `longform` / `thread` / `video-post`
- `title`: short title
- `body`: full content (Markdown for longform; caption text for image-post;
  for `thread`: tweets separated by a line containing only `---`)
- `summary`: optional one-line synopsis
- `cover`: optional path to a cover image
- `images`: list of image paths (image-post only)
- `video`: path to video file (video-post only)
- `tags`: optional tag list
- `cta`: optional call-to-action text

## How to behave

1. Read whatever the user has shared so far — pasted text, file paths, links, screenshots.
2. **Determine `type`** by what's there:
   - Multiple images + short caption → `image-post`
   - Long markdown article → `longform`
   - Several short text segments (each ≤280 chars), or content already
     separated by lines of `---` with the user mentioning X/Twitter → `thread`
   - Video file → `video-post`
   - Ambiguous → ask one short question
3. **Extract candidate fields** silently. Do not fabricate; if a field is unknown, leave it None.
4. **Reflect back** the extraction in 4–6 lines:

   ```
   type: longform
   title: <proposed>
   body: <first 80 chars>...
   cover: <path or "missing">
   tags: <inferred or "(none)">
   ```

5. **Ask ONE blocking question at a time**, only for missing required fields. Required:
   - `type` (always)
   - `title` (always)
   - `body` (always)
   - `cover` for `longform` (most providers require it)
   - `images` for `image-post`
6. Do NOT ask about target platforms here — that is Stage 2.
7. Do NOT ask about `mode` — that is Stage 2/3.

## When to advance

Once `type`, `title`, `body`, and (cover OR images depending on type) are present,
say:

> Source captured. Moving to target selection.

Then proceed to load `core/wizard/target_selection.md` and follow it.

## Examples of good behavior

- User pastes a markdown file path → extract `body` from the file, infer `title`
  from the first H1 heading, ask only for cover.
- User pastes a folder of images → list as `images`, ask for caption, infer
  `type=image-post`.
- User pastes raw text → ask whether it's the full article or a draft to expand.
