from __future__ import annotations

import html
import json
import unittest
from unittest.mock import patch

from requests.cookies import RequestsCookieJar

from jobspy.greenhouse import Greenhouse
from jobspy.model import DescriptionFormat, ScraperInput, Site


class _FakeResponse:
    def __init__(
        self,
        *,
        text: str | None = None,
        json_data=None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        url: str = "https://my.greenhouse.io/jobs",
    ) -> None:
        self.text = text or ""
        self._json_data = json_data
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeGreenhouseSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = RequestsCookieJar()
        self.bootstrap_headers: list[dict[str, str]] = []
        self.inertia_headers: list[dict[str, str]] = []

    def get(
        self,
        url,
        headers=None,
        timeout=None,
        verify=None,
        allow_redirects=True,
    ):
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)

        if merged_headers.get("x-inertia") == "true":
            self.inertia_headers.append(merged_headers)
            return _FakeResponse(
                json_data={
                    "component": "job_search",
                    "props": {
                        "page": 1,
                        "moreResultsAvailable": False,
                        "jobPosts": [
                            {
                                "id": 101,
                                "title": "Backend Engineer",
                                "companyName": "Acme",
                                "publicUrl": "https://boards.greenhouse.io/acme/jobs/101",
                                "locations": ["Tel Aviv, Israel"],
                                "workType": "hybrid",
                                "firstPublished": "2026-05-01T12:00:00Z",
                            }
                        ],
                    },
                },
                headers={
                    "content-type": "application/json; charset=utf-8",
                    "x-inertia": "true",
                },
                url=url,
            )

        self.bootstrap_headers.append(merged_headers)
        accept_header = merged_headers.get("Accept") or merged_headers.get("accept") or ""
        if "text/html" not in accept_header:
            return _FakeResponse(status_code=406, url=url)

        data_page = {
            "component": "job_search",
            "version": "test-version",
            "props": {},
        }
        bootstrap_html = (
            "<div "
            f'data-page="{html.escape(json.dumps(data_page), quote=True)}"'
            "></div>"
        )
        return _FakeResponse(text=bootstrap_html, url=url)


class GreenhouseTests(unittest.TestCase):
    def test_scrape_bootstrap_uses_html_accept_header(self) -> None:
        fake_session = _FakeGreenhouseSession()
        with patch("jobspy.greenhouse.create_session", return_value=fake_session):
            scraper = Greenhouse(
                auth_cookies={
                    "_session_id": "session",
                    "MYGREENHOUSE-XSRF-TOKEN": "xsrf-token",
                }
            )

            result = scraper.scrape(
                ScraperInput(
                    site_type=[Site.GREENHOUSE],
                    location="Israel",
                    results_wanted=1,
                    description_limit=0,
                    description_format=DescriptionFormat.MARKDOWN,
                )
            )

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].title, "Backend Engineer")
        self.assertEqual(
            fake_session.bootstrap_headers[0]["Accept"],
            "text/html, application/xhtml+xml",
        )
        self.assertEqual(
            fake_session.inertia_headers[0]["accept"],
            "text/html, application/xhtml+xml",
        )


if __name__ == "__main__":
    unittest.main()
