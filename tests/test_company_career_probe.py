from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from jobspy import company_career_probe


class FakeResponse:
    def __init__(self, text: str = "", payload=None) -> None:
        self.text = text
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.headers = {}

    def get(self, url: str, **kwargs):
        return self.responses[url]


class CompanyCareerProbeTests(unittest.TestCase):
    def test_detects_greenhouse_public_board_from_page_script(self) -> None:
        session = FakeSession(
            {
                "https://www.nice.com/careers/apply": FakeResponse(
                    '<script src="/_next/static/chunks/jobs.js"></script>'
                ),
                "https://www.nice.com/_next/static/chunks/jobs.js": FakeResponse(
                    'fetch("https://boards-api.greenhouse.io/v1/boards/nice/jobs?content=true")'
                ),
            }
        )

        with patch(
            "jobspy.company_career_probe._build_session",
            return_value=session,
        ):
            detected = company_career_probe.detect_company_career_page(
                company_name="NICE",
                career_page_url="https://www.nice.com/careers/apply",
            )

        self.assertEqual(detected.detected_platform, "greenhouse_public_board")
        self.assertEqual(detected.scraper_site, "json_feed")
        self.assertEqual(
            detected.resolved_fetch_url,
            "https://boards-api.greenhouse.io/v1/boards/nice/jobs?content=true",
        )
        self.assertEqual(
            detected.extra_params["json_feed_config"]["field_paths"]["job_function"],
            "metadata.Category.value",
        )

    def test_probe_validates_and_builds_row_for_public_greenhouse_board(self) -> None:
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "json_feed",
                    "id": "4894768101",
                    "title": "AI AML Product Manager",
                    "company": "NICE",
                    "location": "Israel - Raanana, Israel",
                    "job_url": (
                        "https://boards.eu.greenhouse.io/nice/jobs/4894768101"
                        "?gh_jid=4894768101"
                    ),
                    "apply_url": (
                        "https://boards.eu.greenhouse.io/nice/jobs/4894768101"
                        "?gh_jid=4894768101"
                    ),
                    "description": "Build products",
                    "listing_type": "Regular",
                    "job_function": "Product",
                }
            ]
        )
        scrape_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch(
            "jobspy.company_career_probe.scrape_jobs",
            side_effect=fake_scrape_jobs,
        ):
            result = company_career_probe.probe_company_career_page(
                company_name="NICE",
                company_key="nice",
                career_page_url=(
                    "https://boards-api.greenhouse.io/v1/boards/nice/jobs?content=true"
                ),
                location="Israel",
                sample_size=3,
            )

        self.assertTrue(result["valid"])
        self.assertEqual(result["detected_platform"], "greenhouse_public_board")
        self.assertEqual(result["row"]["company_key"], "nice")
        self.assertEqual(result["row"]["scraper_site"], "json_feed")
        self.assertEqual(
            result["row"]["resolved_fetch_url"],
            "https://boards-api.greenhouse.io/v1/boards/nice/jobs?content=true",
        )
        self.assertEqual(result["jobs_found"], 1)
        self.assertEqual(result["normalized_records"][0]["source"], "json_feed")
        self.assertEqual(scrape_calls[0]["site_name"], "json_feed")
        self.assertEqual(scrape_calls[0]["results_wanted"], 3)


if __name__ == "__main__":
    unittest.main()
