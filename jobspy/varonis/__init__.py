from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobspy.model import (
    DescriptionFormat,
    JobPost,
    JobResponse,
    Location,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    create_logger,
    create_session,
    extract_emails_from_text,
    markdown_converter,
    plain_converter,
)

log = create_logger("Varonis")

DEFAULT_VARONIS_BASE_URL = "https://careers.varonis.com/"
SEARCH_CRITERIA_PATH = "/api/getSearchCriteria"
REQUISITIONS_PATH = "/api/getRequisitions"
ISRAEL_COUNTRY = "Israel"


class Varonis(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.VARONIS,
            proxies=proxies,
            ca_cert=ca_cert,
            user_agent=user_agent,
        )
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
            delay=3,
        )
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": DEFAULT_VARONIS_BASE_URL,
            }
        )
        if self.user_agent:
            self.session.headers["User-Agent"] = self.user_agent
        self.scraper_input = None

    def _debug_enabled(self) -> bool:
        return bool(
            self.scraper_input
            and getattr(self.scraper_input, "varonis_debug_trace", False)
        )

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            log.info(f"[trace] {message}")

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        base_url = self._safe_str(scraper_input.varonis_base_url) or DEFAULT_VARONIS_BASE_URL
        base_url = base_url.rstrip("/") + "/"

        self._assert_israel_filter_available(base_url)
        requisitions = self._fetch_requisitions(base_url)
        israel_jobs = self._filter_israel_requisitions(requisitions)

        target_count = None
        if scraper_input.results_wanted and scraper_input.results_wanted > 0:
            target_count = scraper_input.results_wanted

        self._debug(
            "Initialized Varonis search with "
            f"base_url={base_url!r}, country={ISRAEL_COUNTRY!r}, "
            f"total_requisitions={len(requisitions)}, israel_requisitions={len(israel_jobs)}, "
            f"target_count={target_count}"
        )

        job_posts: list[JobPost] = []
        for raw_job, raw_location in israel_jobs:
            detail = None
            if self.claim_description_slot():
                detail = self._fetch_job_detail(raw_location)

            job_post = self._build_job_post(raw_job, raw_location, detail)
            if job_post is None:
                continue
            job_posts.append(job_post)
            if target_count is not None and len(job_posts) >= target_count:
                break

        self._debug(f"Varonis scrape complete with returned_jobs={len(job_posts)}")
        return JobResponse(jobs=job_posts)

    def _assert_israel_filter_available(self, base_url: str) -> None:
        criteria = self._get_json(urljoin(base_url, SEARCH_CRITERIA_PATH))
        filters = criteria.get("filters") if isinstance(criteria, dict) else None
        if not isinstance(filters, list):
            raise ValueError("Varonis search criteria response did not include filters")

        countries = []
        for filter_item in filters:
            if not isinstance(filter_item, dict):
                continue
            if self._safe_str(filter_item.get("title")) == "Country":
                values = filter_item.get("values") or []
                countries = [self._safe_str(value) for value in values]
                countries = [value for value in countries if value]
                break

        if ISRAEL_COUNTRY not in countries:
            raise ValueError(
                "Varonis careers page does not currently expose Israel as a "
                "country filter"
            )
        self._debug("Confirmed Israel is available in the Varonis country selector")

    def _fetch_requisitions(self, base_url: str) -> list[dict[str, Any]]:
        payload = self._get_json(urljoin(base_url, REQUISITIONS_PATH))
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("Varonis requisitions response did not include a data list")
        return [row for row in rows if isinstance(row, dict)]

    def _filter_israel_requisitions(
        self,
        requisitions: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for raw_job in requisitions:
            raw_locations = raw_job.get("jobLocations") or []
            if not isinstance(raw_locations, list):
                raw_locations = []

            location_matches = [
                location
                for location in raw_locations
                if isinstance(location, dict)
                and self._safe_str(location.get("country")) == ISRAEL_COUNTRY
            ]

            if (
                not location_matches
                and self._safe_str(raw_job.get("locationCountry")) == ISRAEL_COUNTRY
            ):
                matches.append((raw_job, {}))
                continue

            for raw_location in location_matches:
                matches.append((raw_job, raw_location))
        return matches

    def _fetch_job_detail(self, raw_location: dict[str, Any]) -> dict[str, str | None]:
        detail_url = self._safe_str(raw_location.get("jobDetailsUrl"))
        if not detail_url:
            return {"description": None, "job_url": None}

        response = self.session.get(
            detail_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        description_node = soup.select_one(".jv-job-detail-description")
        description_html = str(description_node) if description_node else None
        description = self._convert_description(description_html)
        self._debug(f"Fetched Varonis job detail url={response.url!r}")
        return {
            "description": description,
            "job_url": response.url,
        }

    def _build_job_post(
        self,
        raw_job: dict[str, Any],
        raw_location: dict[str, Any],
        detail: dict[str, str | None] | None,
    ) -> JobPost | None:
        title = self._safe_str(raw_job.get("title"))
        location = self._build_location(raw_job, raw_location)
        job_url = (
            self._safe_str((detail or {}).get("job_url"))
            or self._safe_str(raw_location.get("jobDetailsUrl"))
            or self._safe_str(raw_location.get("applyUrl"))
        )
        if not title or not job_url:
            return None

        description = self._safe_str((detail or {}).get("description"))
        emails = extract_emails_from_text(description or "") or None
        return JobPost(
            id=self._safe_str(raw_job.get("eId")),
            title=title,
            company_name="Varonis",
            job_url=job_url,
            apply_url=self._safe_str(raw_location.get("applyUrl")) or job_url,
            job_url_direct=job_url,
            location=location,
            description=description,
            company_url=DEFAULT_VARONIS_BASE_URL,
            company_url_direct=DEFAULT_VARONIS_BASE_URL,
            date_posted=self._parse_date(raw_job.get("datePosted")),
            emails=emails,
            job_function=self._safe_str(raw_job.get("department")),
            listing_type=self._safe_str(raw_job.get("subDepartment")),
        )

    def _build_location(
        self,
        raw_job: dict[str, Any],
        raw_location: dict[str, Any],
    ) -> Location:
        city = self._safe_str(raw_location.get("city")) or self._safe_str(
            raw_job.get("locationCity")
        )
        state = self._safe_str(raw_location.get("state"))
        country = self._safe_str(raw_location.get("country")) or self._safe_str(
            raw_job.get("locationCountry")
        ) or ISRAEL_COUNTRY
        return Location(city=city, state=state, country=country)

    def _get_json(self, url: str) -> Any:
        response = self.session.get(
            url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        return response.json()

    def _convert_description(self, description_html: str | None) -> str | None:
        if description_html is None:
            return None

        description_format = getattr(
            self.scraper_input,
            "description_format",
            DescriptionFormat.MARKDOWN,
        )
        if description_format == DescriptionFormat.HTML:
            return description_html
        if description_format == DescriptionFormat.PLAIN:
            return plain_converter(description_html)
        return markdown_converter(description_html)

    def _parse_date(self, value: Any):
        text = self._safe_str(value)
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            return None

    def _safe_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None
