from __future__ import annotations

import html as html_lib
import json
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from jobspy.model import (
    Country,
    DescriptionFormat,
    JobPost,
    JobResponse,
    Location,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import create_logger, create_session, extract_emails_from_text

log = create_logger("Apple")

DEFAULT_APPLE_SEARCH_URL = "https://jobs.apple.com/en-il/search?location=israel-ISR"
APPLE_COMPANY_URL = "https://jobs.apple.com"
APPLE_RECORDS_PER_PAGE = 20
HYDRATION_PREFIX = "window.__staticRouterHydrationData = JSON.parse("


class Apple(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.APPLE,
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
        if self.user_agent:
            self.session.headers["User-Agent"] = self.user_agent
        self.scraper_input = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        search_url = self._resolve_search_url(scraper_input)
        locale = self._extract_locale_from_url(search_url)
        requested_offset = max(scraper_input.offset or 0, 0)
        start_page = max(1, self._base_page_from_url(search_url) + (requested_offset // APPLE_RECORDS_PER_PAGE))
        page_skip = requested_offset % APPLE_RECORDS_PER_PAGE

        raw_jobs: list[dict[str, Any]] = []
        total_records: int | None = None
        current_page = start_page

        while True:
            search_payload = self._fetch_search_payload(search_url, page=current_page)
            if total_records is None:
                total_records = self._safe_int(search_payload.get("totalRecords")) or 0

            page_results = list(search_payload.get("searchResults") or [])
            if not page_results:
                break

            if current_page == start_page and page_skip:
                page_results = page_results[page_skip:]

            raw_jobs.extend(
                [row for row in page_results if isinstance(row, dict)]
            )

            target_count = self._resolve_target_count(
                total_records=total_records,
                requested_offset=requested_offset,
                results_wanted=scraper_input.results_wanted,
            )
            if len(raw_jobs) >= target_count:
                raw_jobs = raw_jobs[:target_count]
                break

            if current_page * APPLE_RECORDS_PER_PAGE >= total_records:
                break
            current_page += 1

        log.info(f"Fetching Apple jobs from {search_url}")
        returned_jobs: list[JobPost] = []
        for raw_job in raw_jobs:
            detail_data = None
            detail_url = self._build_detail_url(locale, raw_job)
            if detail_url and self.claim_description_slot():
                detail_data = self._fetch_detail_payload(detail_url)

            job_post = self._build_job_post(
                raw_job,
                detail_data=detail_data,
                detail_url=detail_url,
            )
            if job_post:
                returned_jobs.append(job_post)

        return JobResponse(jobs=returned_jobs)

    def _resolve_search_url(self, scraper_input: ScraperInput) -> str:
        base_url = self._safe_str(scraper_input.apple_search_url) or DEFAULT_APPLE_SEARCH_URL
        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        if scraper_input.search_term is not None:
            query_params["search"] = [scraper_input.search_term]
        normalized_query = urlencode(
            [(key, value) for key, values in query_params.items() for value in values],
            doseq=True,
        )
        return urlunparse(parsed._replace(query=normalized_query))

    def _fetch_search_payload(self, search_url: str, *, page: int) -> dict[str, Any]:
        page_url = self._set_query_param(search_url, "page", str(page))
        response = self.session.get(
            page_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        payload = self._extract_hydration_payload(response.text)
        loader_data = payload.get("loaderData") or {}
        search_payload = loader_data.get("search") or {}
        if not isinstance(search_payload, dict):
            raise ValueError("Apple search page did not expose search loader data")
        return search_payload

    def _fetch_detail_payload(self, detail_url: str) -> dict[str, Any] | None:
        response = self.session.get(
            detail_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        payload = self._extract_hydration_payload(response.text)
        loader_data = payload.get("loaderData") or {}
        detail_payload = (loader_data.get("jobDetails") or {}).get("jobsData")
        return detail_payload if isinstance(detail_payload, dict) else None

    def _extract_hydration_payload(self, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            text = script.get_text() or ""
            if not text.startswith(HYDRATION_PREFIX):
                continue
            encoded_payload = text[len(HYDRATION_PREFIX) :].strip()
            if encoded_payload.endswith(");"):
                encoded_payload = encoded_payload[:-2]
            decoded_payload = json.loads(encoded_payload)
            payload = json.loads(decoded_payload)
            if isinstance(payload, dict):
                return payload
        raise ValueError("Apple page did not expose hydration data")

    def _build_job_post(
        self,
        raw_job: dict[str, Any],
        *,
        detail_data: dict[str, Any] | None,
        detail_url: str | None,
    ) -> JobPost | None:
        title = self._safe_str(
            (detail_data or {}).get("postingTitle")
            or raw_job.get("postingTitle")
        )
        job_url = detail_url
        if not title or not job_url:
            return None

        description = self._build_description(raw_job, detail_data)
        emails = extract_emails_from_text(description or "") or None
        team_name = self._extract_team_name(detail_data or raw_job)
        location = self._build_location(detail_data or raw_job)
        role_id = self._safe_str(
            (detail_data or {}).get("jobNumber")
            or raw_job.get("reqId")
            or raw_job.get("id")
        )
        is_remote = self._coerce_bool((detail_data or {}).get("homeOffice"))
        if is_remote is None:
            is_remote = self._coerce_bool(raw_job.get("homeOffice"))

        return JobPost(
            id=role_id,
            title=title,
            company_name="Apple",
            job_url=job_url,
            apply_url=job_url,
            job_url_direct=job_url,
            location=location,
            description=description,
            company_url=APPLE_COMPANY_URL,
            company_url_direct=APPLE_COMPANY_URL,
            date_posted=self._parse_date(
                (detail_data or {}).get("postingDateMeta")
                or (detail_data or {}).get("postDateInGMT")
                or raw_job.get("postDateInGMT")
                or raw_job.get("postingDate")
            ),
            emails=emails,
            is_remote=is_remote,
            listing_type="remote" if is_remote else None,
            job_function=team_name,
        )

    def _build_description(
        self,
        raw_job: dict[str, Any],
        detail_data: dict[str, Any] | None,
    ) -> str | None:
        sections = [
            ("Summary", self._safe_str((detail_data or {}).get("jobSummary") or raw_job.get("jobSummary"))),
            ("Description", self._safe_str((detail_data or {}).get("description"))),
            ("Responsibilities", self._safe_str((detail_data or {}).get("responsibilities"))),
            ("Minimum Qualifications", self._safe_str((detail_data or {}).get("minimumQualifications"))),
            ("Preferred Qualifications", self._safe_str((detail_data or {}).get("preferredQualifications"))),
            ("Additional Requirements", self._safe_str((detail_data or {}).get("additionalRequirements"))),
        ]
        sections = [(title, content) for title, content in sections if content]
        if not sections:
            return None

        description_format = self.scraper_input.description_format
        if description_format == DescriptionFormat.HTML:
            return self._render_html_description(sections)
        if description_format == DescriptionFormat.PLAIN:
            return self._render_plain_description(sections)
        return self._render_markdown_description(sections)

    def _render_markdown_description(
        self,
        sections: list[tuple[str, str]],
    ) -> str:
        blocks: list[str] = []
        for title, content in sections:
            blocks.append(f"## {title}\n{self._render_markdown_content(content)}")
        return "\n\n".join(blocks).strip()

    def _render_plain_description(
        self,
        sections: list[tuple[str, str]],
    ) -> str:
        blocks: list[str] = []
        for title, content in sections:
            blocks.append(f"{title}\n{self._render_plain_content(content)}")
        return "\n\n".join(blocks).strip()

    def _render_html_description(
        self,
        sections: list[tuple[str, str]],
    ) -> str:
        blocks: list[str] = []
        for title, content in sections:
            rendered = self._render_html_content(content)
            blocks.append(f"<h2>{html_lib.escape(title)}</h2>{rendered}")
        return "".join(blocks).strip()

    def _render_markdown_content(self, content: str) -> str:
        lines = self._split_lines(content)
        if len(lines) <= 1:
            return lines[0] if lines else ""
        return "\n".join(f"- {line}" for line in lines)

    def _render_plain_content(self, content: str) -> str:
        return "\n".join(self._split_lines(content))

    def _render_html_content(self, content: str) -> str:
        lines = [html_lib.escape(line) for line in self._split_lines(content)]
        if len(lines) <= 1:
            value = lines[0] if lines else ""
            return f"<p>{value}</p>"
        list_items = "".join(f"<li>{line}</li>" for line in lines)
        return f"<ul>{list_items}</ul>"

    def _split_lines(self, content: str) -> list[str]:
        return [
            line
            for raw_line in content.splitlines()
            if (line := self._safe_str(raw_line)) is not None
        ]

    def _build_location(self, raw_job: dict[str, Any]) -> Location | None:
        raw_locations = raw_job.get("locations") or []
        if not isinstance(raw_locations, list) or not raw_locations:
            return None

        selected = next(
            (
                location
                for location in raw_locations
                if isinstance(location, dict) and location.get("active")
            ),
            None,
        )
        location_data = selected or next(
            (location for location in raw_locations if isinstance(location, dict)),
            None,
        )
        if not location_data:
            return None

        country_name = self._safe_str(location_data.get("countryName"))
        country: Country | str | None = country_name
        if country_name:
            try:
                country = Country.from_string(country_name)
            except ValueError:
                country = country_name

        city = self._safe_str(location_data.get("city")) or self._safe_str(
            location_data.get("name")
        )
        return Location(
            country=country,
            city=city,
            state=self._safe_str(location_data.get("stateProvince")),
        )

    def _build_detail_url(self, locale: str, raw_job: dict[str, Any]) -> str | None:
        req_id = self._safe_str(raw_job.get("reqId") or raw_job.get("id"))
        slug = self._safe_str(raw_job.get("transformedPostingTitle"))
        team_code = self._safe_str(((raw_job.get("team") or {}).get("teamCode")))
        if not req_id or not slug:
            return None

        path = f"/{locale}/details/{req_id}/{slug}"
        if not team_code:
            return f"{APPLE_COMPANY_URL}{path}"
        return f"{APPLE_COMPANY_URL}{path}?team={team_code}"

    def _extract_team_name(self, raw_job: dict[str, Any]) -> str | None:
        team_names = raw_job.get("teamNames")
        if isinstance(team_names, list):
            for team_name in team_names:
                normalized = self._safe_str(team_name)
                if normalized:
                    return normalized
        if isinstance(raw_job.get("team"), dict):
            return self._safe_str((raw_job.get("team") or {}).get("teamName"))
        return None

    def _parse_date(self, value: Any) -> date | None:
        text = self._safe_str(value)
        if not text:
            return None

        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            pass

        for fmt in ("%d %b %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _base_page_from_url(self, search_url: str) -> int:
        parsed = urlparse(search_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        return self._safe_int((query_params.get("page") or ["1"])[0]) or 1

    def _extract_locale_from_url(self, search_url: str) -> str:
        path_parts = [part for part in urlparse(search_url).path.split("/") if part]
        if path_parts:
            return path_parts[0]
        return "en-il"

    def _set_query_param(self, url: str, key: str, value: str) -> str:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params[key] = [value]
        query = urlencode(
            [(name, item) for name, values in query_params.items() for item in values],
            doseq=True,
        )
        return urlunparse(parsed._replace(query=query))

    def _resolve_target_count(
        self,
        *,
        total_records: int,
        requested_offset: int,
        results_wanted: int | None,
    ) -> int:
        available = max(total_records - requested_offset, 0)
        if results_wanted is None or results_wanted <= 0:
            return available
        return min(available, results_wanted)

    def _coerce_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        return None

    def _safe_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None

    def _safe_int(self, value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = self._safe_str(value)
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
