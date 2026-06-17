from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from jobspy.glassdoor import Glassdoor
from jobspy.model import JobPost, ScraperInput, Site


class _FakeResponse:
    status_code = 200

    def json(self):
        return [
            {
                "data": {
                    "jobListings": {
                        "jobListings": [
                            {"jobview": {"job": {"listingId": "1"}}},
                            {"jobview": {"job": {"listingId": "2"}}},
                            {"jobview": {"job": {"listingId": "3"}}},
                        ],
                        "paginationCursors": [
                            {"pageNumber": 2, "cursor": "cursor-page-2"},
                        ],
                    }
                }
            }
        ]


class _FakeSession:
    def post(self, url, timeout_seconds=15, data=None):
        return _FakeResponse()


class _FakeDetailResponse:
    status_code = 200

    def json(self):
        return [
            {
                "data": {
                    "jobview": {
                        "job": {
                            "description": "<p>Hello <strong>world</strong></p>",
                        }
                    }
                }
            }
        ]


class _FakeDetailSession:
    def post(self, url, json=None, timeout_seconds=15):
        return _FakeDetailResponse()


class GlassdoorTests(unittest.TestCase):
    def test_fetch_jobs_page_preserves_search_order(self) -> None:
        scraper = Glassdoor()
        scraper.session = _FakeSession()
        scraper.base_url = "https://www.glassdoor.com/"
        scraper.jobs_per_page = 3
        scraper.scraper_input = ScraperInput(
            site_type=[Site.GLASSDOOR],
            search_term=None,
            location="Israel",
            results_wanted=3,
            description_limit=0,
        )

        def fake_process_job(job_data, fetch_description=False):
            listing_id = job_data["jobview"]["job"]["listingId"]
            time.sleep(0.04 - (int(listing_id) * 0.01))
            return JobPost(
                id=f"gd-{listing_id}",
                title=f"Job {listing_id}",
                company_name="Acme",
                job_url=f"https://example.com/jobs/{listing_id}",
                location=None,
            )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            jobs, cursor = scraper._fetch_jobs_page(
                scraper.scraper_input,
                location_id=119,
                location_type="COUNTRY",
                page_num=1,
                cursor=None,
            )

        self.assertEqual([job.id for job in jobs], ["gd-1", "gd-2", "gd-3"])
        self.assertEqual(cursor, "cursor-page-2")

    def test_fetch_job_description_uses_session_and_parses_markdown(self) -> None:
        scraper = Glassdoor()
        scraper.session = _FakeDetailSession()
        scraper.base_url = "https://www.glassdoor.com/"
        scraper.scraper_input = ScraperInput(
            site_type=[Site.GLASSDOOR],
            search_term=None,
            location="Israel",
            results_wanted=1,
        )

        description = scraper._fetch_job_description("123")

        self.assertEqual(description, "Hello **world**")


if __name__ == "__main__":
    unittest.main()
