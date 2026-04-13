# Pinterest Engine Configuration

This project includes `pinterest_engine.py` for a dual-source workflow:

1. Pinterest Trends export (authenticated) -> keyword ranking.
2. PinClicks Top Pins crawl (authenticated via Cloudflare Browser Rendering `/crawl`) for ranked trend keywords.
3. Winner keywords run through generation -> WordPress draft publish -> Pinterest CSV row export.

Pinterest account credentials are used only for Trends scraping.  
Pinterest bulk upload is still manual; this tool produces CSV for you.
This workflow does not generate a Pinterest ZIP package.

## Required environment

- `PINTEREST_SEED_MAP_JSON`
- `PINTEREST_BOARD_MAP_JSON`
- `PINTEREST_USERNAME`
- `PINTEREST_PASSWORD`
- `PINCLICKS_USERNAME`
- `PINCLICKS_PASSWORD`
- `PINCLICKS_TOP_PINS_URL_TEMPLATE`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `WP_URL_<BLOG_SUFFIX>`
- `WP_USER_<BLOG_SUFFIX>`
- `WP_KEY_<BLOG_SUFFIX>`
- `DEEPSEEK_API_KEY` (or `OPENAI_API_KEY` when `PINTEREST_ANALYSIS_PROVIDER=openai`)
- `FAL_KEY`

## Optional environment

- `PINTEREST_TRENDS_BASE_URL` default `https://trends.pinterest.com`
- `PINTEREST_TRENDS_FILTER_REGION` default `GLOBAL`
- `PINTEREST_TRENDS_FILTER_RANGE` default `12m`
- `PINTEREST_TRENDS_FORCE_INCLUDE_KEYWORD` default `1` (prioritize include-keyword filter before global search fallback)
- `PINTEREST_TRENDS_TOP_KEYWORDS` default `20`
- `PINTEREST_PINCLICKS_WINNERS_PER_RUN` default `5`
- `PINTEREST_STORAGE_STATE_PATH` default `%USERPROFILE%/.codex/secrets/pinterest_state.json`
- `PINCLICKS_STORAGE_STATE_PATH` default `%USERPROFILE%/.codex/secrets/pinclicks_state.json`
- `PINCLICKS_CRAWL_MAX_PAGES` default `3`
- `CLOUDFLARE_BROWSER_RENDERING_BASE_URL` default `https://api.cloudflare.com/client/v4/accounts`
- `PINTEREST_CSV_PATH_TEMPLATE` default `artifacts/exports/pinterest_bulk_upload_{blog_suffix}.csv`
- `PINTEREST_CSV_CADENCE_MINUTES` default `240`
- `FAL_MODEL_PIN` fallback to `FAL_MODEL`
- `PINTEREST_FONT_MAP_JSON` map of blog suffix/default to scalable `.ttf`/`.otf`/`.ttc` font paths for readable overlay text
- `PINTEREST_PIN_TEMPLATE_MODE` default `center_strip` (`center_strip|none`)
- `PINTEREST_PIN_TEMPLATE_FAILURE_POLICY` default `template_or_none` (`template_or_none|fail`)
- `ARTICLE_VALIDATOR_REPAIR_PROMPT` optional inline override for the article validator repair system prompt
- `WP_PUBLIC_POST_URL_TEMPLATE_<BLOG_SUFFIX>` default `{site_url}/{slug}/`

## Example seed map

```json
{
  "THE_SUNDAY_PATIO": ["patio", "backyard", "outdoor decor"],
  "YOUR_MIDNIGHT_DESK": ["desk setup", "productivity", "ergonomic desk"]
}
```

## Example board map

```json
{
  "THE_SUNDAY_PATIO": {
    "default": "Patio Inspiration",
    "overrides": {
      "gardening": "Backyard Gardening",
      "furniture": "Patio Furniture Ideas"
    }
  }
}
```

## Font map examples

Readable Pinterest overlays require a scalable font. The image pipeline resolves fonts in this order:

1. `PINTEREST_FONT_MAP_JSON` (blog suffix key first, then `default`)
2. Pillow packaged DejaVu font (if available)
3. OS fallback candidates

If no scalable font can be resolved, image generation fails with an actionable error instead of rendering tiny text.

Windows example:

```json
{
  "default": "C:\\Windows\\Fonts\\segoeui.ttf",
  "THE_SUNDAY_PATIO": "C:\\Windows\\Fonts\\arial.ttf"
}
```

macOS example:

```json
{
  "default": "/System/Library/Fonts/Supplemental/Arial.ttf"
}
```

Linux example:

```json
{
  "default": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
}
```

## Pinterest Image Template

Default pin rendering uses a deterministic center-strip template:

1. Full `1000x1500` canvas.
2. Top and bottom image panels are cropped from one generated base image.
3. A light center strip contains:
4. Uppercased headline from `pin_title`.
5. Blog-name byline from the configured blog display name.

Template controls:

- `PINTEREST_PIN_TEMPLATE_MODE=center_strip|none`
- `PINTEREST_PIN_TEMPLATE_FAILURE_POLICY=template_or_none|fail`

`template_or_none` exports a clean no-text full-bleed image when text template rendering fails.
`fail` raises an image generation error instead.

## Run

```bash
python pinterest_engine.py --blog THE_SUNDAY_PATIO
```

## PinClicks Stage 3

Stage 3 now uses Cloudflare Browser Rendering `/crawl` instead of local PinClicks browser automation.

- The start URL is still built from `PINCLICKS_TOP_PINS_URL_TEMPLATE`.
- Authentication is forwarded from `PINCLICKS_STORAGE_STATE_PATH`; that file must contain a valid PinClicks session.
- If the session is missing or expired, Stage 3 fails fast with `authentication_failed`.
- If Cloudflare returns content but no usable pin records, Stage 3 reports a crawl/parse failure instead of silently switching back to synthetic PinClicks input.

Resume a run:

```bash
python pinterest_engine.py --blog THE_SUNDAY_PATIO --resume 20260216_180501
```

## Pinterest CSV Output

The exporter now writes Pinterest-compatible columns in this exact order:

1. `Title`
2. `Media URL`
3. `Pinterest board`
4. `Thumbnail`
5. `Description`
6. `Link`
7. `Publish date`
8. `Keywords`

Notes:

- `Publish date` is written as UTC ISO timestamp: `YYYY-MM-DDTHH:MM:SS`.
- Existing legacy CSV files with old headers (`Image URL`, `Pinterest Board`, `Publish Date`) are auto-migrated in place on next append.
- `Keywords` are auto-generated from analysis output (`primary_keyword` + supporting terms).
- `Thumbnail` is left blank for image pins.

Troubleshooting:

- If you see `CSV row Pinterest board is required.`, your `PINTEREST_BOARD_MAP_JSON` is missing
  the current blog suffix (for example `THE_WEEKEND_FOLIO`) or the blog entry has a blank
  `default` board value.
- If you stop Streamlit and see `Stopping...` followed by `RuntimeError: Event loop is closed`,
  treat it as a benign shutdown-time warning when output artifacts already exist.
- Stop Streamlit with a single `Ctrl+C`, then wait; avoid repeated interrupts while `Stopping...`
  is displayed.
- If shutdown appears stuck, terminate once from Task Manager or `taskkill /PID <streamlit_pid> /F`.
- Classify as actionable only when this appears during active generation/publish before outputs,
  or when expected artifacts are missing.
- Optional: for a cleaner shutdown console experience, run Streamlit in a Python 3.12 virtual
  environment.
