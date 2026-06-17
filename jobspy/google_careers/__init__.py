from __future__ import annotations

import ast
import html as html_lib
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

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
from jobspy.util import (
    create_logger,
    create_session,
    extract_emails_from_text,
    markdown_converter,
    plain_converter,
)

log = create_logger("GoogleCareers")

DEFAULT_GOOGLE_CAREERS_URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "?q=&location=Israel&hl=en"
)
GOOGLE_CAREERS_HOME_URL = "https://www.google.com/about/careers/applications/"
GOOGLE_CAREERS_RECORDS_PER_PAGE = 20


class GoogleCareers(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.GOOGLE_CAREERS,
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
        requested_offset = max(scraper_input.offset or 0, 0)
        start_page = max(
            1,
            self._base_page_from_url(search_url)
            + (requested_offset // GOOGLE_CAREERS_RECORDS_PER_PAGE),
        )
        page_skip = requested_offset % GOOGLE_CAREERS_RECORDS_PER_PAGE

        raw_jobs: list[dict[str, Any]] = []
        total_records: int | None = None
        current_page = start_page

        while True:
            page_payload = self._fetch_search_page(search_url, page=current_page)
            page_results = list(page_payload["jobs"])
            if total_records is None:
                total_records = page_payload["total_records"]

            if not page_results:
                break

            if current_page == start_page and page_skip:
                page_results = page_results[page_skip:]

            raw_jobs.extend(page_results)

            target_count = self._resolve_target_count(
                total_records=total_records,
                requested_offset=requested_offset,
                results_wanted=scraper_input.results_wanted,
            )
            if len(raw_jobs) >= target_count:
                raw_jobs = raw_jobs[:target_count]
                break

            if (
                current_page * GOOGLE_CAREERS_RECORDS_PER_PAGE >= total_records
                or len(page_payload["jobs"]) < GOOGLE_CAREERS_RECORDS_PER_PAGE
            ):
                break

            current_page += 1

        returned_jobs: list[JobPost] = []
        for raw_job in raw_jobs:
            job_post = self._build_job_post(raw_job, search_url=search_url)
            if job_post:
                returned_jobs.append(job_post)

        log.info(f"Fetched {len(returned_jobs)} Google Careers jobs from {search_url}")
        return JobResponse(jobs=returned_jobs)

    def _resolve_search_url(self, scraper_input: ScraperInput) -> str:
        base_url = (
            self._safe_str(scraper_input.google_careers_url)
            or DEFAULT_GOOGLE_CAREERS_URL
        )
        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        if scraper_input.search_term is not None:
            query_params["q"] = [scraper_input.search_term]
        if scraper_input.location is not None:
            query_params["location"] = [scraper_input.location]

        normalized_query = urlencode(
            [(key, value) for key, values in query_params.items() for value in values],
            doseq=True,
        )
        return urlunparse(parsed._replace(query=normalized_query))

    def _fetch_search_page(self, search_url: str, *, page: int) -> dict[str, Any]:
        page_url = self._set_query_param(search_url, "page", str(page))
        response = self.session.get(
            page_url,
            timeout=self.scraper_input.request_timeout,
        )
        response.raise_for_status()

        payload = self._extract_init_data_payload(response.text, dataset_key="ds:1")
        if not isinstance(payload, list) or not payload:
            raise ValueError("Google Careers page did not expose search results data")

        raw_jobs = payload[0] if isinstance(payload[0], list) else []
        total_records = self._safe_int(payload[2]) or len(raw_jobs)
        detail_url_map = self._extract_detail_url_map(response.text, page_url)

        jobs = []
        for raw_job in raw_jobs:
            if not isinstance(raw_job, list):
                continue
            job_id = self._safe_str(raw_job[0] if len(raw_job) > 0 else None)
            jobs.append(
                {
                    "data": raw_job,
                    "detail_url": detail_url_map.get(job_id) if job_id else None,
                }
            )

        return {
            "jobs": jobs,
            "total_records": total_records,
        }

    def _extract_init_data_payload(
        self,
        html: str,
        *,
        dataset_key: str,
    ) -> list[Any]:
        soup = BeautifulSoup(html, "html.parser")
        target_class = dataset_key
        for script in soup.find_all("script"):
            classes = script.get("class") or []
            if target_class not in classes:
                continue
            script_text = script.get_text() or ""
            data_marker = "data:"
            side_channel_marker = ", sideChannel:"
            start_idx = script_text.find(data_marker)
            end_idx = script_text.rfind(side_channel_marker)
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                continue

            raw_literal = script_text[start_idx + len(data_marker) : end_idx].strip()
            python_literal = self._replace_js_primitives(raw_literal)
            payload = ast.literal_eval(python_literal)
            if isinstance(payload, list):
                return payload

        raise ValueError(
            f"Google Careers page did not expose AF_initData payload for {dataset_key}"
        )

    def _extract_detail_url_map(self, html: str, page_url: str) -> dict[str, str]:
        detail_url_map: dict[str, str] = {}
        soup = BeautifulSoup(html, "html.parser")
        base_tag = soup.find("base")
        base_href = self._safe_str(base_tag.get("href")) if base_tag else None
        join_base = base_href or page_url
        for href, job_id in re.findall(
            r'href="([^"]*jobs/results/(\d+)-[^"]*)"',
            html,
        ):
            resolved_href = html_lib.unescape(href)
            detail_url_map[job_id] = self._normalize_detail_url(
                urljoin(join_base, resolved_href)
            )
        return detail_url_map

    def _replace_js_primitives(self, value: str) -> str:
        result: list[str] = []
        quote_char: str | None = None
        is_escaped = False
        index = 0

        while index < len(value):
            char = value[index]

            if quote_char is not None:
                result.append(char)
                if is_escaped:
                    is_escaped = False
                elif char == "\\":
                    is_escaped = True
                elif char == quote_char:
                    quote_char = None
                index += 1
                continue

            if char in {"'", '"'}:
                quote_char = char
                result.append(char)
                index += 1
                continue

            if self._has_literal(value, index, "null"):
                result.append("None")
                index += 4
                continue
            if self._has_literal(value, index, "true"):
                result.append("True")
                index += 4
                continue
            if self._has_literal(value, index, "false"):
                result.append("False")
                index += 5
                continue

            result.append(char)
            index += 1

        return "".join(result)

    def _has_literal(self, value: str, start_index: int, literal: str) -> bool:
        end_index = start_index + len(literal)
        if value[start_index:end_index] != literal:
            return False
        return self._is_boundary(value, start_index - 1) and self._is_boundary(
            value, end_index
        )

    def _is_boundary(self, value: str, index: int) -> bool:
        if index < 0 or index >= len(value):
            return True
        return not (value[index].isalnum() or value[index] in {"_", "$"})

    def _build_job_post(
        self,
        raw_job: dict[str, Any],
        *,
        search_url: str,
    ) -> JobPost | None:
        row = raw_job.get("data")
        if not isinstance(row, list):
            return None

        job_id = self._safe_str(row[0] if len(row) > 0 else None)
        title = self._safe_str(row[1] if len(row) > 1 else None)
        apply_url = self._safe_str(row[2] if len(row) > 2 else None)
        detail_url = raw_job.get("detail_url") or self._build_detail_url(search_url, row)
        if not job_id or not title or not (detail_url or apply_url):
            return None

        full_description = self._build_description(
            row,
            include_full_sections=self.claim_description_slot(),
        )
        summary_description = self._build_summary_description(row)
        description = full_description or summary_description
        emails = extract_emails_from_text(description or "") or None
        location = self._build_location(row[9] if len(row) > 9 else None)
        is_remote = self._infer_is_remote(row, description)

        public_url = detail_url or apply_url

        return JobPost(
            id=job_id,
            title=title,
            company_name=self._safe_str(row[7] if len(row) > 7 else None),
            job_url=public_url,
            apply_url=apply_url,
            job_url_direct=public_url,
            location=location,
            description=description,
            company_url=GOOGLE_CAREERS_HOME_URL,
            company_url_direct=GOOGLE_CAREERS_HOME_URL,
            date_posted=self._parse_proto_date(row),
            emails=emails,
            is_remote=is_remote,
            listing_type="remote" if is_remote else None,
        )

    def _build_detail_url(self, search_url: str, row: list[Any]) -> str | None:
        job_id = self._safe_str(row[0] if len(row) > 0 else None)
        title = self._safe_str(row[1] if len(row) > 1 else None)
        if not job_id or not title:
            return None

        parsed = urlparse(search_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params.pop("page", None)
        normalized_query = urlencode(
            [(key, value) for key, values in query_params.items() for value in values],
            doseq=True,
        )
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        detail_path = f"{parsed.path.rstrip('/')}/{job_id}-{slug}"
        return self._normalize_detail_url(
            urlunparse(parsed._replace(path=detail_path, query=normalized_query))
        )

    def _normalize_detail_url(self, detail_url: str) -> str:
        parsed = urlparse(detail_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params.pop("page", None)
        normalized_query = urlencode(
            [(key, value) for key, values in query_params.items() for value in values],
            doseq=True,
        )
        return urlunparse(parsed._replace(query=normalized_query))

    def _build_summary_description(self, row: list[Any]) -> str | None:
        overview = self._extract_fragment_html(row[10] if len(row) > 10 else None)
        if not overview:
            return None

        description_format = self.scraper_input.description_format
        if description_format == DescriptionFormat.HTML:
            return f"<h2>Overview</h2>{self._as_html_fragment(overview)}"
        if description_format == DescriptionFormat.PLAIN:
            return f"Overview\n{self._fragment_to_plain(overview)}".strip()
        return f"## Overview\n{self._fragment_to_markdown(overview)}".strip()

    def _build_description(
        self,
        row: list[Any],
        *,
        include_full_sections: bool,
    ) -> str | None:
        sections = [
            ("Overview", self._extract_fragment_html(row[10] if len(row) > 10 else None)),
        ]
        if include_full_sections:
            sections.extend(
                [
                    (
                        "Responsibilities",
                        self._extract_fragment_html(row[3] if len(row) > 3 else None),
                    ),
                    (
                        "Qualifications",
                        self._extract_fragment_html(row[4] if len(row) > 4 else None)
                        or self._extract_fragment_html(row[19] if len(row) > 19 else None),
                    ),
                    (
                        "Additional Information",
                        self._extract_fragment_html(row[18] if len(row) > 18 else None),
                    ),
                ]
            )

        sections = [(title, content) for title, content in sections if content]
        if not sections:
            return None

        description_format = self.scraper_input.description_format
        if description_format == DescriptionFormat.HTML:
            return "".join(
                f"<h2>{html_lib.escape(title)}</h2>{self._as_html_fragment(content)}"
                for title, content in sections
            ).strip()
        if description_format == DescriptionFormat.PLAIN:
            return "\n\n".join(
                f"{title}\n{self._fragment_to_plain(content)}"
                for title, content in sections
            ).strip()
        return "\n\n".join(
            f"## {title}\n{self._fragment_to_markdown(content)}"
            for title, content in sections
        ).strip()

    def _extract_fragment_html(self, value: Any) -> str | None:
        if isinstance(value, list) and len(value) > 1:
            return self._safe_str(value[1])
        return self._safe_str(value)

    def _as_html_fragment(self, content: str) -> str:
        if "<" in content and ">" in content:
            return content
        return f"<p>{html_lib.escape(content)}</p>"

    def _fragment_to_markdown(self, content: str) -> str:
        html_fragment = self._as_html_fragment(content)
        markdown = markdown_converter(html_fragment)
        return (markdown or "").strip()

    def _fragment_to_plain(self, content: str) -> str:
        html_fragment = self._as_html_fragment(content)
        text = plain_converter(html_fragment)
        return (text or "").strip()

    def _build_location(self, raw_locations: Any) -> Location | None:
        if not isinstance(raw_locations, list) or not raw_locations:
            return None

        primary_location = next(
            (
                location
                for location in raw_locations
                if isinstance(location, list) and location
            ),
            None,
        )
        if not primary_location:
            return None

        display_name = self._safe_str(primary_location[0] if len(primary_location) > 0 else None)
        city = self._safe_str(primary_location[2] if len(primary_location) > 2 else None)
        state = self._safe_str(primary_location[4] if len(primary_location) > 4 else None)
        country_name = self._extract_country_name(
            display_name=display_name,
            location_parts=primary_location,
        )

        country: Country | str | None = country_name
        if country_name:
            try:
                country = Country.from_string(country_name)
            except ValueError:
                country = country_name

        if not city and display_name and "," in display_name:
            city = display_name.split(",", 1)[0].strip()

        return Location(country=country, city=city, state=state)

    def _extract_country_name(
        self,
        *,
        display_name: str | None,
        location_parts: list[Any],
    ) -> str | None:
        if display_name and "," in display_name:
            return display_name.rsplit(",", 1)[-1].strip()

        country_code = self._safe_str(location_parts[5] if len(location_parts) > 5 else None)
        if country_code == "IL":
            return "Israel"
        return country_code

    def _parse_proto_date(self, row: list[Any]) -> date | None:
        for index in (12, 13, 14):
            value = row[index] if len(row) > index else None
            if not isinstance(value, list) or not value:
                continue
            seconds = value[0]
            if not isinstance(seconds, (int, float)):
                continue
            try:
                return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
            except (OverflowError, OSError, ValueError):
                continue
        return None

    def _infer_is_remote(self, row: list[Any], description: str | None) -> bool:
        raw_locations = row[9] if len(row) > 9 else None
        if isinstance(raw_locations, list):
            for location in raw_locations:
                if not isinstance(location, list):
                    continue
                display_name = self._safe_str(location[0] if len(location) > 0 else None)
                if display_name and "remote" in display_name.lower():
                    return True

        if description:
            description_lower = description.lower()
            return "remote" in description_lower or "work from home" in description_lower
        return False

    def _base_page_from_url(self, search_url: str) -> int:
        parsed = urlparse(search_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        return self._safe_int((query_params.get("page") or ["1"])[0]) or 1

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
