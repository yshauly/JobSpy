from __future__ import annotations

import unittest

from jobspy.model import DescriptionFormat, JobType, ScraperInput, Site
from jobspy.workday import Workday

MARVELL_ISRAEL_BASE_URL = (
    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
    "?Country=084562884af243748dad7c84c304d89a"
)


class _FakeResponse:
    def __init__(
        self,
        *,
        text: str | None = None,
        json_data=None,
        status_code: int = 200,
    ) -> None:
        self.text = text or ""
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self) -> None:
        self.get_requests: list[str] = []
        self.post_requests: list[tuple[str, dict[str, object]]] = []

    def get(self, url, timeout=None, verify=None):
        self.get_requests.append(url)
        if url == MARVELL_ISRAEL_BASE_URL:
            return _FakeResponse(
                text=(
                    "<!DOCTYPE html><html><head>"
                    '<link rel="canonical" href="https://marvell.wd1.myworkdayjobs.com/MarvellCareers" />'
                    '<meta property="og:title" content="Marvell Careers" />'
                    '<meta property="og:description" content="Join our talent community to hear about company news." />'
                    '<meta property="og:image" content="https://marvell.wd1.myworkdayjobs.com/MarvellCareers/assets/logo" />'
                    "<script>"
                    'window.workday = window.workday || { tenant: "marvell", siteId: "MarvellCareers", requestLocale: "en-US" };'
                    "</script>"
                    "</head><body></body></html>"
                )
            )

        if url.endswith(
            "/wday/cxs/marvell/MarvellCareers/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"
        ):
            return _FakeResponse(
                json_data={
                    "jobPostingInfo": {
                        "id": "df48ecc88eb410018541ecb42e5b0000",
                        "title": "Principal Hardware Board Design Engineer",
                        "jobDescription": "<p><b>About Marvell</b></p><p>Build boards</p>",
                        "location": "Yokneam",
                        "postedOn": "Posted 11 Days Ago",
                        "startDate": "2026-04-15",
                        "timeType": "Full time",
                        "jobReqId": "2503821",
                        "country": {
                            "descriptor": "Israel",
                            "id": "084562884af243748dad7c84c304d89a",
                        },
                        "externalUrl": (
                            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                            "/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"
                        ),
                    },
                    "hiringOrganization": {"name": "40 Marvell Israel (MISL) Ltd"},
                }
            )

        if url.endswith(
            "/wday/cxs/marvell/MarvellCareers/job/Yokneam/Senior-Engineer--Physical-Design_2503613"
        ):
            return _FakeResponse(
                json_data={
                    "jobPostingInfo": {
                        "id": "188818496ed010016c3a3206f9520000",
                        "title": "Senior Staff Engineer, Physical Design",
                        "jobDescription": (
                            "<p><b>Your Team, Your Impact</b></p>"
                            "<p>Physical design work</p>"
                        ),
                        "location": "Yokneam",
                        "additionalLocations": ["Petah-Tikva"],
                        "postedOn": "Posted 30+ Days Ago",
                        "startDate": "2026-02-12",
                        "timeType": "Full time",
                        "jobReqId": "2503613",
                        "country": {
                            "descriptor": "Israel",
                            "id": "084562884af243748dad7c84c304d89a",
                        },
                        "externalUrl": (
                            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                            "/job/Yokneam/Senior-Engineer--Physical-Design_2503613"
                        ),
                    },
                    "hiringOrganization": {"name": ""},
                }
            )

        raise AssertionError(f"Unexpected GET request: {url}")

    def post(self, url, json=None, timeout=None, verify=None):
        self.post_requests.append((url, dict(json or {})))
        if url.endswith("/wday/cxs/marvell/MarvellCareers/jobs"):
            return _FakeResponse(
                json_data={
                    "total": 2,
                    "jobPostings": [
                        {
                            "title": "Principal Hardware Board Design Engineer",
                            "externalPath": "/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821",
                            "locationsText": "Yokneam",
                            "postedOn": "Posted 11 Days Ago",
                            "bulletFields": ["2503821"],
                        },
                        {
                            "title": "Senior Staff Engineer, Physical Design",
                            "externalPath": "/job/Yokneam/Senior-Engineer--Physical-Design_2503613",
                            "locationsText": "2 Locations",
                            "postedOn": "Posted 30+ Days Ago",
                            "bulletFields": ["2503613"],
                        },
                    ],
                }
            )

        raise AssertionError(f"Unexpected POST request: {url}")


class WorkdayTests(unittest.TestCase):
    def test_scrape_bootstraps_workday_and_hydrates_marvell_israel_jobs(self) -> None:
        scraper = Workday()
        fake_session = _FakeSession()
        scraper.session = fake_session

        result = scraper.scrape(
            ScraperInput(
                site_type=[Site.WORKDAY],
                workday_company_url=MARVELL_ISRAEL_BASE_URL,
                results_wanted=2,
                description_limit=None,
                description_format=DescriptionFormat.MARKDOWN,
            )
        )

        self.assertEqual(len(result.jobs), 2)
        self.assertEqual(result.jobs[0].company_name, "Marvell")
        self.assertEqual(
            result.jobs[0].company_url,
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers",
        )
        self.assertEqual(
            result.jobs[0].company_logo,
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers/assets/logo",
        )
        self.assertIn("Join our talent community", result.jobs[0].company_description)
        self.assertEqual(
            result.jobs[0].job_url,
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821",
        )
        self.assertEqual(result.jobs[0].location.display_location(), "Yokneam, Israel")
        self.assertEqual(result.jobs[1].location.display_location(), "Yokneam / Petah-Tikva, Israel")
        self.assertEqual(result.jobs[0].job_type, [JobType.FULL_TIME])
        self.assertFalse(result.jobs[0].is_remote)
        self.assertIn("About Marvell", result.jobs[0].description or "")
        self.assertEqual(len(fake_session.post_requests), 1)
        self.assertEqual(
            fake_session.post_requests[0][1]["appliedFacets"],
            {"Country": ["084562884af243748dad7c84c304d89a"]},
        )
        self.assertEqual(fake_session.post_requests[0][1]["offset"], 0)
        self.assertEqual(fake_session.post_requests[0][1]["limit"], 2)
        self.assertEqual(len(fake_session.get_requests), 3)


if __name__ == "__main__":
    unittest.main()
