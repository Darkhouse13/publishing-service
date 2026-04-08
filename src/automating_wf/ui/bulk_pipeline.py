"""Streamlit bulk pipeline wizard for Trends -> PinClicks -> Generation."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from automating_wf.engine.config import EngineRunOptions, GenerationResults, PinClicksResults, TrendCandidates
from automating_wf.export.pinterest_csv import (
    csv_timezone,
    csv_timezone_name,
    default_auto_publish_datetime,
    parse_csv_publish_date,
    preview_publish_schedule,
    validate_board_mapping_for_blog,
)
from automating_wf.engine.pipeline import (
    MANIFEST_NAME,
    RUN_ROOT,
    RUN_OPTIONS_NAME,
    SUMMARY_NAME,
    TERMINAL_WINNER_STATUSES,
    TRENDS_TOP_KEYWORDS_FILE,
    bootstrap_pinclicks_session_sync,
    build_generation_result_from_manifest_entry,
    collect_pinclicks_data_sync,
    collect_trends_candidates_sync,
    replay_pending_csv_sync,
    run_winner_generation_sync,
)


STAGE_CONFIG = 1
STAGE_TRENDS = 2
STAGE_PINCLICKS = 3
STAGE_GENERATION = 4
PINCLICKS_SETUP_REASON = "authentication_setup_required"
SEED_PRESETS_PATH = Path("artifacts") / "config" / "bulk_seed_presets.json"


def _parse_seed_text(value: Any) -> list[str]:
    """Parse multiline/comma-separated or list seed input into ordered deduplicated keywords."""
    if isinstance(value, list):
        parts = [str(item or "") for item in value]
    else:
        parts = [item for line in str(value or "").splitlines() for item in line.split(",")]
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        keyword = part.strip()
        if not keyword:
            continue
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        cleaned.append(keyword)
    return cleaned


def _safe_slug(value: str) -> str:
    """Create a safe key fragment for widget/session identifiers."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_")
    return normalized or "item"


def _pinclicks_setup_skip(results: PinClicksResults | None) -> dict[str, Any] | None:
    """Return the preflight setup-required entry when Stage 3 needs manual login."""
    if results is None:
        return None
    for item in results.skipped:
        if str(item.get("keyword", "")).strip() != "__preflight__":
            continue
        if str(item.get("reason", "")).strip() != PINCLICKS_SETUP_REASON:
            continue
        return item
    return None


def _default_region() -> str:
    """Resolve default trends region from environment aliases."""
    return (
        os.getenv("PINTEREST_TRENDS_REGION", "").strip()
        or os.getenv("PINTEREST_TRENDS_FILTER_REGION", "").strip()
        or "GLOBAL"
    )


def _env_range_to_ui(raw_value: str) -> str:
    """Map raw env range values to the UI range options."""
    value = str(raw_value or "").strip().casefold()
    if value in {"daily", "1d", "24h"}:
        return "daily"
    if value in {"weekly", "7d", "1w"}:
        return "weekly"
    return "monthly"


def _default_range() -> str:
    """Resolve default trends range from environment aliases."""
    raw = (
        os.getenv("PINTEREST_TRENDS_RANGE", "").strip()
        or os.getenv("PINTEREST_TRENDS_FILTER_RANGE", "").strip()
        or "12m"
    )
    return _env_range_to_ui(raw)


def _default_top_n() -> int:
    """Resolve default top-N trends value from environment aliases."""
    raw = (
        os.getenv("PINTEREST_TRENDS_TOP_N", "").strip()
        or os.getenv("PINTEREST_TRENDS_TOP_KEYWORDS", "").strip()
        or "20"
    )
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 20
    return min(30, max(3, parsed))


def _default_winner_count() -> int:
    """Resolve default winner/article count from environment."""
    raw = os.getenv("PINTEREST_PINCLICKS_WINNERS_PER_RUN", "").strip() or "5"
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 5
    return min(20, max(1, parsed))


def _default_publish_status() -> str:
    """Resolve default publish status from environment with validation."""
    value = os.getenv("WP_POST_STATUS", "draft").strip().lower()
    if value in {"draft", "publish", "pending"}:
        return value
    return "draft"


def _default_csv_cadence_minutes() -> int:
    """Resolve default CSV cadence using the same config source as the engine."""
    raw = os.getenv("PINTEREST_CSV_CADENCE_MINUTES", "").strip() or "240"
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 240
    return max(1, parsed)


def _default_csv_anchor() -> datetime:
    """Return the default suggested first CSV publish datetime."""
    return default_auto_publish_datetime()


def _compose_csv_first_publish_at(st: Any) -> str | None:
    """Compose the configured first CSV publish datetime from session state."""
    if bool(st.session_state.get("bulk_csv_auto_schedule", True)):
        return None
    date_value = st.session_state.get("bulk_csv_first_publish_date")
    time_value = st.session_state.get("bulk_csv_first_publish_time")
    if date_value is None or time_value is None:
        return None
    return f"{date_value.isoformat()} {time_value.strftime('%H:%M')}"


def _schedule_preview_rows(st: Any) -> list[dict[str, str]]:
    """Build preview rows for the Stage 1 CSV schedule UI."""
    target_count = max(1, min(int(st.session_state.get("bulk_target_articles", 1) or 1), 5))
    cadence_minutes = max(1, int(st.session_state.get("bulk_csv_cadence_minutes", _default_csv_cadence_minutes()) or 1))
    return preview_publish_schedule(
        first_publish_at=_compose_csv_first_publish_at(st),
        cadence_minutes=cadence_minutes,
        count=target_count,
    )


def _apply_opts_to_schedule_state(st: Any, opts: EngineRunOptions) -> None:
    """Hydrate Stage 1 scheduling widgets from EngineRunOptions."""
    st.session_state.bulk_csv_cadence_minutes = int(opts.csv_cadence_minutes)
    parsed = parse_csv_publish_date(str(opts.csv_first_publish_at or ""))
    if parsed is None:
        parsed = _default_csv_anchor()
        st.session_state.bulk_csv_auto_schedule = True
    else:
        st.session_state.bulk_csv_auto_schedule = False
    st.session_state.bulk_csv_first_publish_date = parsed.date()
    st.session_state.bulk_csv_first_publish_time = parsed.timetz().replace(tzinfo=None, second=0, microsecond=0)


def _init_bulk_state(st: Any) -> None:
    """Initialize all namespaced bulk session-state keys."""
    default_anchor = _default_csv_anchor()
    defaults: dict[str, Any] = {
        "bulk_stage": STAGE_CONFIG,
        "bulk_opts": None,
        "bulk_trend_candidates": None,
        "bulk_selected_keywords": [],
        "bulk_pinclicks_results": None,
        "bulk_final_winners": [],
        "bulk_generation_results": None,
        "bulk_run_id": None,
        "bulk_last_error": None,
        "bulk_generation_started": False,
        "bulk_generation_progress": [],
        "bulk_prev_blog": "",
        "bulk_blog": "",
        "bulk_blog_config": {},
        "bulk_seed_text": "",
        "bulk_seed_notice": "",
        "bulk_trends_region": _default_region(),
        "bulk_trends_range": _default_range(),
        "bulk_trends_top_n": _default_top_n(),
        "bulk_pinclicks_max_records": 25,
        "bulk_target_articles": _default_winner_count(),
        "bulk_publish_status": _default_publish_status(),
        "bulk_csv_auto_schedule": True,
        "bulk_csv_cadence_minutes": _default_csv_cadence_minutes(),
        "bulk_csv_first_publish_date": default_anchor.date(),
        "bulk_csv_first_publish_time": default_anchor.timetz().replace(tzinfo=None, second=0, microsecond=0),
        "bulk_headed": False,
        "bulk_resume_run_id": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_bulk_from_stage(st: Any, stage: int) -> None:
    """Clear cached bulk-stage state from a given stage onward."""
    if stage <= STAGE_TRENDS:
        st.session_state.bulk_trend_candidates = None
        st.session_state.bulk_selected_keywords = []
        st.session_state.bulk_run_id = None
        for key in list(st.session_state.keys()):
            if key.startswith("bulk_kw_"):
                del st.session_state[key]
    if stage <= STAGE_PINCLICKS:
        st.session_state.bulk_pinclicks_results = None
        st.session_state.bulk_final_winners = []
    if stage <= STAGE_GENERATION:
        st.session_state.bulk_generation_results = None
        st.session_state.bulk_generation_started = False
        st.session_state.bulk_generation_progress = []
    st.session_state.bulk_last_error = None


def _reset_bulk_state(st: Any) -> None:
    """Reset all bulk session-state values to initial defaults."""
    for key in list(st.session_state.keys()):
        if key.startswith("bulk_"):
            del st.session_state[key]
    _init_bulk_state(st)


def _manifest_entries(run_dir: Path) -> list[dict[str, Any]]:
    """Load manifest rows from a run directory."""
    manifest_path = run_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_manifest_by_seed(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep only the latest manifest row per seed keyword."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        seed = str(entry.get("seed_keyword", "")).strip()
        if not seed:
            continue
        latest[seed] = entry
    return latest


def _read_json_file(path: Path) -> Any:
    """Read a JSON file safely and return None on parse/read failures."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _seed_presets_path() -> Path:
    """Return the persistent path for saved bulk seed presets."""
    return SEED_PRESETS_PATH


def _load_seed_presets() -> dict[str, list[str]]:
    """Read saved seed presets from disk."""
    payload = _read_json_file(_seed_presets_path())
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for suffix, seeds in payload.items():
        if not isinstance(suffix, str):
            continue
        normalized_suffix = suffix.strip().upper()
        if not normalized_suffix:
            continue
        normalized[normalized_suffix] = _parse_seed_text(seeds)
    return normalized


def _save_seed_preset(blog_suffix: str, seed_keywords: list[str]) -> None:
    """Persist seed presets for one blog suffix."""
    suffix = str(blog_suffix or "").strip().upper()
    if not suffix:
        return
    presets = _load_seed_presets()
    presets[suffix] = _parse_seed_text(seed_keywords)
    path = _seed_presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def _saved_seed_keywords(blog_suffix: str) -> list[str]:
    """Return saved seed keywords for a blog suffix, if any."""
    suffix = str(blog_suffix or "").strip().upper()
    if not suffix:
        return []
    return list(_load_seed_presets().get(suffix, []))


def _latest_run_seed_keywords(blog_suffix: str) -> list[str]:
    """Load seed keywords from the most recent run for the given blog suffix."""
    suffix = str(blog_suffix or "").strip().upper()
    if not suffix or not RUN_ROOT.exists():
        return []
    candidate_dirs = sorted((path for path in RUN_ROOT.iterdir() if path.is_dir()), reverse=True)
    for run_dir in candidate_dirs:
        payload = _read_json_file(run_dir / RUN_OPTIONS_NAME)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("blog_suffix", "")).strip().upper() != suffix:
            continue
        keywords = _parse_seed_text(payload.get("seed_keywords", []))
        if keywords:
            return keywords
    return []


def _preferred_seed_keywords(blog_suffix: str) -> list[str]:
    """Choose the best default seed list for a blog suffix."""
    saved = _saved_seed_keywords(blog_suffix)
    if saved:
        return saved
    return EngineRunOptions.from_env(blog_suffix).seed_keywords


def _find_cached_winners_file(run_dir: Path) -> Path | None:
    """Return cached run_winners_top*.json file if present."""
    analysis_dir = run_dir / "pinclicks_analysis"
    if not analysis_dir.exists():
        return None
    candidates = sorted(analysis_dir.glob("run_winners_top*.json"))
    if candidates:
        return candidates[-1]
    return None


def _detect_resume_stage(run_dir: Path) -> int:
    """Infer wizard stage from existing run artifacts."""
    entries = _manifest_entries(run_dir)
    if any(str(item.get("status", "")).strip() in TERMINAL_WINNER_STATUSES for item in entries):
        return STAGE_GENERATION
    winners_file = _find_cached_winners_file(run_dir)
    scores_file = run_dir / "pinclicks_analysis" / "pinclicks_keyword_scores.json"
    if winners_file is not None or scores_file.exists():
        return STAGE_PINCLICKS
    trends_file = run_dir / "trends_analysis" / TRENDS_TOP_KEYWORDS_FILE
    if trends_file.exists():
        return STAGE_TRENDS
    return STAGE_TRENDS


def _load_trend_candidates_from_run(run_id: str, run_dir: Path) -> TrendCandidates | None:
    """Hydrate Phase 1 result model from cached trend artifacts."""
    trends_file = run_dir / "trends_analysis" / TRENDS_TOP_KEYWORDS_FILE
    payload = _read_json_file(trends_file)
    if not isinstance(payload, list):
        return None
    ranked: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        ranked.append(
            {
                "keyword": keyword,
                "rank": int(item.get("rank", 0) or 0),
                "reach_hat": float(item.get("reach_hat", 0.0) or 0.0),
                "reach_confidence": float(item.get("reach_confidence", 0.0) or 0.0),
                "trend_index_raw": float(item.get("trend_index_raw", 0.0) or 0.0),
                "growth_rate_raw": float(item.get("growth_rate_raw", 0.0) or 0.0),
                "source_count": int(item.get("source_count", 0) or 0),
                "qualified": bool(item.get("qualified", True)),
            }
        )

    records_payload = _read_json_file(run_dir / "trends_analysis" / "trends_records.json")
    raw_count = len(records_payload) if isinstance(records_payload, list) else 0
    return TrendCandidates(
        run_id=run_id,
        run_dir=str(run_dir),
        ranked_keywords=ranked,
        raw_trends_count=raw_count,
    )


def _load_pinclicks_results_from_run(run_id: str, run_dir: Path) -> PinClicksResults | None:
    """Hydrate Phase 2 result model from cached PinClicks artifacts."""
    winners_file = _find_cached_winners_file(run_dir)
    winners_payload = _read_json_file(winners_file) if winners_file else None
    winners: list[dict[str, Any]] = []
    if isinstance(winners_payload, list):
        for item in winners_payload:
            if isinstance(item, dict):
                winners.append(
                    {
                        "keyword": str(item.get("keyword", "")).strip(),
                        "reach_hat": float(item.get("reach_hat", 0.0) or 0.0),
                        "ctr_hat": float(item.get("ctr_hat", 0.0) or 0.0),
                        "click_score": float(item.get("click_score", 0.0) or 0.0),
                        "is_pareto_efficient": bool(item.get("is_pareto_efficient", False)),
                        "selection_reason": str(item.get("selection_reason", "")).strip(),
                        "engagement_score": float(item.get("engagement_score", 0.0) or 0.0),
                        "record_count": int(item.get("record_count", 0) or 0),
                        "trend_rank": int(item.get("trend_rank", 0) or 0),
                        "pinclicks_rank": int(item.get("pinclicks_rank", 0) or 0),
                        "scrape_source": str(item.get("scrape_source", "")).strip(),
                    }
                )

    skipped: list[dict[str, Any]] = []
    latest = _latest_manifest_by_seed(_manifest_entries(run_dir))
    for seed, entry in latest.items():
        status = str(entry.get("status", "")).strip()
        if status != "scrape_failed":
            continue
        details = entry.get("details", {})
        message = str(details.get("error", "PinClicks scrape failed")).strip()
        skipped.append(
            {
                "keyword": seed,
                "reason": str(details.get("reason", "unknown_scrape_failure")).strip() or "unknown_scrape_failure",
                "error": message,
                "attempts": int(details.get("attempts", 0) or 0),
                "used_headed_fallback": bool(details.get("used_headed_fallback", False)),
                "source_stage": "pinclicks",
            }
        )

    if not winners and not skipped:
        return None
    return PinClicksResults(
        run_id=run_id,
        run_dir=str(run_dir),
        winners=winners,
        skipped=skipped,
    )


def _load_generation_results_from_run(run_id: str, run_dir: Path) -> GenerationResults:
    """Hydrate Phase 3 summary model from manifest and summary artifacts."""
    latest = _latest_manifest_by_seed(_manifest_entries(run_dir))
    normalized_results: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    failed_pre_publish: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    latest_suffix = ""
    for seed, entry in latest.items():
        result = build_generation_result_from_manifest_entry(seed_keyword=seed, entry=entry)
        if result is None:
            continue
        normalized_results.append(result)
        if not latest_suffix:
            latest_suffix = str(entry.get("blog_suffix", "")).strip().upper()

    for item in normalized_results:
        status = str(item.get("status", "")).strip()
        if status == "completed":
            completed.append(item)
            continue
        if status == "partial":
            partial.append(item)
            failed.append(item)
            continue
        failed_pre_publish.append(item)
        failed.append(item)

    csv_path = ""
    summary_payload = _read_json_file(run_dir / SUMMARY_NAME)
    if isinstance(summary_payload, dict):
        csv_path = str(summary_payload.get("csv_path", "")).strip()
    if not csv_path and latest_suffix:
        csv_path = str(run_dir / f"pinterest_bulk_upload_{latest_suffix.strip().lower()}.csv")

    return GenerationResults(
        run_id=run_id,
        run_dir=str(run_dir),
        completed=completed,
        partial=partial,
        failed_pre_publish=failed_pre_publish,
        failed=failed,
        manifest_path=str(run_dir / MANIFEST_NAME),
        csv_path=csv_path,
    )


def _apply_resume_state(st: Any, run_id: str) -> bool:
    """Apply resume artifacts into bulk session-state and jump to inferred stage."""
    run_dir = RUN_ROOT / run_id
    if not run_dir.exists():
        st.session_state.bulk_last_error = f"Run '{run_id}' was not found in {RUN_ROOT}."
        return False

    stage = _detect_resume_stage(run_dir)
    trend_candidates = _load_trend_candidates_from_run(run_id, run_dir)
    pinclicks_results = _load_pinclicks_results_from_run(run_id, run_dir)
    generation_results = _load_generation_results_from_run(run_id, run_dir)
    run_options_payload = _read_json_file(run_dir / RUN_OPTIONS_NAME)
    if isinstance(run_options_payload, dict):
        try:
            resumed_opts = EngineRunOptions.from_ui(run_options_payload)
            st.session_state.bulk_opts = resumed_opts
            st.session_state.bulk_seed_text = "\n".join(resumed_opts.seed_keywords)
            _apply_opts_to_schedule_state(st, resumed_opts)
            st.session_state.bulk_publish_status = resumed_opts.publish_status
            st.session_state.bulk_headed = resumed_opts.headed
        except Exception:
            pass

    st.session_state.bulk_run_id = run_id
    st.session_state.bulk_stage = stage
    st.session_state.bulk_trend_candidates = trend_candidates
    if trend_candidates is not None:
        st.session_state.bulk_selected_keywords = [
            str(item.get("keyword", "")).strip()
            for item in trend_candidates.ranked_keywords
            if str(item.get("keyword", "")).strip()
        ]
    st.session_state.bulk_pinclicks_results = pinclicks_results
    if pinclicks_results is not None and pinclicks_results.winners:
        st.session_state.bulk_final_winners = list(pinclicks_results.winners)
    if stage == STAGE_GENERATION:
        st.session_state.bulk_generation_results = generation_results
        st.session_state.bulk_generation_started = True
    else:
        st.session_state.bulk_generation_results = None
        st.session_state.bulk_generation_started = False
    st.session_state.bulk_last_error = None
    return True


def _go_back_to(st: Any, stage: int) -> None:
    """Navigate to a previous bulk stage and rerun."""
    st.session_state.bulk_stage = stage
    st.session_state.bulk_last_error = None
    st.rerun()


def _render_stage_config(
    st: Any,
    blog_configs: dict[str, dict[str, Any]],
    resolve_target_suffix: Callable[[str], str],
) -> None:
    """Render Stage 1 bulk configuration UI."""
    st.subheader("Stage 1: Configuration")
    blog_options = [""] + list(blog_configs.keys())
    selected_blog = st.selectbox(
        "Blog",
        options=blog_options,
        format_func=lambda item: "Select a blog..." if not item else item,
        key="bulk_blog",
    )

    if selected_blog != st.session_state.get("bulk_prev_blog", ""):
        st.session_state.bulk_prev_blog = selected_blog
        st.session_state.bulk_blog_config = dict(blog_configs.get(selected_blog, {})) if selected_blog else {}
        st.session_state.bulk_seed_text = ""
        if selected_blog:
            suffix = resolve_target_suffix(selected_blog)
            defaults = EngineRunOptions.from_env(suffix)
            st.session_state.bulk_seed_text = "\n".join(_preferred_seed_keywords(suffix))
            _apply_opts_to_schedule_state(st, defaults)
            st.session_state.bulk_seed_notice = ""
        _clear_bulk_from_stage(st, STAGE_TRENDS)
        st.rerun()

    if selected_blog:
        suffix = resolve_target_suffix(selected_blog)
        target_url = os.getenv(f"WP_URL_{suffix}", "").strip().rstrip("/")
        if target_url:
            st.caption(f"Target: {target_url}")
        else:
            st.warning(f"Missing destination URL for `{suffix}`. Set `WP_URL_{suffix}` in `.env`.")

        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            if st.button("Load Saved Seeds", key="bulk_load_saved_seeds"):
                saved_keywords = _saved_seed_keywords(suffix)
                if saved_keywords:
                    st.session_state.bulk_seed_text = "\n".join(saved_keywords)
                    st.session_state.bulk_seed_notice = f"Loaded saved seeds for `{suffix}`."
                else:
                    st.session_state.bulk_seed_notice = f"No saved seeds found for `{suffix}`."
                st.rerun()
        with action_col2:
            if st.button("Load Last Run Seeds", key="bulk_load_last_run_seeds"):
                latest_keywords = _latest_run_seed_keywords(suffix)
                if latest_keywords:
                    st.session_state.bulk_seed_text = "\n".join(latest_keywords)
                    st.session_state.bulk_seed_notice = f"Loaded seed keywords from the latest `{suffix}` run."
                else:
                    st.session_state.bulk_seed_notice = f"No prior run seeds found for `{suffix}`."
                st.rerun()
        with action_col3:
            if st.button("Save Current Seeds", key="bulk_save_current_seeds"):
                current_keywords = _parse_seed_text(st.session_state.bulk_seed_text)
                if current_keywords:
                    _save_seed_preset(suffix, current_keywords)
                    st.session_state.bulk_seed_notice = f"Saved {len(current_keywords)} seed keywords for `{suffix}`."
                else:
                    st.session_state.bulk_seed_notice = "Cannot save an empty seed list."
                st.rerun()

    seed_notice = str(st.session_state.get("bulk_seed_notice", "")).strip()
    if seed_notice:
        st.info(seed_notice)

    seeds_value = st.text_area(
        "Seed Keywords",
        key="bulk_seed_text",
        help="One keyword per line (commas also supported).",
        height=150,
    )
    if selected_blog and not _parse_seed_text(seeds_value):
        st.warning("No seed keywords configured for this blog. Enter keywords manually.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.text_input("Region", key="bulk_trends_region")
    with col2:
        st.selectbox("Range", options=["monthly", "weekly", "daily"], key="bulk_trends_range")
    with col3:
        st.number_input(
            "Top N",
            min_value=3,
            max_value=30,
            key="bulk_trends_top_n",
            step=1,
        )

    col4, col5 = st.columns(2)
    with col4:
        st.number_input(
            "PinClicks Max Records",
            min_value=5,
            max_value=100,
            key="bulk_pinclicks_max_records",
            step=1,
        )
    with col5:
        st.number_input(
            "Target Article Count",
            min_value=1,
            max_value=20,
            key="bulk_target_articles",
            step=1,
        )

    col6, col7 = st.columns(2)
    with col6:
        st.selectbox(
            "Publish Status",
            options=["draft", "publish", "pending"],
            key="bulk_publish_status",
        )
    with col7:
        st.checkbox("Headed Browser", key="bulk_headed")

    st.markdown("**CSV Schedule**")
    st.caption(f"Publish dates use timezone: `{csv_timezone_name()}`")
    col8, col9 = st.columns(2)
    with col8:
        st.checkbox(
            "Clear publish datetime and auto-schedule",
            key="bulk_csv_auto_schedule",
            help="When enabled, the first CSV row uses the next available slot automatically.",
        )
    with col9:
        st.number_input(
            "Cadence Minutes",
            min_value=1,
            max_value=1440,
            key="bulk_csv_cadence_minutes",
            step=15,
        )

    if not st.session_state.bulk_csv_auto_schedule:
        col10, col11 = st.columns(2)
        with col10:
            st.date_input(
                "First CSV Publish Date",
                key="bulk_csv_first_publish_date",
            )
        with col11:
            st.time_input(
                "First CSV Publish Time",
                key="bulk_csv_first_publish_time",
                step=900,
            )
    else:
        next_slot = _default_csv_anchor().strftime("%Y-%m-%d %H:%M")
        st.caption(f"Auto-schedule will start from the next rounded slot: `{next_slot}`")

    preview_rows = _schedule_preview_rows(st)
    if preview_rows:
        st.caption("Schedule preview")
        st.dataframe(preview_rows, width="stretch", hide_index=True)

    st.text_input(
        "Resume Previous Run (optional run_id)",
        key="bulk_resume_run_id",
    )

    if st.button("Start Trend Collection", type="primary"):
        if not selected_blog:
            st.session_state.bulk_last_error = "Select a blog before starting."
            st.error(st.session_state.bulk_last_error)
            return

        seed_keywords = _parse_seed_text(st.session_state.bulk_seed_text)
        if not seed_keywords:
            st.session_state.bulk_last_error = "Provide at least one seed keyword."
            st.error(st.session_state.bulk_last_error)
            return

        if int(st.session_state.bulk_target_articles) < 1:
            st.session_state.bulk_last_error = "Target article count must be at least 1."
            st.error(st.session_state.bulk_last_error)
            return

        csv_first_publish_at = _compose_csv_first_publish_at(st)
        if csv_first_publish_at:
            parsed_first_publish_at = parse_csv_publish_date(csv_first_publish_at)
            if parsed_first_publish_at is None:
                st.session_state.bulk_last_error = "First CSV publish datetime is invalid."
                st.error(st.session_state.bulk_last_error)
                return
            if parsed_first_publish_at <= datetime.now(csv_timezone()):
                st.session_state.bulk_last_error = "First CSV publish datetime must be in the future."
                st.error(st.session_state.bulk_last_error)
                return

        suffix = resolve_target_suffix(selected_blog)
        try:
            validate_board_mapping_for_blog(suffix)
        except Exception as exc:
            st.session_state.bulk_last_error = str(exc) or f"{type(exc).__name__}: {exc!r}"
            st.error(st.session_state.bulk_last_error)
            return

        try:
            opts = EngineRunOptions.from_ui(
                {
                    "blog_suffix": suffix,
                    "seed_keywords": seed_keywords,
                    "trends_region": st.session_state.bulk_trends_region,
                    "trends_range": st.session_state.bulk_trends_range,
                    "trends_top_n": int(st.session_state.bulk_trends_top_n),
                    "pinclicks_max_records": int(st.session_state.bulk_pinclicks_max_records),
                    "winners_count": int(st.session_state.bulk_target_articles),
                    "publish_status": st.session_state.bulk_publish_status,
                    "csv_first_publish_at": csv_first_publish_at,
                    "csv_cadence_minutes": int(st.session_state.bulk_csv_cadence_minutes),
                    "headed": bool(st.session_state.bulk_headed),
                    "resume_run_id": str(st.session_state.bulk_resume_run_id).strip() or None,
                }
            )
        except Exception as exc:
            st.session_state.bulk_last_error = (
                str(exc) or f"{type(exc).__name__}: {exc!r}"
            )
            st.error(st.session_state.bulk_last_error)
            return

        st.session_state.bulk_opts = opts
        st.session_state.bulk_last_error = None
        _clear_bulk_from_stage(st, STAGE_TRENDS)

        if opts.resume_run_id:
            if not _apply_resume_state(st, opts.resume_run_id):
                st.error(st.session_state.bulk_last_error)
                return
            st.rerun()

        st.session_state.bulk_stage = STAGE_TRENDS
        st.rerun()


def _render_stage_trends(st: Any) -> None:
    """Render Stage 2 trend collection and keyword selection UI."""
    st.subheader("Stage 2: Trend Collection")
    if st.button("<- Back", key="bulk_back_stage2"):
        _go_back_to(st, STAGE_CONFIG)

    opts = st.session_state.bulk_opts
    if opts is None:
        st.error("Bulk options are missing. Return to Stage 1.")
        return

    if st.session_state.bulk_trend_candidates is None and not st.session_state.bulk_last_error:
        with st.status("Collecting Pinterest Trends...", expanded=True):
            try:
                result = collect_trends_candidates_sync(opts)
                st.session_state.bulk_trend_candidates = result
                st.session_state.bulk_run_id = result.run_id
                st.session_state.bulk_last_error = None
            except Exception as exc:
                st.session_state.bulk_last_error = (
                    str(exc) or f"{type(exc).__name__}: {exc!r}"
                )

    if st.session_state.bulk_last_error:
        st.error(st.session_state.bulk_last_error)
        if st.button("Retry", key="bulk_retry_stage2"):
            st.session_state.bulk_trend_candidates = None
            st.session_state.bulk_last_error = None
            st.rerun()
        return

    trend_candidates: TrendCandidates | None = st.session_state.bulk_trend_candidates
    if trend_candidates is None:
        st.warning("No trend data found yet.")
        return

    if not trend_candidates.ranked_keywords:
        st.warning("No trend data found for these seeds. Try different keywords or a different region.")
        return

    selected_keywords: list[str] = []
    st.caption(f"Run ID: {trend_candidates.run_id}")

    # Show run warnings from Stage 1 metadata (e.g. inactive features)
    _trends_metadata_path = Path(trend_candidates.run_dir) / "trends_analysis" / "trends_scoring_metadata.json"
    if _trends_metadata_path.exists():
        try:
            _tmeta = json.loads(_trends_metadata_path.read_text(encoding="utf-8"))
            for _warn in _tmeta.get("run_warnings", []):
                st.warning(_warn)
            _ew = _tmeta.get("effective_weights", {})
            if _ew:
                st.caption(
                    "Effective reach weights: "
                    + ", ".join(f"{k} {v:.0%}" for k, v in _ew.items() if v > 0)
                )
        except Exception:
            pass

    for index, item in enumerate(trend_candidates.ranked_keywords):
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        checkbox_key = f"bulk_kw_{index}_{_safe_slug(keyword)}"
        reach = item.get("reach_hat", 0.0)
        conf = item.get("reach_confidence", 0.0)
        rank = item.get("rank", 0)
        src = item.get("source_count", 0)
        checked = st.checkbox(
            f"{keyword} | reach {reach:.3f} | conf {conf:.2f} | sources {src} | rank {rank}",
            key=checkbox_key,
            value=st.session_state.get(checkbox_key, True),
        )
        if checked:
            selected_keywords.append(keyword)

    st.caption(f"Selected {len(selected_keywords)} of {len(trend_candidates.ranked_keywords)} keywords")
    proceed_disabled = len(selected_keywords) == 0
    col_pinclicks, col_skip = st.columns(2)
    with col_pinclicks:
        if st.button("Proceed to PinClicks Analysis", disabled=proceed_disabled, key="bulk_to_stage3"):
            st.session_state.bulk_selected_keywords = selected_keywords
            st.session_state.bulk_stage = STAGE_PINCLICKS
            _clear_bulk_from_stage(st, STAGE_PINCLICKS)
            st.rerun()
    with col_skip:
        if st.button("Skip to Generation (no PinClicks)", disabled=proceed_disabled, key="bulk_skip_to_stage4"):
            st.session_state.bulk_selected_keywords = selected_keywords
            trend_data = {
                str(it.get("keyword", "")).strip(): it
                for it in trend_candidates.ranked_keywords
            }
            winners = []
            for idx, kw in enumerate(selected_keywords):
                td = trend_data.get(kw, {})
                rh = float(td.get("reach_hat", 0.5) or 0.5)
                default_ctr = 0.5
                winners.append(
                    {
                        "keyword": kw,
                        "reach_hat": rh,
                        "ctr_hat": default_ctr,
                        "click_score": round(rh * default_ctr, 6),
                        "is_pareto_efficient": True,
                        "selection_reason": "synthetic_skip",
                        "trend_rank": idx + 1,
                        "pinclicks_rank": 0,
                        "scrape_source": "synthetic",
                    }
                )
            st.session_state.bulk_final_winners = winners
            st.session_state.bulk_generation_results = None
            st.session_state.bulk_generation_started = False
            st.session_state.bulk_generation_progress = []
            st.session_state.bulk_last_error = None
            st.session_state.bulk_stage = STAGE_GENERATION
            st.rerun()


def _render_stage_pinclicks(st: Any) -> None:
    """Render Stage 3 PinClicks analysis and winner review UI."""
    st.subheader("Stage 3: PinClicks Analysis (Brave Session)")
    if st.button("<- Back", key="bulk_back_stage3"):
        _go_back_to(st, STAGE_TRENDS)

    opts = st.session_state.bulk_opts
    run_id = st.session_state.bulk_run_id
    selected_keywords = list(st.session_state.bulk_selected_keywords)
    if opts is None or not run_id:
        st.error("Missing run context. Return to Stage 1.")
        return

    if st.session_state.bulk_pinclicks_results is None and not st.session_state.bulk_last_error:
        with st.status(
            f"Checking PinClicks Brave session and scraping {len(selected_keywords)} keywords...",
            expanded=True,
        ):
            try:
                results = collect_pinclicks_data_sync(
                    opts=opts,
                    selected_keywords=selected_keywords,
                    run_id=run_id,
                )
                st.session_state.bulk_pinclicks_results = results
                st.session_state.bulk_last_error = None
            except Exception as exc:
                st.session_state.bulk_last_error = (
                    str(exc) or f"{type(exc).__name__}: {exc!r}"
                )

    if st.session_state.bulk_last_error:
        st.error(st.session_state.bulk_last_error)
        if st.button("Retry", key="bulk_retry_stage3"):
            st.session_state.bulk_pinclicks_results = None
            st.session_state.bulk_last_error = None
            st.rerun()
        return

    results: PinClicksResults | None = st.session_state.bulk_pinclicks_results
    if results is None:
        st.warning("No PinClicks results found.")
        return

    setup_skip = _pinclicks_setup_skip(results)
    if setup_skip is not None:
        is_expired = bool(setup_skip.get("session_expired", False))
        if is_expired:
            expired_cookies = setup_skip.get("expired_cookies", [])
            expired_at = setup_skip.get("expired_at", {})
            cookie_list = (
                ", ".join(f"**{c}**" for c in sorted(expired_cookies))
                if expired_cookies
                else "session cookies"
            )
            date_parts = sorted(expired_at.values()) if expired_at else []
            date_info = f" (expired {date_parts[0]})" if date_parts else ""
            st.warning(
                f"PinClicks session has expired{date_info}. "
                f"Affected cookies: {cookie_list}. "
                "Re-login is required to continue Stage 3 scraping."
            )
            st.markdown(
                "\n".join(
                    [
                        "**Re-login instructions**",
                        "1. Close other Brave windows for a clean session.",
                        "2. Click `Re-authenticate PinClicks Session` below.",
                        "3. Log into PinClicks in the opened PinFlow Brave window.",
                        "4. Wait for confirmation, then retry Stage 3.",
                    ]
                )
            )
        else:
            st.info(
                "Stage 3 needs a one-time PinClicks login in the dedicated PinFlow Brave profile "
                "before scraping can continue."
            )
            st.markdown(
                "\n".join(
                    [
                        "**Setup instructions**",
                        "1. Close other Brave windows for the first setup run.",
                        "2. Click `Set up PinClicks Session` below.",
                        "3. Log into PinClicks in the opened PinFlow Brave window.",
                        "4. Wait for this page to confirm that the session is ready, then retry Stage 3.",
                    ]
                )
            )
        setup_error = str(setup_skip.get("error", "")).strip()
        if setup_error and not is_expired:
            st.warning(setup_error)
        button_label = "Re-authenticate PinClicks Session" if is_expired else "Set up PinClicks Session"
        if st.button(button_label, type="primary", key="bulk_stage3_setup"):
            with st.status("Opening PinFlow Brave profile for PinClicks setup...", expanded=True):
                try:
                    payload = bootstrap_pinclicks_session_sync(
                        headed=True,
                        allow_manual_setup=True,
                        setup_timeout_seconds=900,
                    )
                    if bool(payload.get("authenticated", False)):
                        st.session_state.bulk_pinclicks_results = None
                        st.session_state.bulk_last_error = None
                        st.success(str(payload.get("message", "PinClicks session is ready.")))
                        st.rerun()
                    st.session_state.bulk_last_error = str(payload.get("message", "")).strip() or (
                        "PinClicks session setup did not complete."
                    )
                except Exception as exc:
                    st.session_state.bulk_last_error = str(exc) or f"{type(exc).__name__}: {exc!r}"
        if st.button("Retry Stage 3", key="bulk_retry_stage3_setup"):
            st.session_state.bulk_pinclicks_results = None
            st.session_state.bulk_last_error = None
            st.rerun()
        return

    if results.winners:
        st.dataframe(results.winners, width="stretch", hide_index=True)
    else:
        st.warning("No viable keywords found from PinClicks analysis.")

    if results.skipped:
        st.markdown("**Skipped Keywords**")
        for item in results.skipped:
            keyword = str(item.get("keyword", "")).strip()
            reason = str(item.get("reason", "unknown_scrape_failure")).strip() or "unknown_scrape_failure"
            error = str(item.get("error", "")).strip()
            attempts = int(item.get("attempts", 0) or 0)
            headed = bool(item.get("used_headed_fallback", False))
            suffix = f" (attempts={attempts}, headed_fallback={str(headed).lower()})" if attempts else ""
            st.warning(f"{keyword} [{reason}]{suffix}: {error}")

    winners_count = len(results.winners)
    if winners_count <= 0:
        return

    default_count = min(int(opts.winners_count), winners_count)
    selected_count = st.number_input(
        "Articles to Generate",
        min_value=1,
        max_value=winners_count,
        value=default_count,
        step=1,
        key="bulk_final_count",
    )
    if st.button("Generate Articles", type="primary", key="bulk_to_stage4"):
        st.session_state.bulk_final_winners = list(results.winners[: int(selected_count)])
        st.session_state.bulk_generation_results = None
        st.session_state.bulk_generation_progress = []
        st.session_state.bulk_generation_started = False
        st.session_state.bulk_last_error = None
        st.session_state.bulk_stage = STAGE_GENERATION
        st.rerun()


def _render_stage_generation(st: Any) -> None:
    """Render Stage 4 generation/publish execution and summary UI."""
    st.subheader("Stage 4: Generation + Publishing")
    can_go_back = not st.session_state.get("bulk_generation_started", False)
    if st.button("<- Back", disabled=not can_go_back, key="bulk_back_stage4"):
        st.session_state.bulk_stage = STAGE_PINCLICKS
        st.session_state.bulk_generation_results = None
        st.session_state.bulk_generation_started = False
        st.session_state.bulk_last_error = None
        st.session_state.bulk_generation_progress = []
        st.rerun()

    opts = st.session_state.bulk_opts
    winners = list(st.session_state.bulk_final_winners)
    run_id = st.session_state.bulk_run_id
    if opts is None or not run_id:
        st.error("Missing run context. Return to Stage 1.")
        return

    progress_box = st.empty()
    table_box = st.empty()
    if st.session_state.bulk_generation_progress:
        table_box.dataframe(st.session_state.bulk_generation_progress, width="stretch", hide_index=True)

    if (
        not st.session_state.bulk_generation_started
        and st.session_state.bulk_generation_results is None
        and not st.session_state.bulk_last_error
    ):
        st.session_state.bulk_generation_started = True
        st.session_state.bulk_generation_progress = []

        def on_progress(current_index: int, total_count: int, article_result: dict[str, Any]) -> None:
            ratio = 0.0 if total_count <= 0 else float(current_index / total_count)
            progress_box.progress(min(1.0, max(0.0, ratio)))
            st.session_state.bulk_generation_progress.append(
                {
                    "keyword": str(article_result.get("keyword", "")).strip(),
                    "status": str(article_result.get("status", "")).strip(),
                    "title": str(article_result.get("title", "")).strip(),
                    "post_url": str(article_result.get("post_url", "")).strip(),
                    "error": str(article_result.get("error", "")).strip(),
                }
            )
            table_box.dataframe(st.session_state.bulk_generation_progress, width="stretch", hide_index=True)

        with st.status("Generating and publishing winners...", expanded=True):
            try:
                result = run_winner_generation_sync(
                    opts=opts,
                    winners=winners,
                    run_id=run_id,
                    on_progress=on_progress,
                )
                st.session_state.bulk_generation_results = result
                st.session_state.bulk_last_error = None
            except Exception as exc:
                st.session_state.bulk_last_error = (
                    str(exc) or f"{type(exc).__name__}: {exc!r}"
                )

    if st.session_state.bulk_last_error:
        st.error(st.session_state.bulk_last_error)
        if st.button("Retry", key="bulk_retry_stage4"):
            st.session_state.bulk_generation_started = False
            st.session_state.bulk_generation_results = None
            st.session_state.bulk_generation_progress = []
            st.session_state.bulk_last_error = None
            st.rerun()
        return

    results: GenerationResults | None = st.session_state.bulk_generation_results
    if results is None:
        st.info("Generation is in progress...")
        return

    st.success(
        "Generation completed. "
        f"{len(results.completed)} full success, "
        f"{len(results.partial)} WordPress-published/CSV-pending, "
        f"{len(results.failed_pre_publish)} failed before publish."
    )
    if results.completed:
        st.markdown("**Full Success (CSV Appended)**")
        st.dataframe(results.completed, width="stretch", hide_index=True)
    if results.partial:
        st.markdown("**Partial (Published but CSV Pending)**")
        st.dataframe(results.partial, width="stretch", hide_index=True)
    if results.failed_pre_publish:
        st.markdown("**Failed Before Publish**")
        for item in results.failed_pre_publish:
            with st.expander(str(item.get("keyword", "unknown"))):
                st.json(item)

    csv_path = Path(str(results.csv_path or "").strip()) if str(results.csv_path or "").strip() else None
    summary_payload = _read_json_file(RUN_ROOT / run_id / SUMMARY_NAME)
    if isinstance(summary_payload, dict):
        csv_schedule = summary_payload.get("csv_schedule", {})
        if isinstance(csv_schedule, dict):
            first_publish_at = str(csv_schedule.get("first_publish_at", "")).strip() or "auto"
            cadence_minutes = int(csv_schedule.get("cadence_minutes", 0) or 0)
            timezone_name = str(csv_schedule.get("timezone", "")).strip()
            if cadence_minutes > 0:
                st.caption(
                    "CSV schedule: "
                    f"first slot `{first_publish_at}`, cadence `{cadence_minutes}` minutes, timezone `{timezone_name}`"
                )
            preview_slots = csv_schedule.get("preview_slots", [])
            if isinstance(preview_slots, list) and preview_slots:
                st.dataframe(preview_slots, width="stretch", hide_index=True)
    if csv_path is not None:
        st.caption(f"Expected Pinterest CSV path: `{csv_path}`")
    if csv_path is not None and csv_path.exists():
        st.download_button(
            "Download CSV",
            data=csv_path.read_bytes(),
            file_name=csv_path.name,
            mime="text/csv",
            key="bulk_download_csv",
        )
    if st.button("Retry CSV For Published Posts", key="bulk_retry_csv_replay"):
        try:
            replay = replay_pending_csv_sync(run_id=run_id, blog_suffix=opts.blog_suffix)
            st.info(
                "CSV replay finished: "
                f"{int(replay.get('recovered_count', 0))} recovered, "
                f"{int(replay.get('failed_count', 0))} still failed."
            )
            refreshed = _load_generation_results_from_run(run_id, RUN_ROOT / run_id)
            st.session_state.bulk_generation_results = refreshed
            st.session_state.bulk_last_error = None
            st.rerun()
        except Exception as exc:
            st.session_state.bulk_last_error = str(exc) or f"{type(exc).__name__}: {exc!r}"
            st.error(st.session_state.bulk_last_error)

    if st.button("Start New Run", key="bulk_new_run"):
        _reset_bulk_state(st)
        st.rerun()


def render_bulk_pipeline(
    *,
    st: Any,
    blog_configs: dict[str, dict[str, Any]],
    resolve_target_suffix: Callable[[str], str],
) -> None:
    """Render the bulk pipeline multi-stage wizard."""
    _init_bulk_state(st)
    st.caption("Configure and run the full Trends -> PinClicks -> WordPress pipeline from UI.")

    stage = int(st.session_state.bulk_stage)
    if stage == STAGE_CONFIG:
        _render_stage_config(st, blog_configs=blog_configs, resolve_target_suffix=resolve_target_suffix)
        return
    if stage == STAGE_TRENDS:
        _render_stage_trends(st)
        return
    if stage == STAGE_PINCLICKS:
        _render_stage_pinclicks(st)
        return
    _render_stage_generation(st)
