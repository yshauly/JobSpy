from __future__ import annotations

import unittest

from jobspy.json_feed import JsonFeed
from jobspy import jobs_table
from jobspy.model import Country, DescriptionFormat, ScraperInput, Site


class FakeResponse:
    def __init__(self, payload=None, *, text="", url=None):
        self.payload = payload
        self.text = text
        self.url = url

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class JsonFeedTests(unittest.TestCase):
    def test_scrape_maps_configured_feed_rows(self) -> None:
        payload = [
            {
                "jobId": 19702,
                "jobTitle": "R&D Engineer",
                "openDate": "2026-06-15T07:16:00",
                "description": "Build systems&lt;div&gt;Ship carefully&lt;/div&gt;",
                "requirements": "Python",
                "employerName": "Engineering",
                "employmentType": "Full Time",
                "status": 1,
            },
            {
                "jobId": 19703,
                "jobTitle": "Inactive Engineer",
                "status": 0,
            },
        ]
        config = {
            "company_name": "Elbit Systems Israel",
            "company_url": "https://elbitsystemscareer.com/",
            "field_paths": {
                "id": "jobId",
                "title": "jobTitle",
                "date_posted": "openDate",
                "job_function": "employerName",
                "listing_type": "employmentType",
            },
            "templates": {
                "job_url": "https://elbitsystemscareer.com/job/?jid={jobId}",
                "apply_url": "https://elbitsystemscareer.com/job/?jid={jobId}",
            },
            "description_sections": [
                {"title": "Description", "path": "description"},
                {"title": "Requirements", "path": "requirements"},
            ],
            "constants": {"country": "Israel"},
            "filters": [{"path": "status", "equals": 1}],
        }
        scraper = JsonFeed()
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(payload)

        scraper.session.request = fake_request
        response = scraper.scrape(
            ScraperInput(
                site_type=[Site.JSON_FEED],
                country=Country.ISRAEL,
                location="Israel",
                json_feed_url="https://elbitsystemscareer.com/cron/jobs.json",
                json_feed_config=config,
                description_format=DescriptionFormat.MARKDOWN,
                results_wanted=0,
            )
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(len(response.jobs), 1)

        job = response.jobs[0]
        self.assertEqual(job.id, "19702")
        self.assertEqual(job.title, "R&D Engineer")
        self.assertEqual(
            job.job_url,
            "https://elbitsystemscareer.com/job/?jid=19702",
        )
        self.assertEqual(job.company_name, "Elbit Systems Israel")
        self.assertEqual(job.location.country, "Israel")
        self.assertEqual(job.date_posted.isoformat(), "2026-06-15")
        self.assertIn("### Description", job.description)
        self.assertIn("Ship carefully", job.description)
        self.assertEqual(job.job_function, "Engineering")
        self.assertEqual(job.listing_type, "Full Time")

    def test_scrape_reads_embedded_html_json_script(self) -> None:
        html = """
        <html>
          <script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"positions":[
              {"uid":"abc123","name":"Backend Engineer","location":{"name":"Tel Aviv"}}
            ]}}}
          </script>
        </html>
        """
        config = {
            "html_json_script_id": "__NEXT_DATA__",
            "rows_path": "props.pageProps.positions",
            "company_name": "monday.com",
            "field_paths": {
                "id": "uid",
                "title": "name",
                "city": "location.name",
            },
            "templates": {
                "job_url": "https://monday.com/careers/{uid}",
                "apply_url": "https://monday.com/careers/{uid}",
            },
            "constants": {"country": "Israel"},
            "location_filter_paths": ["location.name"],
        }
        scraper = JsonFeed()

        def fake_request(method, url, **kwargs):
            return FakeResponse(text=html, url=url)

        scraper.session.request = fake_request
        response = scraper.scrape(
            ScraperInput(
                site_type=[Site.JSON_FEED],
                country=Country.ISRAEL,
                location="Tel Aviv",
                json_feed_url="https://monday.com/careers/?location=telaviv",
                json_feed_config=config,
                description_format=DescriptionFormat.MARKDOWN,
                results_wanted=0,
            )
        )

        self.assertEqual(len(response.jobs), 1)
        self.assertEqual(response.jobs[0].id, "abc123")
        self.assertEqual(response.jobs[0].title, "Backend Engineer")
        self.assertEqual(response.jobs[0].job_url, "https://monday.com/careers/abc123")
        self.assertEqual(response.jobs[0].location.city, "Tel Aviv")

    def test_scrape_hydrates_missing_description_from_detail_page(self) -> None:
        payload = [
            {
                "id": "abc123",
                "title": "Backend Engineer",
                "url": "https://example.com/jobs/abc123",
            },
            {
                "id": "def456",
                "title": "Frontend Engineer",
                "url": "https://example.com/jobs/def456",
            },
        ]
        detail_html = """
        <html>
          <script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"positionData":{
              "positionDescription":"<p>Hello <strong>world</strong></p>",
              "positionResponsibilities":"<ul><li>Ship carefully</li></ul>"
            }}}}
          </script>
        </html>
        """
        config = {
            "company_name": "Example",
            "field_paths": {
                "id": "id",
                "title": "title",
                "job_url": "url",
            },
            "detail_fetch": {
                "html_json_script_id": "__NEXT_DATA__",
                "payload_path": "props.pageProps.positionData",
                "description_sections": [
                    {"title": "Description", "path": "positionDescription"},
                    {"title": "Responsibilities", "path": "positionResponsibilities"},
                ],
            },
        }
        scraper = JsonFeed()
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            if url == "https://example.com/jobs":
                return FakeResponse(payload)
            return FakeResponse(text=detail_html, url=url)

        scraper.session.request = fake_request
        response = scraper.scrape(
            ScraperInput(
                site_type=[Site.JSON_FEED],
                country=Country.ISRAEL,
                json_feed_url="https://example.com/jobs",
                json_feed_config=config,
                description_format=DescriptionFormat.MARKDOWN,
                description_limit=1,
                results_wanted=0,
            )
        )

        self.assertEqual(len(response.jobs), 2)
        self.assertIn("### Description", response.jobs[0].description or "")
        self.assertIn("Hello **world**", response.jobs[0].description or "")
        self.assertIn("Ship carefully", response.jobs[0].description or "")
        self.assertIsNone(response.jobs[1].description)
        self.assertEqual(
            [call[1] for call in calls],
            ["https://example.com/jobs", "https://example.com/jobs/abc123"],
        )

    def test_scrape_maps_html_row_selector_rows(self) -> None:
        html = """
        <section class="jobs">
          <a class="job-card" href="/jobs/one">
            <span class="title">Platform Engineer</span>
            <span class="meta">Permanent | Israel</span>
          </a>
          <a class="job-card" href="/jobs/two">
            <span class="title">US Sales</span>
            <span class="meta">Permanent | US</span>
          </a>
        </section>
        """
        config = {
            "html_row_selector": "a.job-card",
            "html_fields": {
                "title": {"selector": ".title"},
                "job_url": {"selector": ".", "attr": "href", "urljoin": True},
                "listing_type": {"selector": ".meta"},
                "city": {"selector": ".meta"},
            },
            "company_name": "HiBob",
            "field_paths": {
                "title": "title",
                "job_url": "job_url",
                "apply_url": "job_url",
                "city": "city",
                "listing_type": "listing_type",
            },
            "constants": {"country": "Israel"},
            "location_filter_paths": ["listing_type"],
        }
        scraper = JsonFeed()

        def fake_request(method, url, **kwargs):
            return FakeResponse(text=html, url=url)

        scraper.session.request = fake_request
        response = scraper.scrape(
            ScraperInput(
                site_type=[Site.JSON_FEED],
                country=Country.ISRAEL,
                location="Israel",
                json_feed_url="https://www.hibob.com/careers/",
                json_feed_config=config,
                description_format=DescriptionFormat.MARKDOWN,
                results_wanted=0,
            )
        )

        self.assertEqual(len(response.jobs), 1)
        self.assertEqual(response.jobs[0].title, "Platform Engineer")
        self.assertEqual(response.jobs[0].job_url, "https://www.hibob.com/jobs/one")
        self.assertEqual(response.jobs[0].listing_type, "Permanent | Israel")

    def test_scrape_maps_hibob_api_rows_with_descriptions(self) -> None:
        payload = {
            "jobAdDetails": [
                {
                    "id": "3af670f7-e74e-4e58-8179-04c677acdde3",
                    "title": "Cloud Security Engineer",
                    "site": "IL",
                    "country": "Israel",
                    "description": "<p>Build secure systems.</p>",
                    "employmentType": "Permanent",
                    "department": "Business Technologies",
                },
                {
                    "id": "us-only",
                    "title": "US Sales",
                    "site": "US",
                    "country": "United States",
                    "description": "<p>Sell products.</p>",
                },
            ]
        }
        scraper = JsonFeed()
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(payload)

        scraper.session.request = fake_request
        response = scraper.scrape(
            ScraperInput(
                site_type=[Site.JSON_FEED],
                country=Country.ISRAEL,
                location="Israel",
                json_feed_url=jobs_table.HIBOB_JOBS_API_URL,
                json_feed_config=jobs_table.HIBOB_JSON_FEED_CONFIG,
                description_format=DescriptionFormat.MARKDOWN,
                results_wanted=0,
            )
        )

        self.assertEqual(len(response.jobs), 1)
        job = response.jobs[0]
        self.assertEqual(job.id, "3af670f7-e74e-4e58-8179-04c677acdde3")
        self.assertEqual(job.title, "Cloud Security Engineer")
        self.assertEqual(job.location.city, "IL")
        self.assertEqual(job.location.country, "Israel")
        self.assertEqual(job.listing_type, "Permanent")
        self.assertEqual(job.job_function, "Business Technologies")
        self.assertIn("Build secure systems.", job.description or "")
        self.assertEqual(
            calls[0][2]["headers"]["companyIdentifier"],
            "hibob-fa0ad69d0cb34a",
        )

    def test_scrape_maps_nice_greenhouse_feed_rows(self) -> None:
        payload = {
            "jobs": [
                {
                    "id": 4845780101,
                    "title": "Software Engineer",
                    "absolute_url": (
                        "https://boards.eu.greenhouse.io/nice/jobs/4845780101"
                        "?gh_jid=4845780101"
                    ),
                    "location": {"name": "Israel - Raanana"},
                    "metadata": [
                        {"name": "Job Type", "value": "Regular"},
                        {"name": "Hiring Manager", "value": {"name": "Manager"}},
                        {"name": "Category", "value": "R&D"},
                    ],
                    "content": "&lt;p&gt;Build NICE products&lt;/p&gt;",
                },
                {
                    "id": 4845780102,
                    "title": "Account Executive",
                    "absolute_url": (
                        "https://boards.eu.greenhouse.io/nice/jobs/4845780102"
                        "?gh_jid=4845780102"
                    ),
                    "location": {"name": "USA - Remote"},
                    "metadata": [
                        {"name": "Job Type", "value": "Regular"},
                        {"name": "Hiring Manager", "value": {"name": "Manager"}},
                        {"name": "Category", "value": "SALES"},
                    ],
                    "content": "&lt;p&gt;Sell NICE products&lt;/p&gt;",
                },
            ]
        }
        scraper = JsonFeed()
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(payload)

        scraper.session.request = fake_request
        response = scraper.scrape(
            ScraperInput(
                site_type=[Site.JSON_FEED],
                country=Country.ISRAEL,
                location="Israel",
                json_feed_url=jobs_table.NICE_GREENHOUSE_JOBS_URL,
                json_feed_config=jobs_table.NICE_JSON_FEED_CONFIG,
                description_format=DescriptionFormat.MARKDOWN,
                results_wanted=0,
            )
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(response.jobs), 1)

        job = response.jobs[0]
        self.assertEqual(job.id, "4845780101")
        self.assertEqual(job.title, "Software Engineer")
        self.assertEqual(job.company_name, "NICE")
        self.assertEqual(job.job_url, payload["jobs"][0]["absolute_url"])
        self.assertEqual(job.location.city, "Israel - Raanana")
        self.assertEqual(job.location.country, "Israel")
        self.assertEqual(job.listing_type, "Regular")
        self.assertEqual(job.job_function, "R&D")
        self.assertIn("Build NICE products", job.description)


if __name__ == "__main__":
    unittest.main()
