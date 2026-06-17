from __future__ import annotations

import os
import unittest
import uuid
from pathlib import Path
import shutil
from unittest.mock import patch

import jobspy.chromium_cookies as chromium_cookies


class ChromiumCookieResolutionTests(unittest.TestCase):
    def test_resolve_linkedin_auth_context_prefers_browser_cookies_before_hardcoded(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cookies, auth_source = chromium_cookies.resolve_linkedin_auth_context(
                builtin_cookie_loader=lambda: {
                    "li_at": "hardcoded-li-at",
                    "JSESSIONID": '"ajax:hardcoded"',
                },
                browser_cookie_loader=lambda: (
                    {"li_at": "browser-li-at"},
                    "browser:chrome/Default",
                ),
            )

        self.assertEqual(
            cookies,
            {
                "li_at": "browser-li-at",
            },
        )
        self.assertEqual(auth_source, "browser:chrome/Default")

    def test_resolve_linkedin_auth_context_uses_env_cookies_before_browser(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LINKEDIN_LI_AT": "env-li-at",
                "LINKEDIN_JSESSIONID": '"ajax:env"',
            },
            clear=True,
        ):
            cookies, auth_source = chromium_cookies.resolve_linkedin_auth_context(
                browser_cookie_loader=lambda: (
                    {"li_at": "browser-li-at"},
                    "browser:chrome/Default",
                )
            )

        self.assertEqual(
            cookies,
            {
                "li_at": "env-li-at",
                "JSESSIONID": '"ajax:env"',
            },
        )
        self.assertEqual(auth_source, "env")

    def test_resolve_linkedin_auth_context_returns_guest_only_when_all_sources_empty(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cookies, auth_source = chromium_cookies.resolve_linkedin_auth_context(
                builtin_cookie_loader=lambda: {},
                browser_cookie_loader=lambda: ({}, None),
            )

        self.assertEqual(cookies, {})
        self.assertEqual(auth_source, "guest-only")

    def test_discover_chromium_profile_cookie_stores_includes_workspace_style_profile(
        self,
    ) -> None:
        temp_dir = Path.cwd() / f"tmp-chromium-cookie-test-{uuid.uuid4().hex}"
        try:
            user_data_dir = temp_dir / "jobspy-chrome-test"
            cookie_db_path = user_data_dir / "Default" / "Network" / "Cookies"
            cookie_db_path.parent.mkdir(parents=True, exist_ok=True)
            cookie_db_path.write_bytes(b"")

            with patch.object(
                chromium_cookies,
                "_discover_chromium_user_data_roots",
                return_value=[("jobspy-chrome", user_data_dir)],
            ):
                cookie_stores = chromium_cookies._discover_chromium_profile_cookie_stores()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual(len(cookie_stores), 1)
        self.assertEqual(cookie_stores[0].browser_name, "jobspy-chrome")
        self.assertEqual(cookie_stores[0].cookie_db_path, cookie_db_path)
