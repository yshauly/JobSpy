from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from jobspy.model import (
    Country,
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

log = create_logger("Comeet")

COMPANY_DATA_VARIABLE = "COMPANY_DATA"
COMPANY_POSITIONS_DATA_VARIABLE = "COMPANY_POSITIONS_DATA"
POSITION_DATA_VARIABLE = "POSITION_DATA"


class Comeet(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.COMEET,
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
            and getattr(self.scraper_input, "comeet_debug_trace", False)
        )

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            log.info(f"[trace] {message}")

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        company_url = (scraper_input.comeet_company_url or "").strip()
        if not company_url:
            raise ValueError("Comeet scrape requires scraper_input.comeet_company_url")

        log.info(f"Fetching Comeet company page: {company_url}")
        response = self.session.get(
            company_url,
            timeout=scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        self._debug(
            f"Fetched company page status={response.status_code} "
            f"final_url={response.url!r} content_length={len(response.text)}"
        )

        company_data = self._extract_embedded_json(
            response.text,
            COMPANY_DATA_VARIABLE,
        )
        positions_data = self._extract_embedded_json(
            response.text,
            COMPANY_POSITIONS_DATA_VARIABLE,
        )
        if not positions_data:
            single_position = self._extract_embedded_json(
                response.text,
                POSITION_DATA_VARIABLE,
            )
            if isinstance(single_position, dict):
                positions_data = [single_position]

        if not isinstance(company_data, dict):
            company_data = {}
        if not isinstance(positions_data, list):
            positions_data = []

        requested_country_aliases = self._requested_country_aliases()
        if requested_country_aliases:
            original_count = len(positions_data)
            positions_data = [
                position_data
                for position_data in positions_data
                if isinstance(position_data, dict)
                and self._matches_requested_country(
                    position_data,
                    requested_country_aliases,
                )
            ]
            self._debug(
                "Applied country filter to positions: "
                f"aliases={sorted(requested_country_aliases)} "
                f"kept={len(positions_data)}/{original_count}"
            )

        self._debug(
            "Embedded data extraction summary: "
            f"company_keys={sorted(company_data.keys())[:12]}, "
            f"positions_found={len(positions_data)}"
        )

        job_posts: list[JobPost] = []
        seen_job_urls: set[str] = set()
        total_positions = len(positions_data)
        for index, position_data in enumerate(positions_data, start=1):
            if not isinstance(position_data, dict):
                self._debug(f"Skipping non-dict position at index={index}")
                continue

            job_post = self._build_job_post(position_data, company_data)
            if not job_post:
                self._debug(
                    f"Skipping position index={index} because required fields were missing"
                )
                continue
            if job_post.job_url in seen_job_urls:
                self._debug(
                    f"Skipping duplicate position index={index} job_url={job_post.job_url}"
                )
                continue

            seen_job_urls.add(job_post.job_url)
            job_posts.append(job_post)
            self._debug(
                f"Accepted position {index}/{total_positions}: "
                f"title={job_post.title!r} job_url={job_post.job_url!r}"
            )

        log.info(
            f"Comeet scrape finished for {company_url} with {len(job_posts)} job(s)"
        )

        start = scraper_input.offset or 0
        end = start + scraper_input.results_wanted if scraper_input.results_wanted else None
        return JobResponse(jobs=job_posts[start:end])

    def _extract_embedded_json(self, html: str, variable_name: str) -> Any:
        pattern = re.compile(
            rf"{re.escape(variable_name)}\s*=\s*(.*?);\s*(?:\n|\r)",
            re.S,
        )
        match = pattern.search(html)
        if not match:
            self._debug(f"Embedded variable {variable_name} was not found")
            return None

        raw_value = match.group(1).strip()
        self._debug(
            f"Embedded variable {variable_name} found with prefix="
            f"{raw_value[:160]!r}"
        )
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as exc:
            self._debug(f"Failed to parse {variable_name} JSON: {exc}")
            return None

    def _build_job_post(
        self,
        position_data: dict[str, Any],
        company_data: dict[str, Any],
    ) -> JobPost | None:
        title = self._safe_str(position_data.get("name"))
        job_url = self._safe_str(
            position_data.get("url_comeet_hosted_page")
            or position_data.get("url_recruit_hosted_page")
        )
        if not title or not job_url:
            return None

        company_name = self._safe_str(
            position_data.get("company_name") or company_data.get("name")
        )
        description_html = self._build_description_html(position_data)
        description = self._convert_description(description_html)
        explicit_email = self._safe_str(position_data.get("email"))
        emails = []
        if explicit_email:
            emails.append(explicit_email)
        extracted_emails = extract_emails_from_text(description or "") or []
        for email in extracted_emails:
            if email not in emails:
                emails.append(email)

        location = self._build_location(position_data.get("location"))
        is_remote = self._is_remote(position_data)
        employment_type = self._safe_str(position_data.get("employment_type"))
        experience_level = self._safe_str(position_data.get("experience_level"))
        company_logo = self._extract_company_logo(company_data)
        company_url = self._normalize_company_website(company_data.get("website"))
        job_type = self._parse_job_type(employment_type)
        company_description = self._convert_company_description(company_data)
        date_posted = self._parse_date(position_data.get("time_updated"))

        return JobPost(
            id=self._safe_str(position_data.get("uid")),
            title=title,
            company_name=company_name,
            job_url=job_url,
            apply_url=job_url,
            job_url_direct=self._safe_str(position_data.get("url_active_page")),
            location=location,
            description=description,
            company_url=company_url,
            company_url_direct=company_url,
            job_type=job_type,
            date_posted=date_posted,
            emails=emails or None,
            is_remote=is_remote,
            listing_type=self._safe_str(position_data.get("workplace_type")),
            job_level=experience_level,
            company_description=company_description,
            company_logo=company_logo,
        )

    def _build_description_html(self, position_data: dict[str, Any]) -> str | None:
        details = (
            (position_data.get("custom_fields") or {}).get("details") or []
        )
        sections: list[str] = []
        for detail in details:
            if not isinstance(detail, dict):
                continue
            name = self._safe_str(detail.get("name"))
            value = self._safe_str(detail.get("value"))
            if not value:
                continue
            if name:
                sections.append(f"<h3>{name}</h3>{value}")
            else:
                sections.append(value)

        if sections:
            return "".join(sections)
        return None

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

    def _convert_company_description(self, company_data: dict[str, Any]) -> str | None:
        company_description_html = self._safe_str(company_data.get("description"))
        return self._convert_description(company_description_html)

    def _build_location(self, location_data: Any) -> Location | None:
        if not isinstance(location_data, dict):
            return None

        return Location(
            city=self._safe_str(location_data.get("city")),
            state=self._safe_str(location_data.get("state")),
            country=self._normalize_country(location_data.get("country")),
        )

    def _requested_country_aliases(self) -> set[str]:
        requested_country = getattr(self.scraper_input, "country", None)
        if requested_country is None:
            return set()
        if requested_country == Country.WORLDWIDE:
            return set()

        aliases: set[str] = set()
        if isinstance(requested_country, Country):
            aliases.update(
                alias.strip().lower()
                for alias in requested_country.value[0].split(",")
                if alias.strip()
            )
            try:
                _, api_country_code = requested_country.indeed_domain_value
            except Exception:
                api_country_code = None
            if api_country_code:
                aliases.add(api_country_code.lower())
        else:
            raw_country = self._safe_str(requested_country)
            if raw_country:
                aliases.add(raw_country.lower())

        return aliases

    def _matches_requested_country(
        self,
        position_data: dict[str, Any],
        requested_country_aliases: set[str],
    ) -> bool:
        location_data = position_data.get("location")
        candidate_values: list[Any] = []
        if isinstance(location_data, dict):
            candidate_values.extend(
                [
                    location_data.get("country"),
                    location_data.get("name"),
                    location_data.get("city"),
                    location_data.get("state"),
                ]
            )

        for candidate_value in candidate_values:
            candidate_text = self._safe_str(candidate_value)
            if not candidate_text:
                continue
            normalized_candidate = candidate_text.lower()
            for alias in requested_country_aliases:
                if re.search(
                    rf"(?<![a-z]){re.escape(alias)}(?![a-z])",
                    normalized_candidate,
                ):
                    return True
        return False

    def _normalize_country(self, country_value: Any) -> str | None:
        country = self._safe_str(country_value)
        if not country:
            return None

        country_map = {
            "IL": "Israel",
            "US": "USA",
            "UK": "UK",
        }
        return country_map.get(country.upper(), country)

    def _parse_job_type(self, employment_type: str | None) -> list[JobType] | None:
        normalized = self._safe_str(employment_type)
        if not normalized:
            return None

        normalized = normalized.lower().replace(" ", "").replace("-", "")
        mapping = {
            "fulltime": JobType.FULL_TIME,
            "parttime": JobType.PART_TIME,
            "contract": JobType.CONTRACT,
            "internship": JobType.INTERNSHIP,
        }
        job_type = mapping.get(normalized)
        return [job_type] if job_type else None

    def _is_remote(self, position_data: dict[str, Any]) -> bool | None:
        location_data = position_data.get("location")
        if isinstance(location_data, dict) and location_data.get("is_remote") is True:
            return True

        workplace_type = (
            (self._safe_str(position_data.get("workplace_type")) or "")
            .lower()
            .replace("-", "")
            .replace(" ", "")
        )
        if workplace_type == "remote":
            return True
        if workplace_type in {"onsite", "hybrid"}:
            return False
        return None

    def _extract_company_logo(self, company_data: dict[str, Any]) -> str | None:
        logos = company_data.get("logos")
        if isinstance(logos, dict):
            for key in ("medium", "small", "original"):
                logo_data = logos.get(key)
                if isinstance(logo_data, dict):
                    logo_url = self._safe_str(logo_data.get("url"))
                    if logo_url:
                        return logo_url
        return self._safe_str(company_data.get("company_picture_url"))

    def _normalize_company_website(self, website: Any) -> str | None:
        website_text = self._safe_str(website)
        if not website_text:
            return None
        if website_text.startswith(("http://", "https://")):
            normalized = website_text
        else:
            normalized = f"https://{website_text}"

        parsed = urlparse(normalized)
        if parsed.netloc in {"app.comeet.co", "app.comeet.com"}:
            return None
        return normalized

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
