from __future__ import annotations

import json
from datetime import datetime, timezone
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
from jobspy.util import (
    create_logger,
    create_session,
    extract_emails_from_text,
    markdown_converter,
    plain_converter,
)

log = create_logger("Eightfold")

COUNTRY_CODE_MAP = {
    "CA": Country.CANADA,
    "GB": Country.UK,
    "IL": Country.ISRAEL,
    "IN": Country.INDIA,
    "UK": Country.UK,
    "US": Country.USA,
}
BRANDING_ITEM_TYPE = "BRANDING"


class Eightfold(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.EIGHTFOLD,
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
            and getattr(self.scraper_input, "eightfold_debug_trace", False)
        )

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            log.info(f"[trace] {message}")

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        company_url = self._safe_str(scraper_input.eightfold_company_url)
        if not company_url:
            raise ValueError(
                "Eightfold scrape requires scraper_input.eightfold_company_url"
            )

        context = self._bootstrap_company_context(company_url)
        requested_start, search_params, detail_language = self._build_search_request(
            company_url,
            context,
            scraper_input,
        )
        base_url = context["base_url"]

        log.info(f"Fetching Eightfold jobs from {company_url}")
        raw_page = self._fetch_search_page(base_url, search_params)
        total_count = self._safe_int(raw_page.get("count")) or 0
        raw_positions = list(raw_page.get("positions") or [])
        target_count = self._resolve_target_count(
            total_count=total_count,
            requested_start=requested_start,
            results_wanted=scraper_input.results_wanted,
        )
        self._debug(
            "Initialized Eightfold search with "
            f"domain={context['domain']!r}, company_name={context['company_name']!r}, "
            f"requested_start={requested_start}, target_count={target_count}, "
            f"location={search_params.get('location')!r}"
        )

        current_start = requested_start + len(raw_positions)
        while len(raw_positions) < target_count and current_start < total_count:
            next_page_params = dict(search_params)
            next_page_params["start"] = current_start
            next_page = self._fetch_search_page(base_url, next_page_params)
            page_positions = list(next_page.get("positions") or [])
            if not page_positions:
                self._debug(
                    f"Stopping pagination at start={current_start} because the page was empty"
                )
                break
            raw_positions.extend(page_positions)
            current_start += len(page_positions)

        job_posts: list[JobPost] = []
        for raw_position in raw_positions[:target_count]:
            if not isinstance(raw_position, dict):
                continue

            detail_data = None
            if self.claim_description_slot():
                detail_data = self._fetch_position_details(
                    base_url,
                    context["domain"],
                    raw_position,
                    queried_location=search_params.get("location"),
                    language=detail_language,
                )

            job_post = self._build_job_post(
                raw_position,
                detail_data=detail_data,
                context=context,
            )
            if job_post:
                job_posts.append(job_post)

        self._debug(
            f"Eightfold scrape finished with total_count={total_count} "
            f"and returned_jobs={len(job_posts)}"
        )
        return JobResponse(jobs=job_posts)

    def _bootstrap_company_context(self, company_url: str) -> dict[str, str | None]:
        response = self.session.get(
            company_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()

        resolved_url = self._safe_str(getattr(response, "url", None)) or company_url
        parsed = urlparse(resolved_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        soup = BeautifulSoup(response.text, "html.parser")
        context: dict[str, str | None] = {
            "base_url": base_url,
            "domain": None,
            "company_name": None,
            "company_url": None,
            "company_logo": None,
        }

        page_title = self._safe_str(soup.title.get_text()) if soup.title else None
        if page_title and page_title.lower().startswith("careers at "):
            context["company_name"] = page_title.removeprefix("Careers at ").strip()

        for payload in self._extract_code_payloads(soup):
            context["domain"] = context["domain"] or self._safe_str(payload.get("domain"))

            branding = self._extract_nav_branding(payload)
            for key, value in branding.items():
                if key in context and not context[key]:
                    context[key] = value

            config_branding = self._extract_config_branding(payload)
            for key, value in config_branding.items():
                if key in context and not context[key]:
                    context[key] = value

        context["domain"] = context["domain"] or self._derive_domain_from_url(company_url)
        context["company_name"] = context["company_name"] or self._humanize_domain_name(
            context["domain"] or parsed.netloc
        )
        context["company_url"] = context["company_url"] or resolved_url.split("?", 1)[0]
        self._debug(
            "Bootstrapped Eightfold context: "
            f"{json.dumps(context, ensure_ascii=False, default=str)}"
        )
        return context

    def _build_search_request(
        self,
        company_url: str,
        context: dict[str, str | None],
        scraper_input: ScraperInput,
    ) -> tuple[int, dict[str, Any], str]:
        parsed = urlparse(company_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        base_start = self._safe_int((query_params.get("start") or ["0"])[0]) or 0
        requested_start = base_start + max(scraper_input.offset, 0)
        location = self._safe_str(scraper_input.location)
        if location is None:
            location = self._safe_str((query_params.get("location") or [None])[0])
        if location is None:
            location = self._safe_str((query_params.get("lc") or [None])[0]) or ""

        query = self._safe_str(scraper_input.search_term)
        if query is None:
            query = self._safe_str((query_params.get("query") or [None])[0]) or ""

        params: dict[str, Any] = {
            "domain": context["domain"] or self._derive_domain_from_url(company_url),
            "query": query,
            "location": location,
            "start": requested_start,
        }
        sort_by = self._safe_str((query_params.get("sort_by") or [None])[0])
        if sort_by:
            params["sort_by"] = sort_by

        if scraper_input.is_remote:
            params["filter_include_remote"] = "1"

        for key, values in query_params.items():
            if key.startswith("filter_") and values:
                params[key] = values if len(values) > 1 else values[0]

        language = self._safe_str((query_params.get("hl") or [None])[0]) or "en"
        return requested_start, params, language

    def _fetch_search_page(
        self,
        base_url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.session.get(
            f"{base_url}/api/pcsx/search",
            params=params,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        self._debug(
            f"Fetched Eightfold page start={params.get('start')} "
            f"count={data.get('count')} positions={len(data.get('positions') or [])}"
        )
        return data

    def _fetch_position_details(
        self,
        base_url: str,
        domain: str | None,
        raw_position: dict[str, Any],
        *,
        queried_location: str | None,
        language: str,
    ) -> dict[str, Any] | None:
        position_id = self._safe_str(raw_position.get("id"))
        if not position_id or not domain:
            return None

        params = {
            "position_id": position_id,
            "domain": domain,
            "hl": language,
        }
        if queried_location:
            params["queried_location"] = queried_location

        response = self.session.get(
            f"{base_url}/api/pcsx/position_details",
            params=params,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        self._debug(
            f"Fetched position details for id={position_id} "
            f"has_description={bool(self._safe_str((data or {}).get('jobDescription')))}"
        )
        return data if isinstance(data, dict) else None

    def _build_job_post(
        self,
        raw_position: dict[str, Any],
        *,
        detail_data: dict[str, Any] | None,
        context: dict[str, str | None],
    ) -> JobPost | None:
        title = self._safe_str(raw_position.get("name")) or self._safe_str(
            (detail_data or {}).get("name")
        )
        position_path = self._safe_str(
            (detail_data or {}).get("publicUrl")
            or (detail_data or {}).get("positionUrl")
            or raw_position.get("positionUrl")
        )
        if not title or not position_path:
            return None

        job_url = (
            position_path
            if position_path.startswith("http")
            else urljoin(context["base_url"] or "", position_path)
        )
        description_html = self._safe_str((detail_data or {}).get("jobDescription"))
        description = self._convert_description(description_html)
        work_location_option = self._safe_str(
            raw_position.get("workLocationOption")
            or (detail_data or {}).get("workLocationOption")
        )

        return JobPost(
            id=self._safe_str(raw_position.get("id"))
            or self._safe_str((detail_data or {}).get("id")),
            title=title,
            company_name=context["company_name"],
            job_url=job_url,
            apply_url=job_url,
            location=self._build_location(
                raw_position.get("standardizedLocations"),
                raw_position.get("locations"),
                (detail_data or {}).get("location"),
            ),
            description=description,
            company_url=context["company_url"],
            company_url_direct=context["company_url"],
            date_posted=self._parse_timestamp_to_date(
                raw_position.get("postedTs") or (detail_data or {}).get("postedTs")
            ),
            emails=extract_emails_from_text(description) if description else None,
            is_remote=work_location_option == "remote",
            listing_type=work_location_option,
            company_logo=context["company_logo"],
        )

    def _build_location(
        self,
        standardized_locations: Any,
        raw_locations: Any,
        detail_location: Any,
    ) -> Location | None:
        standardized = self._first_text(standardized_locations)
        if standardized:
            parts = [part.strip() for part in standardized.split(",") if part.strip()]
            if len(parts) >= 3:
                return Location(
                    city=", ".join(parts[:-2]) or None,
                    state=parts[-2],
                    country=self._parse_country(parts[-1]),
                )
            if len(parts) == 2:
                return Location(
                    city=parts[0],
                    country=self._parse_country(parts[1]),
                )

        raw_location = self._first_text(raw_locations) or self._safe_str(detail_location)
        if not raw_location:
            return None

        if "-" in raw_location:
            country_text, _, remainder = raw_location.partition("-")
            city_text = remainder.split("(")[0].strip() or None
            return Location(
                city=city_text,
                country=self._parse_country(country_text),
            )

        return Location(country=self._parse_country(raw_location))

    def _resolve_target_count(
        self,
        *,
        total_count: int,
        requested_start: int,
        results_wanted: int,
    ) -> int:
        remaining = max(total_count - requested_start, 0)
        if results_wanted is None or results_wanted <= 0:
            return remaining
        return min(results_wanted, remaining)

    def _convert_description(self, description_html: str | None) -> str | None:
        if not description_html:
            return None

        description_format = self.scraper_input.description_format
        if description_format == DescriptionFormat.HTML:
            return description_html.strip()
        if description_format == DescriptionFormat.PLAIN:
            return plain_converter(description_html)
        return markdown_converter(description_html)

    def _extract_code_payloads(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for code_tag in soup.find_all("code"):
            raw_text = code_tag.get_text(strip=True)
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def _extract_nav_branding(self, payload: dict[str, Any]) -> dict[str, str | None]:
        navbar_data = payload.get("navbarData") or {}
        for view in ("desktop", "mobile"):
            items = (navbar_data.get(view) or {}).get("nav_left_items") or []
            for item in items:
                if not isinstance(item, dict) or item.get("type") != BRANDING_ITEM_TYPE:
                    continue
                return {
                    "company_name": self._safe_str(item.get("company_name")),
                    "company_url": self._safe_str(item.get("product_homepage_url")),
                    "company_logo": self._safe_str(item.get("company_logo_url")),
                }
        return {}

    def _extract_config_branding(
        self, payload: dict[str, Any]
    ) -> dict[str, str | None]:
        branding = (((payload.get("configs") or {}).get("pcsxConfig") or {}).get("branding") or {})
        return {
            "company_logo": self._safe_str(branding.get("companyLogo")),
        }

    def _derive_domain_from_url(self, company_url: str) -> str | None:
        host = (urlparse(company_url).hostname or "").strip().lower()
        if not host:
            return None
        host_parts = host.split(".")
        if len(host_parts) > 2 and host_parts[0] in {"apply", "career", "careers", "jobs"}:
            return ".".join(host_parts[1:])
        return host

    def _humanize_domain_name(self, domain: str) -> str | None:
        label = (domain or "").split(".", 1)[0].replace("-", " ").strip()
        return label.title() or None

    def _parse_country(self, value: Any) -> Country | str | None:
        text = self._safe_str(value)
        if not text:
            return None

        mapped_country = COUNTRY_CODE_MAP.get(text.upper())
        if mapped_country:
            return mapped_country

        try:
            return Country.from_string(text)
        except ValueError:
            return text

    def _parse_timestamp_to_date(self, value: Any):
        timestamp = self._safe_int(value)
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date()

    def _first_text(self, value: Any) -> str | None:
        if isinstance(value, list):
            for item in value:
                text = self._safe_str(item)
                if text:
                    return text
            return None
        return self._safe_str(value)

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
