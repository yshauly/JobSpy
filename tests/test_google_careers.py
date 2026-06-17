from __future__ import annotations

import html
import json
import unittest

from jobspy.google_careers import (
    DEFAULT_GOOGLE_CAREERS_URL,
    GoogleCareers,
)
from jobspy.model import DescriptionFormat, ScraperInput, Site


def _build_job(
    *,
    job_id: str,
    title: str,
    city: str,
    state: str,
    company_name: str = "Google",
    overview: str = "Build products used worldwide.",
    apply_url: str | None = None,
) -> list[object]:
    effective_apply_url = apply_url or (
        "https://www.google.com/about/careers/applications/signin"
        f"?jobId={job_id}"
    )
    return [
        job_id,
        title,
        effective_apply_url,
        [None, "<ul><li>Ship reliable services.</li><li>Improve systems.</li></ul>"],
        [
            None,
            (
                "<h3>Minimum qualifications:</h3><ul><li>Python</li></ul>"
                "<br><h3>Preferred qualifications:</h3><ul><li>Testing</li></ul>"
            ),
        ],
        "projects/gweb-careers-proto/tenants/example/companies/google",
        None,
        company_name,
        "en-US",
        [[f"{city}, Israel", [f"{city}, Israel"], city, None, state, "IL"]],
        [None, overview],
        [2],
        [1780000000, 0],
        [1780000000, 0],
        [1780000000, 0],
        [None, ""],
        None,
        None,
        [None, f"Role based in <b>{city}, Israel</b>."],
        [None, "<ul><li>Python</li></ul>"],
        2,
    ]


def _build_results_html(
    *,
    jobs: list[list[object]],
    total_records: int,
    search_query: str = "q=&location=Israel&hl=en",
) -> str:
    data_payload = json.dumps(
        [jobs, None, total_records, len(jobs)],
        ensure_ascii=False,
    )
    detail_links = "".join(
        (
            '<a class="WpHeLc" href="jobs/results/'
            f'{job[0]}-{job[1].lower().replace(" ", "-")}?{html.escape(search_query)}'
            '"></a>'
        )
        for job in jobs
    )
    return (
        "<html><head><base "
        'href="https://www.google.com/about/careers/applications/">'
        "</head><body>"
        f"{detail_links}"
        "<script class=\"ds:1\">"
        f"AF_initDataCallback({{key: 'ds:1', hash: '2', data:{data_payload}, sideChannel: {{}}}});"
        "</script>"
        "</body></html>"
    )


class _FakeResponse:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        if "page=2" in url:
            return _FakeResponse(
                text=_build_results_html(
                    jobs=[
                        _build_job(
                            job_id="30021",
                            title="Staff Software Engineer",
                            city="Jerusalem",
                            state="Jerusalem District",
                        )
                    ],
                    total_records=21,
                )
            )

        page_one_jobs = [
            _build_job(
                job_id=f"300{index:02d}",
                title=f"Software Engineer {index}",
                city="Tel Aviv",
                state="Tel Aviv District",
            )
            for index in range(1, 21)
        ]
        return _FakeResponse(
            text=_build_results_html(
                jobs=page_one_jobs,
                total_records=21,
            )
        )


class GoogleCareersTests(unittest.TestCase):
    def test_scrape_reads_google_careers_results_pages(self) -> None:
        scraper = GoogleCareers()
        fake_session = _FakeSession()
        scraper.session = fake_session

        result = scraper.scrape(
            ScraperInput(
                site_type=[Site.GOOGLE_CAREERS],
                google_careers_url=DEFAULT_GOOGLE_CAREERS_URL,
                results_wanted=21,
                description_limit=None,
                description_format=DescriptionFormat.MARKDOWN,
            )
        )

        self.assertEqual(len(result.jobs), 21)
        self.assertEqual(result.jobs[0].company_name, "Google")
        self.assertEqual(
            result.jobs[0].job_url,
            (
                "https://www.google.com/about/careers/applications/jobs/results/"
                "30001-software-engineer-1?q=&location=Israel&hl=en"
            ),
        )
        self.assertEqual(
            result.jobs[0].apply_url,
            "https://www.google.com/about/careers/applications/signin?jobId=30001",
        )
        self.assertEqual(
            result.jobs[0].location.display_location(),
            "Tel Aviv, Tel Aviv District, Israel",
        )
        self.assertIn("## Responsibilities", result.jobs[0].description or "")
        self.assertIn("Ship reliable services.", result.jobs[0].description or "")
        self.assertEqual(
            result.jobs[-1].location.display_location(),
            "Jerusalem, Jerusalem District, Israel",
        )
        self.assertTrue(any("page=1" in url for url in fake_session.requested_urls))
        self.assertTrue(any("page=2" in url for url in fake_session.requested_urls))

    def test_resolve_search_url_can_override_q_and_location(self) -> None:
        scraper = GoogleCareers()
        resolved_url = scraper._resolve_search_url(
            ScraperInput(
                site_type=[Site.GOOGLE_CAREERS],
                google_careers_url=DEFAULT_GOOGLE_CAREERS_URL,
                search_term="site reliability engineer",
                location="Haifa",
            )
        )

        self.assertIn("q=site+reliability+engineer", resolved_url)
        self.assertIn("location=Haifa", resolved_url)
        self.assertIn("hl=en", resolved_url)


if __name__ == "__main__":
    unittest.main()
