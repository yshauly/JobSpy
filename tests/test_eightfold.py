from __future__ import annotations

import unittest

from jobspy.eightfold import Eightfold
from jobspy.model import DescriptionFormat, Site, ScraperInput

AMDOCS_BASE_URL = (
    "https://jobs.amdocs.com/careers"
    "?start=0&location=Israel&pid=563431010318975"
    "&sort_by=match&filter_include_remote=1"
)


def _build_position(position_id: int) -> dict[str, object]:
    return {
        "id": position_id,
        "displayJobId": f"{position_id}",
        "name": f"Job {position_id}",
        "locations": ["Israel- RAANANA (Amdocs Site)"],
        "standardizedLocations": ["Ra'anana, Center District, IL"],
        "postedTs": 1776110819,
        "workLocationOption": "remote" if position_id == 1 else "hybrid",
        "positionUrl": f"/careers/job/{position_id}",
    }


class _FakeResponse:
    def __init__(
        self,
        *,
        text: str | None = None,
        json_data=None,
        status_code: int = 200,
        url: str | None = None,
    ):
        self.text = text or ""
        self._json_data = json_data
        self.status_code = status_code
        self.url = url or ""

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self) -> None:
        self.search_requests: list[dict[str, object]] = []
        self.detail_requests: list[dict[str, object]] = []

    def get(self, url, params=None, timeout=None, verify=None):
        if url.endswith("/api/pcsx/search"):
            recorded_params = dict(params or {})
            self.search_requests.append(recorded_params)
            start = int(recorded_params.get("start", 0))
            positions = []
            if start == 0:
                positions = [_build_position(position_id) for position_id in range(1, 11)]
            elif start == 10:
                positions = [_build_position(position_id) for position_id in range(11, 13)]
            return _FakeResponse(
                json_data={
                    "status": 200,
                    "data": {
                        "count": 12,
                        "positions": positions,
                    },
                }
            )

        if url.endswith("/api/pcsx/position_details"):
            recorded_params = dict(params or {})
            self.detail_requests.append(recorded_params)
            position_id = str(recorded_params["position_id"])
            return _FakeResponse(
                json_data={
                    "status": 200,
                    "data": {
                        "id": int(position_id),
                        "name": f"Job {position_id}",
                        "postedTs": 1776110819,
                        "workLocationOption": "remote",
                        "publicUrl": f"https://jobs.amdocs.com/careers/job/{position_id}",
                        "jobDescription": f"<p>Hello <strong>{position_id}</strong></p>",
                    },
                }
            )

        return _FakeResponse(
            text=(
                "<html><head><title>Careers at Amdocs</title></head><body>"
                "<code>{\"navbarData\":{\"desktop\":{\"nav_left_items\":["
                "{\"type\":\"BRANDING\",\"company_name\":\"Amdocs\","
                "\"product_homepage_url\":\"https://www.amdocs.com/careers/home\","
                "\"company_logo_url\":\"https://static.example.com/amdocs.png\"}"
                "]}}}</code>"
                "<code>{\"domain\":\"amdocs.com\",\"configs\":{\"pcsxConfig\":{"
                "\"branding\":{\"companyLogo\":\"https://static.example.com/amdocs-logo.png\"}"
                "}}}</code>"
                "</body></html>"
            )
        )


class EightfoldTests(unittest.TestCase):
    def test_scrape_bootstraps_context_paginates_and_hydrates_one_description(self) -> None:
        scraper = Eightfold()
        fake_session = _FakeSession()
        scraper.session = fake_session

        result = scraper.scrape(
            ScraperInput(
                site_type=[Site.EIGHTFOLD],
                eightfold_company_url=AMDOCS_BASE_URL,
                results_wanted=12,
                description_limit=1,
                description_format=DescriptionFormat.MARKDOWN,
            )
        )

        self.assertEqual(len(result.jobs), 12)
        self.assertEqual(result.jobs[0].company_name, "Amdocs")
        self.assertEqual(
            result.jobs[0].company_url,
            "https://www.amdocs.com/careers/home",
        )
        self.assertEqual(
            result.jobs[0].company_logo,
            "https://static.example.com/amdocs.png",
        )
        self.assertEqual(
            result.jobs[0].job_url,
            "https://jobs.amdocs.com/careers/job/1",
        )
        self.assertEqual(result.jobs[0].description, "Hello **1**")
        self.assertIsNone(result.jobs[1].description)
        self.assertTrue(result.jobs[0].is_remote)
        self.assertEqual(
            result.jobs[0].location.display_location(),
            "Ra'anana, Center District, Israel",
        )
        self.assertEqual(fake_session.search_requests[0]["domain"], "amdocs.com")
        self.assertEqual(fake_session.search_requests[0]["location"], "Israel")
        self.assertEqual(fake_session.search_requests[0]["filter_include_remote"], "1")
        self.assertEqual(fake_session.search_requests[1]["start"], 10)
        self.assertEqual(len(fake_session.detail_requests), 1)
        self.assertEqual(fake_session.detail_requests[0]["position_id"], "1")

    def test_bootstrap_uses_resolved_redirect_host_for_api_base(self) -> None:
        scraper = Eightfold()

        class RedirectSession:
            def get(self, url, params=None, timeout=None, verify=None):
                return _FakeResponse(
                    text=(
                        "<html><head><title>Careers at Microsoft</title></head><body>"
                        "<code>{\"domain\":\"microsoft.com\"}</code>"
                        "</body></html>"
                    ),
                    url="https://apply.careers.microsoft.com/careers?location=Israel",
                )

        scraper.session = RedirectSession()
        scraper.scraper_input = ScraperInput(site_type=[Site.EIGHTFOLD])

        context = scraper._bootstrap_company_context(
            "https://jobs.careers.microsoft.com/global/en/search?lc=Israel"
        )

        self.assertEqual(context["base_url"], "https://apply.careers.microsoft.com")
        self.assertEqual(
            context["company_url"],
            "https://apply.careers.microsoft.com/careers",
        )
        self.assertEqual(context["domain"], "microsoft.com")


if __name__ == "__main__":
    unittest.main()
