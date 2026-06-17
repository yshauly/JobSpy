from __future__ import annotations

import json
import unittest

from jobspy.meta import Meta
from jobspy.model import DescriptionFormat, ScraperInput, Site

META_CAREERS_URL = (
    "https://www.metacareers.com/jobsearch/"
    "?offices[0]=Tel%20Aviv%2C%20Israel"
)


class _FakeResponse:
    def __init__(self, *, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self) -> None:
        self.search_params: list[dict[str, object]] = []

    def get(self, url, params=None, timeout=None, verify=None):
        if url.endswith("/search/filter/"):
            self.search_params.append(dict(params or {}))
            fragment = """
                <div id="search_result">
                  <div>Viewing 1 Job Related To:</div>
                  <a href="/jobs/">Start a New Search</a>
                  <a class="_8sef" href="/jobs/24425919033670586/">
                    <div class="_8sel">Software Engineer, ML</div>
                    <div class="_8see">Tel Aviv, Israel</div>
                    <div class="_8see">Software Engineering</div>
                    <div class="_8see">Engineering</div>
                  </a>
                </div>
            """
            payload = {
                "domops": [["replace", "#search_result", False, {"__html": fragment}]]
            }
            return _FakeResponse(text="for (;;);" + json.dumps(payload))

        detail_payload = {
            "@context": "http://schema.org/",
            "@type": "JobPosting",
            "title": "Software Engineer, ML",
            "description": "Build ML systems.",
            "responsibilities": "Lead technical work.",
            "qualifications": "Experience with ML.",
            "datePosted": "2025-07-30T05:11:30-07:00",
            "jobLocation": [
                {
                    "@type": "Place",
                    "name": "Tel Aviv, Israel",
                }
            ],
        }
        return _FakeResponse(
            text=(
                '<html><head><script type="application/ld+json">'
                f"{json.dumps(detail_payload)}"
                "</script></head></html>"
            )
        )


class MetaTests(unittest.TestCase):
    def test_scrape_uses_search_fragment_and_hydrates_json_ld(self) -> None:
        scraper = Meta()
        fake_session = _FakeSession()
        scraper.session = fake_session

        result = scraper.scrape(
            ScraperInput(
                site_type=[Site.META],
                meta_careers_url=META_CAREERS_URL,
                results_wanted=1,
                description_limit=1,
                description_format=DescriptionFormat.MARKDOWN,
            )
        )

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(fake_session.search_params[0]["q"], "*")
        self.assertEqual(
            fake_session.search_params[0]["offices[0]"],
            "Tel Aviv, Israel",
        )
        job = result.jobs[0]
        self.assertEqual(job.id, "24425919033670586")
        self.assertEqual(job.company_name, "Meta")
        self.assertEqual(job.title, "Software Engineer, ML")
        self.assertEqual(job.location.display_location(), "Tel Aviv, Israel")
        self.assertEqual(
            job.job_url,
            "https://www.metacareers.com/jobs/24425919033670586/",
        )
        self.assertIn("## Description", job.description or "")
        self.assertEqual(job.date_posted.isoformat(), "2025-07-30")


if __name__ == "__main__":
    unittest.main()
