from __future__ import annotations

import unittest
from unittest.mock import patch

import jobspy
from jobspy.model import JobResponse


class _FakeLinkedInScraper:
    init_kwargs: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs) -> None:
        type(self).init_kwargs.append(kwargs)

    def scrape(self, scraper_input) -> JobResponse:
        return JobResponse(jobs=[])


class ScrapeJobsLinkedInAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeLinkedInScraper.init_kwargs = []

    def test_scrape_jobs_auto_resolves_linkedin_auth_cookies(self) -> None:
        with patch.object(jobspy, "LinkedIn", _FakeLinkedInScraper):
            with patch.object(
                jobspy,
                "resolve_linkedin_auth_context",
                return_value=(
                    {
                        "li_at": "env-li-at",
                        "JSESSIONID": '"ajax:env"',
                    },
                    "env",
                ),
            ) as mock_resolve:
                jobs = jobspy.scrape_jobs(
                    site_name="linkedin",
                    results_wanted=1,
                    verbose=0,
                )

        self.assertTrue(jobs.empty)
        mock_resolve.assert_called_once_with()
        self.assertEqual(len(_FakeLinkedInScraper.init_kwargs), 1)
        self.assertEqual(
            _FakeLinkedInScraper.init_kwargs[0]["auth_cookies"],
            {
                "li_at": "env-li-at",
                "JSESSIONID": '"ajax:env"',
            },
        )

    def test_scrape_jobs_keeps_explicit_linkedin_auth_cookies(self) -> None:
        explicit_cookies = {
            "li_at": "explicit-li-at",
            "JSESSIONID": '"ajax:explicit"',
        }

        with patch.object(jobspy, "LinkedIn", _FakeLinkedInScraper):
            with patch.object(jobspy, "resolve_linkedin_auth_context") as mock_resolve:
                jobs = jobspy.scrape_jobs(
                    site_name="linkedin",
                    results_wanted=1,
                    verbose=0,
                    linkedin_auth_cookies=explicit_cookies,
                )

        self.assertTrue(jobs.empty)
        mock_resolve.assert_not_called()
        self.assertEqual(len(_FakeLinkedInScraper.init_kwargs), 1)
        self.assertEqual(
            _FakeLinkedInScraper.init_kwargs[0]["auth_cookies"],
            explicit_cookies,
        )
