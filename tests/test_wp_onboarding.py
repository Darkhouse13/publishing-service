import json
import unittest
from unittest.mock import Mock, patch

from automating_wf.wordpress.onboarding import OnboardingConfig, run_onboarding


def _response(payload: object, status_code: int = 200) -> Mock:
    response = Mock()
    response.status_code = status_code
    if payload is None:
        response.text = ""
        response.json.side_effect = ValueError("empty")
    else:
        response.text = json.dumps(payload)
        response.json.return_value = payload
    return response


def _privacy_stub() -> str:
    return (
        "Suggested text: Who we are. Comments. Cookies. "
        "Embedded content from other websites."
    )


class WordPressOnboardingTests(unittest.TestCase):
    def _config(self, dry_run: bool) -> OnboardingConfig:
        return OnboardingConfig(
            wp_url="https://example.com",
            wp_user="admin",
            wp_key="app-password",
            dry_run=dry_run,
            timezone="UTC",
            enable_indexing=False,
            default_comment_status="open",
            base_pages=("about", "contact", "privacy-policy"),
            seo_plugin="seo-by-rank-math",
            use_wp_cli=True,
            delete_default_plugins=True,
        )

    def test_default_post_lookup_uses_slug_and_never_calls_comments_endpoint(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_request(
            method: str,
            url: str,
            auth: object = None,
            params: dict[str, object] | None = None,
            json: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> Mock:
            del auth, timeout
            calls.append({"method": method, "url": url, "params": params, "json": json})
            if url.endswith("/users/me"):
                return _response({"id": 1, "name": "Admin", "slug": "admin"})
            if url.endswith("/settings"):
                return _response({"timezone": "UTC", "page_for_privacy_policy": 7})
            if url.endswith("/posts") and method == "GET":
                return _response([{"id": 101, "slug": "hello-world"}])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "sample-page":
                return _response([])
            if url.endswith("/media") and method == "GET":
                return _response([])
            if url.endswith("/pages/7") and method == "GET":
                return _response({"id": 7, "status": "draft", "content": {"raw": _privacy_stub()}})
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "about":
                return _response([])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "contact":
                return _response([])
            raise AssertionError(f"Unexpected request: {method} {url} {params}")

        with patch("automating_wf.wordpress.onboarding.requests.request", side_effect=fake_request):
            report = run_onboarding(self._config(dry_run=True))

        post_calls = [call for call in calls if call["url"].endswith("/posts")]
        self.assertEqual(len(post_calls), 1)
        params = post_calls[0]["params"]
        assert isinstance(params, dict)
        self.assertEqual(params.get("slug"), "hello-world")
        self.assertNotIn("search", params)
        self.assertFalse(any("/comments" in str(call["url"]) for call in calls))
        self.assertTrue(all(call["method"] == "GET" for call in calls))
        self.assertTrue(any("Delete starter post" in action for action in report.planned_actions))

    def test_unsupported_settings_never_post_timezone(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_request(
            method: str,
            url: str,
            auth: object = None,
            params: dict[str, object] | None = None,
            json: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> Mock:
            del auth, timeout
            calls.append({"method": method, "url": url, "params": params, "json": json})
            if url.endswith("/users/me"):
                return _response({"id": 1, "name": "Admin", "slug": "admin"})
            if url.endswith("/settings"):
                return _response({"page_for_privacy_policy": 7})
            if url.endswith("/posts") and method == "GET":
                return _response([])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "sample-page":
                return _response([])
            if url.endswith("/pages/7") and method == "GET":
                return _response(
                    {"id": 7, "status": "publish", "content": {"raw": "<p>Custom privacy text.</p>"}}
                )
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") in {"about", "contact"}:
                slug = str(params.get("slug"))
                return _response([{"id": 10 if slug == "about" else 11, "slug": slug}])
            raise AssertionError(f"Unexpected request: {method} {url} {params}")

        with patch("automating_wf.wordpress.onboarding.requests.request", side_effect=fake_request):
            report = run_onboarding(self._config(dry_run=False))

        self.assertFalse(
            any(call["method"] == "POST" and str(call["url"]).endswith("/settings") for call in calls)
        )
        self.assertTrue(
            any("wp option update timezone_string 'UTC'" in cmd for cmd in report.manual_wpcli_actions)
        )

    def test_privacy_policy_updates_in_place_without_delete(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_request(
            method: str,
            url: str,
            auth: object = None,
            params: dict[str, object] | None = None,
            json: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> Mock:
            del auth, timeout
            calls.append({"method": method, "url": url, "params": params, "json": json})
            if url.endswith("/users/me"):
                return _response({"id": 1, "name": "Admin", "slug": "admin"})
            if url.endswith("/settings"):
                return _response({"timezone": "UTC", "page_for_privacy_policy": 7})
            if url.endswith("/posts") and method == "GET":
                return _response([])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "sample-page":
                return _response([])
            if url.endswith("/pages/7") and method == "GET":
                return _response({"id": 7, "status": "draft", "content": {"raw": _privacy_stub()}})
            if url.endswith("/pages/7") and method == "POST":
                return _response({"id": 7, "status": "publish"})
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") in {"about", "contact"}:
                slug = str(params.get("slug"))
                return _response([{"id": 10 if slug == "about" else 11, "slug": slug}])
            raise AssertionError(f"Unexpected request: {method} {url} {params}")

        with patch("automating_wf.wordpress.onboarding.requests.request", side_effect=fake_request):
            run_onboarding(self._config(dry_run=False))

        self.assertTrue(
            any(
                call["method"] == "POST"
                and str(call["url"]).endswith("/pages/7")
                and isinstance(call["json"], dict)
                and call["json"].get("status") == "publish"
                for call in calls
            )
        )
        self.assertFalse(
            any(call["method"] == "DELETE" and str(call["url"]).endswith("/pages/7") for call in calls)
        )

    def test_base_pages_precheck_prevents_slug_duplicates(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_request(
            method: str,
            url: str,
            auth: object = None,
            params: dict[str, object] | None = None,
            json: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> Mock:
            del auth, timeout
            calls.append({"method": method, "url": url, "params": params, "json": json})
            if url.endswith("/users/me"):
                return _response({"id": 1, "name": "Admin", "slug": "admin"})
            if url.endswith("/settings"):
                return _response({"timezone": "UTC", "page_for_privacy_policy": 7})
            if url.endswith("/posts") and method == "GET":
                return _response([])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "sample-page":
                return _response([])
            if url.endswith("/pages/7") and method == "GET":
                return _response(
                    {"id": 7, "status": "publish", "content": {"raw": "<p>Custom privacy text.</p>"}}
                )
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "about":
                return _response([{"id": 10, "slug": "about"}])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "contact":
                return _response([])
            if url.endswith("/pages") and method == "POST":
                return _response({"id": 20, "slug": json.get("slug") if isinstance(json, dict) else ""})
            raise AssertionError(f"Unexpected request: {method} {url} {params}")

        with patch("automating_wf.wordpress.onboarding.requests.request", side_effect=fake_request):
            run_onboarding(self._config(dry_run=False))

        created_slugs = [
            call["json"].get("slug")
            for call in calls
            if call["method"] == "POST"
            and str(call["url"]).endswith("/pages")
            and isinstance(call["json"], dict)
        ]
        self.assertEqual(created_slugs, ["contact"])

    def test_dry_run_never_calls_mutating_endpoints(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_request(
            method: str,
            url: str,
            auth: object = None,
            params: dict[str, object] | None = None,
            json: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> Mock:
            del auth, timeout
            calls.append({"method": method, "url": url, "params": params, "json": json})
            if url.endswith("/users/me"):
                return _response({"id": 1, "name": "Admin", "slug": "admin"})
            if url.endswith("/settings"):
                return _response({"timezone": "Etc/GMT+1", "page_for_privacy_policy": 7})
            if url.endswith("/posts") and method == "GET":
                return _response([{"id": 101, "slug": "hello-world"}])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "sample-page":
                return _response([{"id": 202, "slug": "sample-page"}])
            if url.endswith("/media") and method == "GET":
                return _response([{"id": 303, "post": 101}])
            if url.endswith("/pages/7") and method == "GET":
                return _response({"id": 7, "status": "draft", "content": {"raw": _privacy_stub()}})
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") in {"about", "contact"}:
                return _response([])
            raise AssertionError(f"Unexpected request: {method} {url} {params}")

        with patch("automating_wf.wordpress.onboarding.requests.request", side_effect=fake_request):
            report = run_onboarding(self._config(dry_run=True))

        self.assertTrue(all(call["method"] == "GET" for call in calls))
        self.assertTrue(any("Delete starter post" in action for action in report.planned_actions))
        self.assertTrue(any("Delete sample page" in action for action in report.planned_actions))
        self.assertTrue(any("Delete starter media" in action for action in report.planned_actions))

    def test_apply_rerun_is_idempotent(self) -> None:
        calls: list[dict[str, object]] = []
        state: dict[str, object] = {
            "posts": [{"id": 101, "slug": "hello-world"}],
            "sample_page": [{"id": 202, "slug": "sample-page"}],
            "media": [{"id": 303, "post": 101}],
            "privacy_page": {"id": 7, "status": "draft", "content": {"raw": _privacy_stub()}},
            "about_exists": False,
            "contact_exists": False,
            "next_page_id": 500,
        }

        def fake_request(
            method: str,
            url: str,
            auth: object = None,
            params: dict[str, object] | None = None,
            json: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> Mock:
            del auth, timeout
            calls.append({"method": method, "url": url, "params": params, "json": json})

            if url.endswith("/users/me"):
                return _response({"id": 1, "name": "Admin", "slug": "admin"})
            if url.endswith("/settings"):
                return _response({"timezone": "UTC", "page_for_privacy_policy": 7})

            if url.endswith("/posts") and method == "GET":
                return _response(list(state["posts"]))
            if url.endswith("/posts/101") and method == "DELETE":
                state["posts"] = []
                state["media"] = [item for item in state["media"] if item["post"] != 101]
                return _response({"deleted": True})

            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "sample-page":
                return _response(list(state["sample_page"]))
            if url.endswith("/pages/202") and method == "DELETE":
                state["sample_page"] = []
                return _response({"deleted": True})

            if url.endswith("/media") and method == "GET":
                return _response(list(state["media"]))
            if url.endswith("/media/303") and method == "DELETE":
                state["media"] = []
                return _response({"deleted": True})

            if url.endswith("/pages/7") and method == "GET":
                return _response(dict(state["privacy_page"]))
            if url.endswith("/pages/7") and method == "POST":
                if isinstance(json, dict):
                    if "status" in json:
                        state["privacy_page"]["status"] = json["status"]
                    if "content" in json:
                        state["privacy_page"]["content"] = {"raw": json["content"]}
                return _response(dict(state["privacy_page"]))

            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "about":
                return _response([{"id": 610, "slug": "about"}] if state["about_exists"] else [])
            if url.endswith("/pages") and method == "GET" and params and params.get("slug") == "contact":
                return _response([{"id": 611, "slug": "contact"}] if state["contact_exists"] else [])
            if url.endswith("/pages") and method == "POST":
                if isinstance(json, dict) and json.get("slug") == "about":
                    state["about_exists"] = True
                if isinstance(json, dict) and json.get("slug") == "contact":
                    state["contact_exists"] = True
                state["next_page_id"] = int(state["next_page_id"]) + 1
                return _response({"id": int(state["next_page_id"]), "slug": json.get("slug")})

            raise AssertionError(f"Unexpected request: {method} {url} {params}")

        with patch("automating_wf.wordpress.onboarding.requests.request", side_effect=fake_request):
            run_onboarding(self._config(dry_run=False))
            run_onboarding(self._config(dry_run=False))

        delete_post_calls = [
            call
            for call in calls
            if call["method"] == "DELETE" and str(call["url"]).endswith("/posts/101")
        ]
        delete_sample_page_calls = [
            call
            for call in calls
            if call["method"] == "DELETE" and str(call["url"]).endswith("/pages/202")
        ]
        create_page_calls = [
            call
            for call in calls
            if call["method"] == "POST"
            and str(call["url"]).endswith("/pages")
            and isinstance(call["json"], dict)
            and call["json"].get("slug") in {"about", "contact"}
        ]
        self.assertEqual(len(delete_post_calls), 1)
        self.assertEqual(len(delete_sample_page_calls), 1)
        self.assertEqual(len(create_page_calls), 2)


if __name__ == "__main__":
    unittest.main()
