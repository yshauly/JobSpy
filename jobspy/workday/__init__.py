from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from jobspy.model import (
    DescriptionFormat,
    JobPost,
    JobResponse,
    JobType,
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

log = create_logger("Workday")

WORKDAY_TENANT_REGEX = re.compile(r'tenant:\s*"(?P<tenant>[^"]+)"')
WORKDAY_SITE_ID_REGEX = re.compile(r'siteId:\s*"(?P<site_id>[^"]+)"')
WORKDAY_REQUEST_LOCALE_REGEX = re.compile(
    r'requestLocale:\s*"(?P<request_locale>[^"]+)"'
)
WORKDAY_REMOTE_REGEX = re.compile(r"\bremote\b", re.I)
WORKDAY_REGION_PREFIX_REGEX = re.compile(
    r"^(?:[A-Z]{2}(?:-[A-Z]{2,})?\s*-\s*)(?P<location>.+)$"
)
WORKDAY_LOCATION_SUFFIX_REGEX = re.compile(r"\s*-\s*[A-Z]{2,4}$")
WORKDAY_POSTED_DAYS_AGO_REGEX = re.compile(r"Posted\s+(?P<days>\d+)\s+Days?\s+Ago", re.I)
WORKDAY_EXTERNAL_ID_REGEX = re.compile(r"_(?P<external_id>[^/?#]+)$")


class Workday(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.WORKDAY,
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

    def _debug_enabled(self) -> bool:
        return bool(
            self.scraper_input
            and getattr(self.scraper_input, "workday_debug_trace", False)
        )

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            log.info(f"[trace] {message}")

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        company_url = self._safe_str(scraper_input.workday_company_url)
        if not company_url:
            raise ValueError(
                "Workday scrape requires scraper_input.workday_company_url"
            )

        context = self._bootstrap_company_context(company_url)
        requested_offset, base_payload = self._build_listing_payload(
            company_url,
            scraper_input,
        )
        api_base_url = context["api_base_url"]
        job_posts: list[JobPost] = []
        total_count: int | None = None
        current_offset = requested_offset
        page_size = 20

        requested_results = scraper_input.results_wanted
        target_count = None
        if requested_results is not None and requested_results > 0:
            target_count = requested_results

        self._debug(
            "Initialized Workday search with "
            f"company_url={company_url!r}, requested_offset={requested_offset}, "
            f"target_count={target_count}, appliedFacets={base_payload.get('appliedFacets')}"
        )

        while True:
            if target_count is not None and len(job_posts) >= target_count:
                break

            limit = page_size
            if target_count is not None:
                limit = min(page_size, target_count - len(job_posts))
            if limit <= 0:
                break

            page_payload = self._fetch_listing_page(
                api_base_url,
                base_payload=base_payload,
                offset=current_offset,
                limit=limit,
            )
            if total_count is None:
                total_count = self._safe_int(page_payload.get("total")) or 0

            raw_jobs = page_payload.get("jobPostings") or []
            self._debug(
                f"Workday page offset={current_offset} "
                f"returned_jobs={len(raw_jobs)} total={total_count}"
            )
            if not raw_jobs:
                break

            for raw_job in raw_jobs:
                if not isinstance(raw_job, dict):
                    continue

                detail_data: dict[str, Any] | None = None
                if self.claim_description_slot():
                    try:
                        detail_data = self._fetch_job_detail(api_base_url, raw_job)
                    except Exception as exc:
                        self._debug(
                            f"Failed to hydrate Workday job "
                            f"{raw_job.get('externalPath')!r}: {exc}"
                        )
                        detail_data = None

                job_post = self._build_job_post(
                    raw_job=raw_job,
                    detail_data=detail_data,
                    context=context,
                )
                if job_post is None:
                    continue
                job_posts.append(job_post)

                if target_count is not None and len(job_posts) >= target_count:
                    break

            current_offset += len(raw_jobs)
            if current_offset >= (total_count or 0):
                break

        self._debug(
            f"Workday scrape complete with returned_jobs={len(job_posts)}"
        )
        return JobResponse(jobs=job_posts)

    def _bootstrap_company_context(self, company_url: str) -> dict[str, str | None]:
        response = self.session.get(
            company_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        parsed = urlparse(company_url)
        canonical_href = self._safe_str(
            (soup.find("link", rel="canonical") or {}).get("href")
        )
        canonical_url = canonical_href or urlunparse(
            parsed._replace(query="", fragment="")
        )
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        tenant = self._extract_workday_value(response.text, WORKDAY_TENANT_REGEX)
        site_id = self._extract_workday_value(response.text, WORKDAY_SITE_ID_REGEX)
        request_locale = self._extract_workday_value(
            response.text,
            WORKDAY_REQUEST_LOCALE_REGEX,
        )
        if not tenant or not site_id:
            raise ValueError(
                "Workday bootstrap page did not expose tenant/siteId; "
                "page structure may have changed"
            )

        raw_company_name = self._repair_mojibake(
            self._safe_str(self._get_meta_content(soup, "og:title"))
        )
        company_name = raw_company_name.removesuffix(" Careers").strip() if raw_company_name else None
        company_description = self._repair_mojibake(
            self._safe_str(self._get_meta_content(soup, "og:description"))
        )
        company_logo = self._normalize_url(
            base_url,
            self._get_meta_content(soup, "og:image"),
        )

        context = {
            "base_url": base_url,
            "canonical_url": canonical_url,
            "tenant": tenant,
            "site_id": site_id,
            "request_locale": request_locale,
            "company_name": company_name,
            "company_description": company_description,
            "company_logo": company_logo,
            "api_base_url": f"{base_url}/wday/cxs/{tenant}/{site_id}",
        }
        self._debug(f"Bootstrapped Workday context: {context}")
        return context

    def _build_listing_payload(
        self,
        company_url: str,
        scraper_input: ScraperInput,
    ) -> tuple[int, dict[str, Any]]:
        parsed = urlparse(company_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        base_offset = self._safe_int((query_params.get("start") or ["0"])[0]) or 0
        requested_offset = base_offset + max(scraper_input.offset or 0, 0)

        search_text = self._safe_str(scraper_input.search_term)
        if search_text is None:
            search_text = self._safe_str(
                (query_params.get("searchText") or query_params.get("query") or [None])[0]
            ) or ""

        applied_facets: dict[str, list[str]] = {}
        for key, values in query_params.items():
            if key in {"start", "offset", "limit", "query", "searchText"}:
                continue
            normalized_values = [
                normalized
                for value in values
                if (normalized := self._safe_str(value)) is not None
            ]
            if normalized_values:
                applied_facets[key] = normalized_values

        payload = {
            "appliedFacets": applied_facets,
            "searchText": search_text,
        }
        return requested_offset, payload

    def _fetch_listing_page(
        self,
        api_base_url: str,
        *,
        base_payload: dict[str, Any],
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        payload = {
            **base_payload,
            "offset": offset,
            "limit": limit,
        }
        response = self.session.post(
            f"{api_base_url}/jobs",
            json=payload,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        return response.json()

    def _fetch_job_detail(
        self,
        api_base_url: str,
        raw_job: dict[str, Any],
    ) -> dict[str, Any]:
        external_path = self._safe_str(raw_job.get("externalPath"))
        if not external_path:
            return {}

        response = self.session.get(
            f"{api_base_url}{external_path}",
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        payload = response.json()
        self._debug(
            f"Fetched Workday job detail for externalPath={external_path!r}"
        )
        return payload if isinstance(payload, dict) else {}

    def _build_job_post(
        self,
        *,
        raw_job: dict[str, Any],
        detail_data: dict[str, Any] | None,
        context: dict[str, str | None],
    ) -> JobPost | None:
        detail_info = (detail_data or {}).get("jobPostingInfo") or {}
        if not isinstance(detail_info, dict):
            detail_info = {}

        title = self._safe_str(detail_info.get("title")) or self._safe_str(
            raw_job.get("title")
        )
        job_url = self._safe_str(detail_info.get("externalUrl")) or self._normalize_url(
            context["base_url"] or "",
            raw_job.get("externalPath"),
        )
        if not title or not job_url:
            return None

        description_html = self._safe_html(detail_info.get("jobDescription"))
        description = self._convert_description(description_html)
        emails = extract_emails_from_text(description or "") or None
        is_remote = self._is_remote(detail_info, raw_job)
        time_type = self._safe_str(detail_info.get("timeType"))
        country_text = self._safe_str(
            ((detail_info.get("country") or {}).get("descriptor"))
            if isinstance(detail_info.get("country"), dict)
            else None
        )
        location = self._build_location(
            detail_info=detail_info,
            raw_job=raw_job,
            country_text=country_text,
        )
        external_id = self._safe_str(detail_info.get("jobReqId")) or self._safe_str(
            self._first_list_value(raw_job.get("bulletFields"))
        ) or self._extract_external_id(job_url)
        posted_date = self._parse_date(detail_info.get("startDate")) or self._parse_relative_posted_date(
            raw_job.get("postedOn")
        )

        return JobPost(
            id=external_id or self._safe_str(detail_info.get("id")),
            title=title,
            company_name=context["company_name"],
            job_url=job_url,
            apply_url=job_url,
            job_url_direct=job_url,
            location=location,
            description=description,
            company_url=context["canonical_url"],
            company_url_direct=context["canonical_url"],
            job_type=self._parse_job_type(
                time_type=time_type,
                title=title,
            ),
            date_posted=posted_date,
            emails=emails,
            is_remote=is_remote,
            listing_type="remote" if is_remote else None,
            company_description=context["company_description"],
            company_logo=context["company_logo"],
        )

    def _build_location(
        self,
        *,
        detail_info: dict[str, Any],
        raw_job: dict[str, Any],
        country_text: str | None,
    ) -> Location | None:
        location_values: list[str] = []
        primary_location = self._safe_str(detail_info.get("location")) or self._safe_str(
            raw_job.get("locationsText")
        )
        if primary_location and primary_location.lower() != "2 locations":
            location_values.append(primary_location)

        additional_locations = detail_info.get("additionalLocations")
        if isinstance(additional_locations, list):
            for location_value in additional_locations:
                normalized = self._safe_str(location_value)
                if normalized:
                    location_values.append(normalized)

        cleaned_locations: list[str] = []
        for location_value in location_values:
            normalized = self._normalize_location_text(location_value)
            if normalized and normalized not in cleaned_locations:
                cleaned_locations.append(normalized)

        if not cleaned_locations and country_text:
            return Location(country=country_text)
        if not cleaned_locations:
            return None

        if len(cleaned_locations) == 1:
            location_text = cleaned_locations[0]
            parts = [part.strip() for part in location_text.split(",") if part.strip()]
            if len(parts) >= 2:
                city = parts[0]
                state = ", ".join(parts[1:])
                return Location(city=city, state=state, country=country_text)
            return Location(city=location_text, country=country_text)

        return Location(city=" / ".join(cleaned_locations), country=country_text)

    def _normalize_location_text(self, location_text: str | None) -> str | None:
        normalized = self._safe_str(location_text)
        if not normalized:
            return None

        match = WORKDAY_REGION_PREFIX_REGEX.match(normalized)
        if match:
            normalized = match.group("location").strip()
        normalized = WORKDAY_LOCATION_SUFFIX_REGEX.sub("", normalized).strip()
        return normalized or None

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

    def _parse_job_type(
        self,
        *,
        time_type: str | None,
        title: str | None,
    ) -> list[JobType] | None:
        parsed_types: list[JobType] = []

        normalized_time_type = (self._safe_str(time_type) or "").lower()
        if normalized_time_type == "full time":
            parsed_types.append(JobType.FULL_TIME)
        elif normalized_time_type == "part time":
            parsed_types.append(JobType.PART_TIME)

        normalized_title = (self._safe_str(title) or "").lower()
        if "intern" in normalized_title and JobType.INTERNSHIP not in parsed_types:
            parsed_types.append(JobType.INTERNSHIP)

        return parsed_types or None

    def _is_remote(
        self,
        detail_info: dict[str, Any],
        raw_job: dict[str, Any],
    ) -> bool | None:
        candidates: list[str | None] = [
            self._safe_str(detail_info.get("location")),
            self._safe_str(raw_job.get("locationsText")),
        ]

        additional_locations = detail_info.get("additionalLocations")
        if isinstance(additional_locations, list):
            candidates.extend(self._safe_str(value) for value in additional_locations)

        if any(
            candidate and WORKDAY_REMOTE_REGEX.search(candidate)
            for candidate in candidates
        ):
            return True
        return False if candidates else None

    def _parse_date(self, value: Any):
        text = self._safe_str(value)
        if not text:
            return None

        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            return None

    def _parse_relative_posted_date(self, value: Any):
        posted_text = self._safe_str(value)
        if not posted_text:
            return None

        lowered = posted_text.lower()
        today = datetime.now(timezone.utc).date()
        if "today" in lowered:
            return today
        if "yesterday" in lowered:
            return today - timedelta(days=1)

        match = WORKDAY_POSTED_DAYS_AGO_REGEX.search(posted_text)
        if not match:
            return None

        days = int(match.group("days"))
        return today - timedelta(days=days)

    def _extract_workday_value(
        self,
        html_text: str,
        pattern: re.Pattern[str],
    ) -> str | None:
        match = pattern.search(html_text)
        if not match:
            return None
        return self._safe_str(next(iter(match.groupdict().values())))

    def _get_meta_content(self, soup: BeautifulSoup, property_name: str) -> str | None:
        tag = soup.find("meta", property=property_name)
        if tag is None:
            return None
        return self._safe_str(tag.get("content"))

    def _normalize_url(self, base_url: str, value: Any) -> str | None:
        url_text = self._safe_str(value)
        if not url_text:
            return None
        return urljoin(base_url, url_text)

    def _extract_external_id(self, job_url: str | None) -> str | None:
        job_url_text = self._safe_str(job_url)
        if not job_url_text:
            return None
        parsed = urlparse(job_url_text)
        match = WORKDAY_EXTERNAL_ID_REGEX.search(parsed.path.rstrip("/"))
        if not match:
            return None
        return self._safe_str(match.group("external_id"))

    def _safe_html(self, value: Any) -> str | None:
        text = self._safe_str(value)
        if not text:
            return None
        return html.unescape(text)

    def _repair_mojibake(self, value: str | None) -> str | None:
        text = self._safe_str(value)
        if not text:
            return None

        if not any(marker in text for marker in ("â", "Ã", "ā\x80")):
            return text

        for source_encoding in ("cp1252", "latin-1"):
            try:
                repaired = text.encode(source_encoding).decode("utf-8")
            except UnicodeError:
                continue
            if repaired:
                return repaired

        return text

    def _first_list_value(self, value: Any) -> Any:
        if isinstance(value, list) and value:
            return value[0]
        return None

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

    def _safe_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None
