from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from automating_wf.config.blogs import (
    BLOG_CONFIGS,
    DEFAULT_BLOG_PROFILE,
    VIBE_SUGGESTION_COUNT,
    _sorted_category_names,
    fetch_vibes_for_blog,
    resolve_blog_config,
    resolve_blog_profile,
    resolve_target_suffix,
    suggest_primary_category,
)

TMP_DIR = Path("tmp")
REQUIRED_SEO_PUBLISH_FIELDS = (
    "article_markdown",
    "seo_title",
    "meta_description",
    "focus_keyword",
)


def maybe_autofill_topic(
    selected_vibe: str,
    current_topic: str,
    topic_is_custom: bool,
) -> tuple[str, str]:
    if topic_is_custom or not selected_vibe.strip():
        return current_topic, ""
    return selected_vibe.strip(), selected_vibe.strip()


def reconcile_topic_flags(
    previous_topic: str,
    current_topic: str,
    topic_is_custom: bool,
    last_autofilled_topic: str,
) -> tuple[bool, str]:
    if not current_topic.strip():
        return False, ""
    if current_topic == previous_topic:
        return topic_is_custom, last_autofilled_topic
    if current_topic == last_autofilled_topic:
        return False, last_autofilled_topic
    return True, last_autofilled_topic


def sanitize_article_markdown_for_preview(title: str, content_markdown: str) -> tuple[str, bool]:
    from automating_wf.wordpress.uploader import strip_duplicate_leading_h1

    return strip_duplicate_leading_h1(
        content_markdown=content_markdown,
        title=title,
    )


def missing_seo_publish_fields(article_payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(article_payload, dict):
        return list(REQUIRED_SEO_PUBLISH_FIELDS)
    missing: list[str] = []
    for field in REQUIRED_SEO_PUBLISH_FIELDS:
        value = article_payload.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


def _init_session_state(st: Any) -> None:
    blog_options = list(BLOG_CONFIGS.keys())

    if (
        "selected_blog" not in st.session_state
        or st.session_state.selected_blog not in BLOG_CONFIGS
    ):
        if DEFAULT_BLOG_PROFILE in BLOG_CONFIGS:
            st.session_state.selected_blog = DEFAULT_BLOG_PROFILE
        else:
            st.session_state.selected_blog = blog_options[0]
    if "topic" not in st.session_state:
        st.session_state.topic = ""
    if "topic_is_custom" not in st.session_state:
        st.session_state.topic_is_custom = False
    if "last_autofilled_topic" not in st.session_state:
        st.session_state.last_autofilled_topic = ""
    if "vibe_options" not in st.session_state:
        st.session_state.vibe_options = []
    if "selected_vibe" not in st.session_state:
        st.session_state.selected_vibe = ""
    if "vibe_source_blog" not in st.session_state:
        st.session_state.vibe_source_blog = ""
    if "vibe_generation_error" not in st.session_state:
        st.session_state.vibe_generation_error = None
    if "article_payload" not in st.session_state:
        st.session_state.article_payload = None
    if "hero_image_path" not in st.session_state:
        st.session_state.hero_image_path = None
    if "detail_image_path" not in st.session_state:
        st.session_state.detail_image_path = None
    if "publish_result" not in st.session_state:
        st.session_state.publish_result = None
    if "category_options" not in st.session_state:
        st.session_state.category_options = []
    if "selected_category_name" not in st.session_state:
        st.session_state.selected_category_name = ""
    if "category_fetch_error" not in st.session_state:
        st.session_state.category_fetch_error = None
    if "last_suggested_category" not in st.session_state:
        st.session_state.last_suggested_category = ""
    if "article_failure_stage" not in st.session_state:
        st.session_state.article_failure_stage = ""
    if "article_generation_errors" not in st.session_state:
        st.session_state.article_generation_errors = []
    if "article_validator_errors" not in st.session_state:
        st.session_state.article_validator_errors = []
    if "article_validator_attempts" not in st.session_state:
        st.session_state.article_validator_attempts = []
    if "article_validator_artifact_dir" not in st.session_state:
        st.session_state.article_validator_artifact_dir = None


def _get_selected_index(options: list[str], selected_value: str) -> int:
    if not options:
        return 0
    if selected_value in options:
        return options.index(selected_value)
    return 0


def _refresh_vibes(st: Any, generate_vibe_bank: Any) -> None:
    try:
        vibes = fetch_vibes_for_blog(
            selected_blog=st.session_state.selected_blog,
            generator=generate_vibe_bank,
            count=VIBE_SUGGESTION_COUNT,
        )
    except Exception as exc:
        st.session_state.vibe_generation_error = str(exc)
        st.session_state.vibe_options = []
        st.session_state.selected_vibe = ""
        st.session_state.vibe_source_blog = st.session_state.selected_blog
        return

    st.session_state.vibe_generation_error = None
    st.session_state.vibe_options = vibes
    st.session_state.vibe_source_blog = st.session_state.selected_blog

    if not vibes:
        st.session_state.selected_vibe = ""
        return

    if st.session_state.selected_vibe not in vibes:
        st.session_state.selected_vibe = vibes[0]

    topic, autofilled = maybe_autofill_topic(
        selected_vibe=st.session_state.selected_vibe,
        current_topic=st.session_state.topic,
        topic_is_custom=st.session_state.topic_is_custom,
    )
    if autofilled:
        st.session_state.topic = topic
        st.session_state.last_autofilled_topic = autofilled


def _render_single_article_tab() -> None:
    import streamlit as st

    from automating_wf.content.generators import GenerationError, generate_vibe_bank
    from automating_wf.content.single_article_flow import (
        SingleArticleDraftError,
        generate_single_article_draft,
    )
    from automating_wf.wordpress.uploader import (
        WordPressUploadError,
        list_categories,
        publish_post,
        resolve_category_id,
    )

    st.title(st.session_state.selected_blog)
    st.caption("Generate SEO blog drafts with DeepSeek + Fal and publish to WordPress.")

    with st.sidebar:
        st.header("Settings")

        def reset_blog_state() -> None:
            st.session_state.category_options = []
            st.session_state.selected_category_name = ""
            st.session_state.category_fetch_error = None
            st.session_state.last_suggested_category = ""
            st.session_state.publish_result = None
            st.session_state.vibe_options = []
            st.session_state.selected_vibe = ""
            st.session_state.vibe_source_blog = ""
            st.session_state.article_failure_stage = ""
            st.session_state.article_generation_errors = []
            st.session_state.article_validator_errors = []
            st.session_state.article_validator_attempts = []
            st.session_state.article_validator_artifact_dir = None

        blog_options = list(BLOG_CONFIGS.keys())
        blog_index = _get_selected_index(blog_options, st.session_state.selected_blog)
        st.selectbox(
            "Blog",
            options=blog_options,
            index=blog_index,
            key="selected_blog",
            on_change=reset_blog_state,
        )

        selected_blog = st.session_state.selected_blog
        selected_blog_config = resolve_blog_config(selected_blog)
        target_suffix = resolve_target_suffix(selected_blog)
        target_url = os.getenv(f"WP_URL_{target_suffix}", "").strip().rstrip("/")
        if target_url:
            st.caption(f"Destination: `{target_url}`")
        else:
            st.warning(
                "Missing destination URL for selected blog. "
                f"Set `WP_URL_{target_suffix}` in `.env`."
            )

        refresh_clicked = st.button("Refresh Suggestions")
        needs_refresh = (
            refresh_clicked
            or st.session_state.vibe_source_blog != st.session_state.selected_blog
            or not st.session_state.vibe_options
        )
        if needs_refresh:
            _refresh_vibes(st, generate_vibe_bank)

        if st.session_state.vibe_options:
            previous_vibe = st.session_state.selected_vibe
            vibe_index = _get_selected_index(
                st.session_state.vibe_options, st.session_state.selected_vibe
            )
            selected_vibe = st.selectbox(
                "Vibe/Style Suggestions",
                options=st.session_state.vibe_options,
                index=vibe_index,
            )
            st.session_state.selected_vibe = selected_vibe

            if selected_vibe != previous_vibe:
                topic, autofilled = maybe_autofill_topic(
                    selected_vibe=selected_vibe,
                    current_topic=st.session_state.topic,
                    topic_is_custom=st.session_state.topic_is_custom,
                )
                if autofilled:
                    st.session_state.topic = topic
                    st.session_state.last_autofilled_topic = autofilled
        else:
            st.info("No vibe suggestions available. You can still type a custom topic below.")

        if st.session_state.vibe_generation_error:
            st.warning(f"Suggestion generation failed: {st.session_state.vibe_generation_error}")

        refresh_categories_clicked = st.button("Refresh Categories")
        needs_category_refresh = (
            refresh_categories_clicked or not st.session_state.category_options
        )
        if needs_category_refresh:
            # Keep category lookups uncached for now. If cache_data is added later,
            # include target_suffix in the cache key to avoid cross-blog bleed.
            try:
                category_payload = list_categories(target_suffix=target_suffix)
                st.session_state.category_options = _sorted_category_names(
                    [str(item.get("name", "")).strip() for item in category_payload],
                    deprioritized_category=str(
                        selected_blog_config.get("deprioritized_category", "")
                    ),
                )
                st.session_state.category_fetch_error = None
            except WordPressUploadError as exc:
                st.session_state.category_options = []
                st.session_state.category_fetch_error = str(exc)

        category_options = st.session_state.category_options
        if st.session_state.category_fetch_error:
            st.warning(f"Category load failed: {st.session_state.category_fetch_error}")
        elif category_options:
            article_for_category = st.session_state.article_payload
            suggestion_title = st.session_state.topic
            suggestion_content = st.session_state.selected_vibe
            if isinstance(article_for_category, dict):
                suggestion_title = str(article_for_category.get("title", suggestion_title))
                suggestion_content = str(
                    article_for_category.get("content_markdown", suggestion_content)
                )

            suggested_category = suggest_primary_category(
                title=suggestion_title,
                content_markdown=suggestion_content,
                category_names=category_options,
                fallback_category=str(selected_blog_config.get("fallback_category", "")),
                deprioritized_category=str(
                    selected_blog_config.get("deprioritized_category", "")
                ),
                category_keywords=dict(selected_blog_config.get("category_keywords", {})),
            )
            previous_suggested = st.session_state.last_suggested_category
            current_selected = st.session_state.selected_category_name
            if current_selected not in category_options:
                current_selected = ""

            if not current_selected or current_selected == previous_suggested:
                st.session_state.selected_category_name = suggested_category
            st.session_state.last_suggested_category = suggested_category

            category_index = _get_selected_index(
                category_options, st.session_state.selected_category_name
            )
            st.selectbox(
                "Primary Category",
                options=category_options,
                index=category_index,
                key="selected_category_name",
            )
            st.caption(f"Suggested category: `{suggested_category}`")
        else:
            st.warning(
                "No categories found in WordPress for this blog. "
                "Add one in WP Admin, then refresh categories."
            )

        post_status = os.getenv("WP_POST_STATUS", "draft")
        st.caption(f"WordPress publish status: `{post_status}`")

    previous_topic = st.session_state.topic
    st.text_input(
        "Topic",
        key="topic",
        placeholder="Small Patio Makeover for Weekend Relaxation",
    )
    st.session_state.topic_is_custom, st.session_state.last_autofilled_topic = reconcile_topic_flags(
        previous_topic=previous_topic,
        current_topic=st.session_state.topic,
        topic_is_custom=st.session_state.topic_is_custom,
        last_autofilled_topic=st.session_state.last_autofilled_topic,
    )

    if st.button("Generate Draft", type="primary", disabled=not st.session_state.topic.strip()):
        try:
            if hasattr(st, "status"):
                with st.status("Generating article...", expanded=True) as status:
                    try:
                        draft_result = generate_single_article_draft(
                            topic=st.session_state.topic.strip(),
                            vibe=st.session_state.selected_vibe,
                            blog_profile=resolve_blog_profile(st.session_state.selected_blog),
                            out_dir=TMP_DIR,
                        )
                        status.update(label="Article generated!", state="complete")
                    except Exception:
                        status.update(label="Generation failed", state="error")
                        raise
            else:
                with st.spinner("Generating article and images..."):
                    draft_result = generate_single_article_draft(
                        topic=st.session_state.topic.strip(),
                        vibe=st.session_state.selected_vibe,
                        blog_profile=resolve_blog_profile(st.session_state.selected_blog),
                        out_dir=TMP_DIR,
                    )

            st.session_state.article_payload = dict(draft_result.article_payload)
            st.session_state.hero_image_path = str(draft_result.hero_image_path)
            st.session_state.detail_image_path = str(draft_result.detail_image_path)
            st.session_state.publish_result = None
            st.session_state.article_failure_stage = ""
            st.session_state.article_generation_errors = []
            st.session_state.article_validator_errors = []
            st.session_state.article_validator_attempts = []
            st.session_state.article_validator_artifact_dir = str(draft_result.validator_artifact_dir)
            if draft_result.validator_repaired:
                st.info(
                    "Validator repaired the draft before image generation "
                    f"({draft_result.validator_attempts_used} attempt(s))."
                )
            st.success("Draft generated. Review the preview before publishing.")
        except SingleArticleDraftError as exc:
            st.error(f"Article generation failed: {exc}")
            st.session_state.article_payload = None
            st.session_state.hero_image_path = None
            st.session_state.detail_image_path = None
            st.session_state.publish_result = None
            st.session_state.article_failure_stage = str(exc.failure_stage or "article_failed")
            st.session_state.article_generation_errors = list(exc.generation_errors or [])
            st.session_state.article_validator_errors = list(exc.validator_errors or [])
            st.session_state.article_validator_attempts = list(exc.validator_attempts or [])
            if exc.validator_artifact_dir is not None:
                st.session_state.article_validator_artifact_dir = str(exc.validator_artifact_dir)
            else:
                st.session_state.article_validator_artifact_dir = None
        except GenerationError as exc:
            st.error(f"Generation failed: {exc}")
            st.session_state.article_payload = None
            st.session_state.hero_image_path = None
            st.session_state.detail_image_path = None
            st.session_state.publish_result = None
            st.session_state.article_failure_stage = ""
            st.session_state.article_generation_errors = []
            st.session_state.article_validator_errors = []
            st.session_state.article_validator_attempts = []
            st.session_state.article_validator_artifact_dir = None

    article_payload = st.session_state.article_payload
    hero_image_path = st.session_state.hero_image_path
    detail_image_path = st.session_state.detail_image_path
    article_failure_stage = str(st.session_state.article_failure_stage or "").strip()
    article_generation_errors = list(st.session_state.article_generation_errors or [])
    article_validator_errors = list(st.session_state.article_validator_errors or [])
    article_validator_attempts = list(st.session_state.article_validator_attempts or [])
    article_validator_artifact_dir = str(st.session_state.article_validator_artifact_dir or "").strip()

    if article_failure_stage == "article_failed":
        st.error("Latest draft failed at `article_failed` before image generation/publish.")
        if article_generation_errors:
            st.write("Generation errors:")
            for error in article_generation_errors:
                st.error(str(error))
        if article_validator_errors:
            st.write("Validator errors:")
            for error in article_validator_errors:
                st.error(str(error))
        with st.expander("Validator Diagnostic Details"):
            if article_validator_artifact_dir:
                st.caption(f"Validator artifacts: `{article_validator_artifact_dir}`")
            if article_validator_attempts:
                st.json(article_validator_attempts)
            else:
                st.caption("No validator attempts recorded.")

    if article_payload:
        st.subheader(article_payload["title"])
        st.write(f"**Selected blog:** {st.session_state.selected_blog}")
        st.write(f"**Selected vibe:** {st.session_state.selected_vibe}")

        preview_source_markdown = str(
            article_payload.get("article_markdown", article_payload.get("content_markdown", ""))
        )
        preview_markdown, stripped_duplicate_h1 = sanitize_article_markdown_for_preview(
            title=str(article_payload.get("title", "")),
            content_markdown=preview_source_markdown,
        )
        with st.expander("Article Preview", expanded=True):
            if stripped_duplicate_h1:
                st.caption("Note: duplicate top title heading removed before publish.")
            st.markdown(preview_markdown)

        with st.expander("Generated Image Prompts"):
            st.write(f"**Hero Prompt:** {article_payload['hero_image_prompt']}")
            st.write(f"**Detail Prompt:** {article_payload['detail_image_prompt']}")

        if hero_image_path and detail_image_path:
            left, right = st.columns(2)
            with left:
                st.image(hero_image_path, caption="Hero Image Preview", width="stretch")
            with right:
                st.image(detail_image_path, caption="Detail Image Preview", width="stretch")

    has_category_choice = bool(st.session_state.selected_category_name.strip())
    missing_seo_fields = missing_seo_publish_fields(article_payload)
    has_required_seo_fields = not missing_seo_fields
    if article_payload and not has_required_seo_fields:
        st.warning(
            "Generated draft is missing required SEO fields for publish: "
            + ", ".join(missing_seo_fields)
            + ". Regenerate draft before publishing."
        )

    can_publish = bool(
        article_payload
        and hero_image_path
        and detail_image_path
        and has_category_choice
        and not st.session_state.category_fetch_error
        and has_required_seo_fields
    )
    if st.button("Publish to WordPress", disabled=not can_publish):
        try:
            with st.spinner("Publishing draft to WordPress..."):
                if missing_seo_fields:
                    raise WordPressUploadError(
                        "Draft is missing required SEO fields ("
                        + ", ".join(missing_seo_fields)
                        + "). Regenerate the draft and try again."
                    )

                try:
                    category_id = resolve_category_id(
                        selected_name=st.session_state.selected_category_name,
                        typed_new_name="",
                        target_suffix=target_suffix,
                    )
                except WordPressUploadError:
                    # Re-fetch once in case category state changed between load and publish.
                    category_payload = list_categories(target_suffix=target_suffix)
                    st.session_state.category_options = _sorted_category_names(
                        [str(item.get("name", "")).strip() for item in category_payload],
                        deprioritized_category=str(
                            selected_blog_config.get("deprioritized_category", "")
                        ),
                    )
                    st.session_state.category_fetch_error = None
                    category_id = resolve_category_id(
                        selected_name=st.session_state.selected_category_name,
                        typed_new_name="",
                        target_suffix=target_suffix,
                    )

                publish_result = publish_post(
                    title=article_payload["title"],
                    content_markdown=article_payload.get(
                        "article_markdown", article_payload["content_markdown"]
                    ),
                    hero_path=Path(hero_image_path),
                    detail_path=Path(detail_image_path),
                    focus_keyword=str(article_payload["focus_keyword"]),
                    meta_description=str(article_payload["meta_description"]),
                    seo_title=str(article_payload["seo_title"]),
                    status=os.getenv("WP_POST_STATUS", "draft"),
                    category_id=category_id,
                    target_suffix=target_suffix,
                )

            st.session_state.publish_result = publish_result
            st.success(f"Post published successfully to {selected_blog}.")
        except WordPressUploadError as exc:
            st.error(f"WordPress upload failed: {exc}")

    if st.session_state.publish_result:
        publish_result = st.session_state.publish_result
        st.write(f"**Post ID:** {publish_result['post_id']}")
        st.write(f"**Status:** {publish_result['status']}")
        if publish_result.get("post_url"):
            st.write(f"**Post URL:** {publish_result['post_url']}")
        publish_warnings = publish_result.get("publish_warnings")
        if isinstance(publish_warnings, list) and publish_warnings:
            for warning in publish_warnings:
                st.warning(str(warning))
        st.json(publish_result)


def main() -> None:
    import streamlit as st
    from dotenv import load_dotenv

    load_dotenv()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    st.set_page_config(page_title="Blog Publisher", layout="wide")
    _init_session_state(st)

    tab_single, tab_bulk = st.tabs(["Single Article", "Bulk Pipeline"])
    with tab_single:
        _render_single_article_tab()
    with tab_bulk:
        from automating_wf.ui.bulk_pipeline import render_bulk_pipeline

        render_bulk_pipeline(
            st=st,
            blog_configs=BLOG_CONFIGS,
            resolve_target_suffix=resolve_target_suffix,
        )


if __name__ == "__main__":
    main()
