from __future__ import annotations

import unittest
from unittest.mock import call, patch

from bs4 import BeautifulSoup

from jobspy.linkedin import LinkedIn
from jobspy.model import (
    Country,
    DescriptionFormat,
    JobPost,
    LinkedInScrapeMode,
    ScraperInput,
    Site,
)


class _FakeResponse:
    def __init__(self, text: str, *, status_code: int = 200, url: str = "https://www.linkedin.com/jobs/search") -> None:
        self.text = text
        self.status_code = status_code
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("Unexpected LinkedIn session.get call")
        return self._responses.pop(0)


class LinkedInProgressLoggingTests(unittest.TestCase):
    def test_until_last_page_prefers_authenticated_search_when_auth_cookies_exist(self) -> None:
        authenticated_page_html = """
        <section>
          <div class="job-card-container">
            <a class="job-card-list__title" href="https://www.linkedin.com/jobs/view/1001">Job 1001</a>
            <a href="https://www.linkedin.com/company/acme">Acme</a>
            <span class="job-card-container__metadata-item">Tel Aviv, Israel</span>
            <time datetime="2026-06-16"></time>
          </div>
        </section>
        """
        fake_session = _FakeSession(
            [
                _FakeResponse(authenticated_page_html),
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )
        scraper = LinkedIn(
            auth_cookies={
                "li_at": "session-cookie",
                "JSESSIONID": '"ajax:test"',
            }
        )
        scraper.session = fake_session

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            location="Israel",
            linkedin_geo_id=101620260,
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.DEFAULT,
            hours_old=1,
            results_wanted=1,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.random.uniform", return_value=0):
                with patch("jobspy.linkedin.time.sleep"):
                    scraper.scrape(scraper_input)

        self.assertGreaterEqual(len(fake_session.calls), 1)
        self.assertEqual(
            fake_session.calls[0]["url"],
            "https://www.linkedin.com/jobs/search/",
        )

    def test_until_last_page_falls_back_to_guest_when_authenticated_search_is_guest_markup(self) -> None:
        guest_markup_html = """
        <html>
          <code id="pageKey"><!--"d_jobs_guest_search"--></code>
          <div class="base-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/9999"></a>
          </div>
        </html>
        """
        guest_results_html = """
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1001"></a>
        </div>
        """
        fake_session = _FakeSession(
            [
                _FakeResponse(guest_markup_html),
                _FakeResponse(
                    guest_results_html,
                    url="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                ),
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )
        scraper = LinkedIn(
            auth_cookies={
                "li_at": "session-cookie",
                "JSESSIONID": '"ajax:test"',
            }
        )
        scraper.session = fake_session

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            location="Israel",
            linkedin_geo_id=101620260,
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.DEFAULT,
            hours_old=1,
            results_wanted=1,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.random.uniform", return_value=0):
                with patch("jobspy.linkedin.time.sleep"):
                    scraper.scrape(scraper_input)

        self.assertEqual(
            fake_session.calls[0]["url"],
            "https://www.linkedin.com/jobs/search/",
        )
        self.assertEqual(
            fake_session.calls[1]["url"],
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
        )

    def test_until_last_page_sends_geo_id_with_location(self) -> None:
        first_page_html = """
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1001"></a>
        </div>
        """
        fake_session = _FakeSession(
            [
                _FakeResponse(first_page_html),
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )
        scraper = LinkedIn(auth_cookies={})
        scraper.session = fake_session

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            location="Israel",
            linkedin_geo_id=101620260,
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
            num_of_min=60,
            results_wanted=1000,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.random.uniform", return_value=0):
                with patch("jobspy.linkedin.time.sleep"):
                    scraper.scrape(scraper_input)

        self.assertGreaterEqual(len(fake_session.calls), 1)
        first_call_params = fake_session.calls[0]["params"]
        self.assertEqual(first_call_params["location"], "Israel")
        self.assertEqual(first_call_params["geoId"], 101620260)
        first_call_param_names = list(first_call_params)
        self.assertLess(
            first_call_param_names.index("geoId"),
            first_call_param_names.index("pageNum"),
        )
        self.assertLess(
            first_call_param_names.index("f_TPR"),
            first_call_param_names.index("pageNum"),
        )

    def test_blank_search_term_sends_empty_keywords_param(self) -> None:
        fake_session = _FakeSession(
            [
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )
        scraper = LinkedIn(auth_cookies={})
        scraper.session = fake_session

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            search_term=None,
            location="Israel",
            linkedin_geo_id=101620260,
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
            num_of_min=60,
            results_wanted=1000,
        )

        scraper.scrape(scraper_input)

        first_call_params = fake_session.calls[0]["params"]
        self.assertIn("keywords", first_call_params)
        self.assertEqual(first_call_params["keywords"], "")

    def test_until_last_page_logs_page_progress(self) -> None:
        first_page_html = """
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1001"></a>
        </div>
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1002"></a>
        </div>
        """
        scraper = LinkedIn(auth_cookies={})
        scraper.session = _FakeSession(
            [
                _FakeResponse(first_page_html),
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            location="Israel",
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
            num_of_min=60,
            results_wanted=1000,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.log.info") as info_mock:
                with patch("jobspy.linkedin.random.uniform", return_value=3.5):
                    with patch("jobspy.linkedin.time.sleep"):
                        with patch(
                            "jobspy.linkedin.time.perf_counter",
                            side_effect=[10.0, 11.25, 12.0],
                        ):
                            response = scraper.scrape(scraper_input)

        self.assertEqual(len(response.jobs), 2)
        self.assertIn(
            call(
                "LinkedIn page %s complete: start=%s cards=%s new=%s duplicates=%s total=%s elapsed=%.2fs",
                1,
                0,
                2,
                2,
                0,
                2,
                1.25,
            ),
            info_mock.call_args_list,
        )
        self.assertIn(
            call(
                "LinkedIn waiting %.2fs before next page (next_start=%s)",
                3.5,
                2,
            ),
            info_mock.call_args_list,
        )
        self.assertIn(
            call(
                "LinkedIn page %s returned 0 cards; stopping with total_jobs=%s",
                2,
                2,
            ),
            info_mock.call_args_list,
        )

    def test_until_last_page_uses_configured_page_delay_range(self) -> None:
        first_page_html = """
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1001"></a>
        </div>
        """
        scraper = LinkedIn(auth_cookies={})
        scraper.session = _FakeSession(
            [
                _FakeResponse(first_page_html),
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            location="Israel",
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
            linkedin_page_delay_min=0.5,
            linkedin_page_delay_max=1.0,
            num_of_min=60,
            results_wanted=1000,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.random.uniform", return_value=0.75) as uniform_mock:
                with patch("jobspy.linkedin.time.sleep") as sleep_mock:
                    scraper.scrape(scraper_input)

        uniform_mock.assert_called_once_with(0.5, 1.0)
        sleep_mock.assert_called_once_with(0.75)

    def test_until_last_page_retries_transient_429_response(self) -> None:
        first_page_html = """
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1001"></a>
        </div>
        """
        scraper = LinkedIn(auth_cookies={})
        fake_session = _FakeSession(
            [
                _FakeResponse("Too many requests", status_code=429),
                _FakeResponse(first_page_html),
                _FakeResponse("<html><body>No jobs</body></html>"),
            ]
        )
        scraper.session = fake_session

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            location="Israel",
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
            num_of_min=60,
            results_wanted=1000,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.random.uniform", return_value=0.5):
                with patch("jobspy.linkedin.time.sleep") as sleep_mock:
                    with patch("jobspy.linkedin.log.warning") as warning_mock:
                        response = scraper.scrape(scraper_input)

        self.assertEqual(len(response.jobs), 1)
        self.assertEqual(len(fake_session.calls), 3)
        self.assertEqual(sleep_mock.call_args_list[0], call(1.0))
        warning_mock.assert_called_once_with(
            "LinkedIn page request retry scheduled: start=%s attempt=%s/%s reason=%s sleep=%.2fs",
            0,
            2,
            scraper.search_page_retry_attempts,
            "status 429",
            1.0,
        )

    def test_until_last_page_stops_before_guest_start_limit(self) -> None:
        first_page_html = "\n".join(
            [
                (
                    '<div class="base-search-card">'
                    f'<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/{1000 + index}"></a>'
                    "</div>"
                )
                for index in range(1000)
            ]
        )
        scraper = LinkedIn(auth_cookies={})
        fake_session = _FakeSession([_FakeResponse(first_page_html)])
        scraper.session = fake_session

        def fake_process_job(job_card, job_id, full_descr, apply_url=None):
            return JobPost(
                id=f"li-{job_id}",
                title=f"Job {job_id}",
                company_name="Acme",
                job_url=apply_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                location=None,
            )

        scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.INDIA,
            location="India",
            linkedin_geo_id=102713980,
            description_format=DescriptionFormat.PLAIN,
            linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
            num_of_min=60,
            results_wanted=1000,
        )

        with patch.object(scraper, "_process_job", side_effect=fake_process_job):
            with patch("jobspy.linkedin.log.info") as info_mock:
                response = scraper.scrape(scraper_input)

        self.assertEqual(len(response.jobs), 1000)
        self.assertEqual(len(fake_session.calls), 1)
        self.assertIn(
            call(
                "LinkedIn reached guest pagination limit at next_start=%s; stopping with total_jobs=%s",
                1000,
                1000,
            ),
            info_mock.call_args_list,
        )


class LinkedInAuthAndApplyUrlTests(unittest.TestCase):
    def test_init_applies_auth_cookies_to_session(self) -> None:
        scraper = LinkedIn(
            auth_cookies={
                "li_at": "session-cookie",
                "JSESSIONID": '"ajax:test"',
            }
        )

        self.assertEqual(
            scraper.auth_cookies,
            {
                "li_at": "session-cookie",
                "JSESSIONID": '"ajax:test"',
            },
        )
        self.assertFalse(scraper.session.clear_cookies)
        self.assertEqual(scraper.session.cookies.get("li_at"), "session-cookie")
        self.assertEqual(scraper.session.cookies.get("JSESSIONID"), '"ajax:test"')
        self.assertEqual(scraper.session.headers.get("csrf-token"), "ajax:test")

    def test_process_job_persists_apply_urls_from_job_details(self) -> None:
        scraper = LinkedIn(auth_cookies={})
        scraper.scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.USA,
            description_format=DescriptionFormat.PLAIN,
            linkedin_fetch_description=True,
            results_wanted=1,
        )
        job_card = BeautifulSoup(
            """
            <div class="base-search-card">
              <span class="sr-only">Software Engineer</span>
              <h4 class="base-search-card__subtitle">
                <a href="https://www.linkedin.com/company/acme?trk=test">Acme</a>
              </h4>
              <div class="base-search-card__metadata">
                <span class="job-search-card__location">Tel Aviv, Israel</span>
                <time class="job-search-card__listdate" datetime="2026-05-27"></time>
              </div>
            </div>
            """,
            "html.parser",
        ).find("div")

        with patch.object(scraper, "_get_existing_job_details", return_value={}):
            with patch.object(
                scraper,
                "_get_job_details",
                return_value={
                    "job_url": "https://www.linkedin.com/jobs/view/1001",
                    "apply_url": "https://www.linkedin.com/jobs/view/1001/apply",
                    "job_url_direct": "https://company.example.com/jobs/1001/apply",
                    "description": "Role description",
                    "job_type": None,
                    "job_level": "Senior",
                    "company_industry": "Software",
                    "applications_count": 12,
                    "job_function": "Engineering",
                },
            ):
                job_post = scraper._process_job(
                    job_card,
                    "1001",
                    True,
                    apply_url="https://www.linkedin.com/jobs/view/1001",
                )

        self.assertIsNotNone(job_post)
        self.assertEqual(job_post.job_url, "https://www.linkedin.com/jobs/view/1001")
        self.assertEqual(
            job_post.apply_url,
            "https://www.linkedin.com/jobs/view/1001/apply",
        )
        self.assertEqual(
            job_post.job_url_direct,
            "https://company.example.com/jobs/1001/apply",
        )
        self.assertEqual(job_post.applications_count, 12)

    def test_process_job_parses_authenticated_search_card_fields(self) -> None:
        scraper = LinkedIn(auth_cookies={})
        scraper.scraper_input = ScraperInput(
            site_type=[Site.LINKEDIN],
            country=Country.ISRAEL,
            description_format=DescriptionFormat.PLAIN,
            linkedin_fetch_description=False,
            results_wanted=1,
        )
        job_card = BeautifulSoup(
            """
            <div class="job-card-container">
              <a class="job-card-list__title" href="https://www.linkedin.com/jobs/view/2001">Platform Engineer</a>
              <a class="hidden-nested-link" href="https://www.linkedin.com/company/acme/?trk=test">Acme</a>
              <span class="job-card-container__metadata-item">Tel Aviv, Israel</span>
              <time datetime="2026-06-16"></time>
            </div>
            """,
            "html.parser",
        ).find("div")

        job_post = scraper._process_job(
            job_card,
            "2001",
            False,
            apply_url="https://www.linkedin.com/jobs/view/2001",
        )

        self.assertIsNotNone(job_post)
        self.assertEqual(job_post.title, "Platform Engineer")
        self.assertEqual(job_post.company_name, "Acme")
        self.assertEqual(job_post.company_url, "https://www.linkedin.com/company/acme/")
        self.assertEqual(job_post.job_url, "https://www.linkedin.com/jobs/view/2001")
        self.assertEqual(job_post.location.city, "Tel Aviv")
        self.assertEqual(job_post.location.state, "Israel")
        self.assertEqual(job_post.date_posted.isoformat(), "2026-06-16")
