from __future__ import annotations

import json
import unittest

from jobspy.apple import Apple, DEFAULT_APPLE_SEARCH_URL
from jobspy.model import DescriptionFormat, ScraperInput, Site


def _build_hydration_html(payload: dict[str, object]) -> str:
    encoded_payload = json.dumps(payload, ensure_ascii=False)
    encoded_string = json.dumps(encoded_payload, ensure_ascii=False)
    return (
        "<html><head>"
        f"<script>window.__staticRouterHydrationData = JSON.parse({encoded_string});</script>"
        "</head><body></body></html>"
    )


def _build_search_result(
    *,
    req_id: str,
    title: str,
    slug: str,
    summary: str,
    city: str,
    team_name: str,
    team_code: str,
    post_date: str,
    iso_posted_at: str,
    home_office: bool = False,
) -> dict[str, object]:
    return {
        "id": req_id,
        "jobSummary": summary,
        "locations": [
            {
                "name": city,
                "city": city,
                "stateProvince": "",
                "countryName": "Israel",
            }
        ],
        "positionId": req_id.split("-", 1)[0],
        "postingDate": post_date,
        "postingTitle": title,
        "postDateInGMT": iso_posted_at,
        "transformedPostingTitle": slug,
        "reqId": req_id,
        "standardWeeklyHours": 42,
        "team": {
            "teamName": team_name,
            "teamCode": team_code,
        },
        "homeOffice": home_office,
    }


class _FakeResponse:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    def get(self, url, params=None, timeout=None, verify=None):
        self.requested_urls.append(url)
        if "page=2" in url:
            return _FakeResponse(
                text=_build_hydration_html(
                    {
                        "loaderData": {
                            "root": {"locale": "en-il"},
                            "search": {
                                "totalRecords": 21,
                                "page": 2,
                                "searchResults": [
                                    _build_search_result(
                                        req_id="2002-IL",
                                        title="ML Engineer",
                                        slug="ml-engineer",
                                        summary="Second summary",
                                        city="Jerusalem",
                                        team_name="Machine Learning and AI",
                                        team_code="MLAI",
                                        post_date="02 Jun 2026",
                                        iso_posted_at="2026-06-02T10:00:00.000Z",
                                        home_office=True,
                                    )
                                ],
                            },
                        },
                        "actionData": None,
                        "errors": None,
                    }
                )
            )
        if "/details/" in url:
            return _FakeResponse(
                text=_build_hydration_html(
                    {
                        "loaderData": {
                            "root": {"locale": "en-il"},
                            "jobDetails": {
                                "jobsData": {
                                    "jobNumber": "2001-IL",
                                    "postingTitle": "Software Engineer",
                                    "jobSummary": "First summary",
                                    "description": "Build reliable services.",
                                    "responsibilities": "Own delivery\nImprove tests",
                                    "minimumQualifications": "Python\nAPIs",
                                    "preferredQualifications": "Playwright",
                                    "postDateInGMT": "2026-06-03T08:35:34.882+00:00",
                                    "postingDateMeta": "2026-06-03",
                                    "locations": [
                                        {
                                            "name": "Herzliya",
                                            "city": "Herzliya",
                                            "stateProvince": "Tel Aviv District",
                                            "countryName": "Israel",
                                            "active": True,
                                        }
                                    ],
                                    "teamNames": ["Software and Services"],
                                    "homeOffice": False,
                                }
                            },
                        },
                        "actionData": None,
                        "errors": None,
                    }
                )
            )
        return _FakeResponse(
            text=_build_hydration_html(
                {
                    "loaderData": {
                        "root": {"locale": "en-il"},
                        "search": {
                            "totalRecords": 21,
                            "page": 1,
                            "searchResults": [
                                _build_search_result(
                                    req_id="2001-IL",
                                    title="Software Engineer",
                                    slug="software-engineer",
                                    summary="First summary",
                                    city="Herzliya",
                                    team_name="Software and Services",
                                    team_code="SFTWR",
                                    post_date="03 Jun 2026",
                                    iso_posted_at="2026-06-03T08:35:34.882Z",
                                )
                            ],
                        },
                    },
                    "actionData": None,
                    "errors": None,
                }
            )
        )


class AppleTests(unittest.TestCase):
    def test_scrape_reads_search_hydration_and_hydrates_one_detail_page(self) -> None:
        scraper = Apple()
        fake_session = _FakeSession()
        scraper.session = fake_session

        result = scraper.scrape(
            ScraperInput(
                site_type=[Site.APPLE],
                apple_search_url=DEFAULT_APPLE_SEARCH_URL,
                results_wanted=2,
                description_limit=1,
                description_format=DescriptionFormat.MARKDOWN,
            )
        )

        self.assertEqual(len(result.jobs), 2)
        self.assertEqual(result.jobs[0].company_name, "Apple")
        self.assertEqual(
            result.jobs[0].job_url,
            "https://jobs.apple.com/en-il/details/2001-IL/software-engineer?team=SFTWR",
        )
        self.assertEqual(
            result.jobs[0].location.display_location(),
            "Herzliya, Tel Aviv District, Israel",
        )
        self.assertIn("## Description", result.jobs[0].description or "")
        self.assertIn("Build reliable services.", result.jobs[0].description or "")
        self.assertEqual(
            result.jobs[1].description,
            "## Summary\nSecond summary",
        )
        self.assertTrue(result.jobs[1].is_remote)
        self.assertEqual(
            result.jobs[1].location.display_location(),
            "Jerusalem, Israel",
        )
        self.assertTrue(any("page=1" in url for url in fake_session.requested_urls))
        self.assertTrue(any("page=2" in url for url in fake_session.requested_urls))
        self.assertEqual(
            len([url for url in fake_session.requested_urls if "/details/" in url]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
