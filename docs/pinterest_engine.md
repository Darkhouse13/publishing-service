# Pinterest Engine Configuration

This project includes `pinterest_engine.py` for a dual-source workflow:

1. Pinterest Trends export (authenticated) -> keyword ranking.
2. PinClicks Top Pins export (authenticated) for ranked trend keywords.
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
- `PINTEREST_CSV_PATH_TEMPLATE` default `artifacts/exports/pinterest_bulk_upload_{blog_suffix}.csv`
- `PINTEREST_CSV_CADENCE_MINUTES` default `240`
- `FAL_MODEL_PIN` fallback to `FAL_MODEL`
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

## Run

```bash
python pinterest_engine.py --blog THE_SUNDAY_PATIO
```

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
