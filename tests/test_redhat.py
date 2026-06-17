from __future__ import annotations

import unittest
from unittest.mock import patch

from jobspy.model import JobPost, JobResponse, ScraperInput, Site
from jobspy.redhat import DEFAULT_REDHAT_BASE_URL, RedHat


class RedHatTests(unittest.TestCase):
    def test_scrape_delegates_to_workday_with_israel_defaults(self) -> None:
        scraper = RedHat()
        delegated_inputs: list[ScraperInput] = []

        def fake_workday_scrape(_, delegated_input: ScraperInput) -> JobResponse:
            delegated_inputs.append(delegated_input)
            return JobResponse(
                jobs=[
                    JobPost(
                        title="Senior Software Engineer",
                        company_name="Careers at Red Hat",
                        job_url="https://example.com/job/1",
                        location=None,
                    )
                ]
            )

        with patch("jobspy.redhat.Workday.scrape", autospec=True, side_effect=fake_workday_scrape):
            result = scraper.scrape(
                ScraperInput(
                    site_type=[Site.REDHAT],
                    results_wanted=1,
                    redhat_debug_trace=True,
                )
            )

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(len(delegated_inputs), 1)
        self.assertEqual(scraper.site, Site.REDHAT)
        self.assertEqual(result.jobs[0].company_name, "Red Hat")
        self.assertEqual(delegated_inputs[0].site_type, [Site.WORKDAY])
        self.assertEqual(
            delegated_inputs[0].workday_company_url,
            DEFAULT_REDHAT_BASE_URL,
        )
        self.assertTrue(delegated_inputs[0].workday_debug_trace)


if __name__ == "__main__":
    unittest.main()
