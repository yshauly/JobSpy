from __future__ import annotations

import unittest
from unittest.mock import patch

from jobspy.microsoft import DEFAULT_MICROSOFT_BASE_URL, Microsoft
from jobspy.model import JobPost, JobResponse, ScraperInput, Site


class MicrosoftTests(unittest.TestCase):
    def test_scrape_delegates_to_eightfold_with_normalized_apply_host(self) -> None:
        scraper = Microsoft()
        delegated_inputs: list[ScraperInput] = []

        def fake_eightfold_scrape(_, delegated_input: ScraperInput) -> JobResponse:
            delegated_inputs.append(delegated_input)
            return JobResponse(
                jobs=[
                    JobPost(
                        title="Software Engineer",
                        company_name="Microsoft",
                        job_url="https://apply.careers.microsoft.com/careers/job/1",
                        location=None,
                    )
                ]
            )

        with patch("jobspy.microsoft.Eightfold.scrape", autospec=True, side_effect=fake_eightfold_scrape):
            result = scraper.scrape(
                ScraperInput(
                    site_type=[Site.MICROSOFT],
                    microsoft_base_url=DEFAULT_MICROSOFT_BASE_URL,
                    results_wanted=1,
                )
            )

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(scraper.site, Site.MICROSOFT)
        self.assertEqual(len(delegated_inputs), 1)
        self.assertEqual(delegated_inputs[0].site_type, [Site.EIGHTFOLD])
        self.assertEqual(
            delegated_inputs[0].eightfold_company_url,
            "https://apply.careers.microsoft.com/careers?location=Israel",
        )


if __name__ == "__main__":
    unittest.main()
