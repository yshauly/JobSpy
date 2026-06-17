from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

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

log = create_logger("Meta")

DEFAULT_META_CAREERS_URL = "https://www.metacareers.com/jobsearch/"
META_COMPANY_URL = "https://www.metacareers.com"
META_SEARCH_ENDPOINT = "https://www.metacareers.com/search/filter/"
META_RESULTS_PER_PAGE = 25
META_AJAX_PREFIX = "for (;;);"


class Meta(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.META,
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
        careers_url = self._safe_str(scraper_input.meta_careers_url) or DEFAULT_META_CAREERS_URL
        base_params = self._build_search_params(careers_url, scraper_input)
        requested_offset = max(scraper_input.offset or 0, 0)
        start_page = max(1, (requested_offset // META_RESULTS_PER_PAGE) + 1)
        page_skip = requested_offset % META_RESULTS_PER_PAGE

        raw_jobs: list[dict[str, str | None]] = []
        total_count: int | None = None
        current_page = start_page

        while True:
            page_payload = self._fetch_search_page(base_params, page=current_page)
            if total_count is None:
                total_count = page_payload["total_count"]

            page_jobs = page_payload["jobs"]
            if current_page == start_page and page_skip:
                page_jobs = page_jobs[page_skip:]
            if not page_jobs:
                break

            raw_jobs.extend(page_jobs)
            target_count = self._resolve_target_count(
                total_count=total_count,
                requested_offset=requested_offset,
                results_wanted=scraper_input.results_wanted,
            )
            if len(raw_jobs) >= target_count:
                raw_jobs = raw_jobs[:target_count]
                break
            if current_page * META_RESULTS_PER_PAGE >= total_count:
                break
            current_page += 1

        log.info(f"Fetching Meta jobs from {careers_url}")
        returned_jobs: list[JobPost] = []
        for raw_job in raw_jobs:
            detail_data = None
            job_url = self._safe_str(raw_job.get("job_url"))
            if job_url and self.claim_description_slot():
                detail_data = self._fetch_detail_data(job_url)
            job_post = self._build_job_post(raw_job, detail_data)
            if job_post:
                returned_jobs.append(job_post)
        return JobResponse(jobs=returned_jobs)

    def _build_search_params(
        self,
        careers_url: str,
        scraper_input: ScraperInput,
    ) -> dict[str, Any]:
        parsed = urlparse(careers_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        params: dict[str, Any] = {
            "results_per_page": META_RESULTS_PER_PAGE,
            "is_in_page": "true",
            "search_result_section_id": "search_result",
            "__a": "1",
        }

        for key, values in query_params.items():
            if values:
                params[key] = values if len(values) > 1 else values[0]

        query = self._safe_str(scraper_input.search_term)
        if query is None:
            query = self._safe_str((query_params.get("q") or [None])[0])
        params["q"] = query if query is not None else "*"

        return params

    def _fetch_search_page(
        self,
        base_params: dict[str, Any],
        *,
        page: int,
    ) -> dict[str, Any]:
        params = dict(base_params)
        params["page"] = page
        response = self.session.get(
            META_SEARCH_ENDPOINT,
            params=params,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        payload = self._parse_ajax_payload(response.text)
        html_fragment = self._extract_domops_html(payload)
        return {
            "jobs": self._extract_search_jobs(html_fragment),
            "total_count": self._extract_total_count(html_fragment),
        }

    def _parse_ajax_payload(self, text: str) -> dict[str, Any]:
        if text.startswith(META_AJAX_PREFIX):
            text = text[len(META_AJAX_PREFIX) :]
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Meta search response did not include an object payload")
        return payload

    def _extract_domops_html(self, payload: dict[str, Any]) -> str:
        fragments: list[str] = []
        for operation in payload.get("domops") or []:
            if (
                isinstance(operation, list)
                and len(operation) >= 4
                and isinstance(operation[3], dict)
            ):
                html_fragment = self._safe_str(operation[3].get("__html"))
                if html_fragment:
                    fragments.append(html_fragment)
        return "\n".join(fragments)

    def _extract_search_jobs(
        self,
        html_fragment: str,
    ) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html_fragment, "html.parser")
        jobs: list[dict[str, str | None]] = []
        seen_urls: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = self._safe_str(link.get("href"))
            if not href or not href.startswith("/jobs/") or href == "/jobs/":
                continue
            job_url = urljoin(META_COMPANY_URL, href)
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            title = self._safe_str(self._text_from_first(link, "._8sel"))
            labels = [
                label
                for label in (
                    self._safe_str(node.get_text(" ", strip=True))
                    for node in link.select("._8see")
                )
                if label
            ]
            jobs.append(
                {
                    "id": self._extract_job_id(job_url),
                    "title": title,
                    "job_url": job_url,
                    "location": labels[0] if labels else None,
                    "job_function": labels[1] if len(labels) > 1 else None,
                    "job_level": labels[2] if len(labels) > 2 else None,
                }
            )
        return jobs

    def _extract_total_count(self, html_fragment: str) -> int:
        soup = BeautifulSoup(html_fragment, "html.parser")
        text = soup.get_text(" ", strip=True)
        match = re.search(r"Viewing\s+([0-9,]+)\s+Jobs?", text)
        if not match:
            return 0
        return int(match.group(1).replace(",", ""))

    def _fetch_detail_data(self, job_url: str) -> dict[str, Any] | None:
        response = self.session.get(
            job_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            text = script.get_text(strip=True)
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
                return payload
        return None

    def _build_job_post(
        self,
        raw_job: dict[str, str | None],
        detail_data: dict[str, Any] | None,
    ) -> JobPost | None:
        title = self._safe_str((detail_data or {}).get("title")) or self._safe_str(
            raw_job.get("title")
        )
        job_url = self._safe_str(raw_job.get("job_url"))
        if not title or not job_url:
            return None

        description = self._build_description(detail_data)
        location = self._build_location(detail_data, raw_job.get("location"))
        job_function = self._safe_str(raw_job.get("job_function"))
        job_level = self._safe_str(raw_job.get("job_level"))

        return JobPost(
            id=self._safe_str(raw_job.get("id")) or self._extract_job_id(job_url),
            title=title,
            company_name="Meta",
            job_url=job_url,
            apply_url=job_url,
            job_url_direct=job_url,
            location=location,
            description=description,
            company_url=META_COMPANY_URL,
            company_url_direct=META_COMPANY_URL,
            date_posted=self._parse_date((detail_data or {}).get("datePosted")),
            emails=extract_emails_from_text(description or "") or None,
            job_function=job_function,
            job_level=job_level,
        )

    def _build_description(self, detail_data: dict[str, Any] | None) -> str | None:
        if not detail_data:
            return None

        sections = [
            ("Description", self._safe_str(detail_data.get("description"))),
            ("Responsibilities", self._safe_str(detail_data.get("responsibilities"))),
            ("Qualifications", self._safe_str(detail_data.get("qualifications"))),
        ]
        sections = [(title, content) for title, content in sections if content]
        if not sections:
            return None

        description_format = self.scraper_input.description_format
        if description_format == DescriptionFormat.HTML:
            return "".join(
                f"<h2>{title}</h2><p>{content}</p>" for title, content in sections
            )
        if description_format == DescriptionFormat.PLAIN:
            return "\n\n".join(f"{title}\n{content}" for title, content in sections)
        return "\n\n".join(f"## {title}\n{content}" for title, content in sections)

    def _build_location(
        self,
        detail_data: dict[str, Any] | None,
        fallback_location: Any,
    ) -> Location | None:
        raw_location = self._safe_str(fallback_location)
        job_locations = (detail_data or {}).get("jobLocation")
        if isinstance(job_locations, dict):
            job_locations = [job_locations]
        if isinstance(job_locations, list):
            for item in job_locations:
                if isinstance(item, dict):
                    raw_location = self._safe_str(item.get("name")) or raw_location
                    break
        if not raw_location:
            return None

        parts = [part.strip() for part in raw_location.split(",") if part.strip()]
        if len(parts) >= 2:
            country = self._parse_country(parts[-1])
            return Location(city=", ".join(parts[:-1]) or None, country=country)
        return Location(country=self._parse_country(raw_location))

    def _parse_country(self, text: str) -> Country | str | None:
        try:
            return Country.from_string(text)
        except ValueError:
            return text

    def _parse_date(self, value: Any):
        text = self._safe_str(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None

    def _resolve_target_count(
        self,
        *,
        total_count: int,
        requested_offset: int,
        results_wanted: int,
    ) -> int:
        remaining = max(total_count - requested_offset, 0)
        if results_wanted is None or results_wanted <= 0:
            return remaining
        return min(results_wanted, remaining)

    def _extract_job_id(self, job_url: str) -> str | None:
        parsed = urlparse(job_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "jobs":
            return parts[1]
        return None

    def _text_from_first(self, soup: BeautifulSoup, selector: str) -> str | None:
        element = soup.select_one(selector)
        return element.get_text(" ", strip=True) if element else None

    def _safe_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None
