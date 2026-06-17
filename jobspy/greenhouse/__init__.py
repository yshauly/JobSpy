from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from jobspy.model import (
    Compensation,
    CompensationInterval,
    Country,
    DescriptionFormat,
    GreenhouseScrapeMode,
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
    currency_parser,
    extract_emails_from_text,
    extract_salary,
    markdown_converter,
    plain_converter,
)

log = create_logger("Greenhouse")

INERTIA_DATA_PAGE_REGEX = re.compile(
    r'data-page="(?P<data_page>.*?)"',
    re.S,
)
REMIX_CONTEXT_REGEX = re.compile(
    r"window\.__remixContext\s*=\s*(\{.*?\});\s*</script>",
    re.S,
)
JOBS_PATH = "/jobs"
INERTIA_COMPONENT = "job_search"
INERTIA_PARTIAL_DATA = "jobPosts,moreResultsAvailable,page"
HTML_ACCEPT_HEADER = "text/html, application/xhtml+xml"
GREENHOUSE_LOCATION_PRESETS = {
    "il": {
        "location_name": "Israel",
        "lat": 30.895128,
        "lon": 34.874702,
        "location_type": "country",
        "country_short_name": "IL",
    },
    "israel": {
        "location_name": "Israel",
        "lat": 30.895128,
        "lon": 34.874702,
        "location_type": "country",
        "country_short_name": "IL",
    },
    "ישראל": {
        "location_name": "Israel",
        "lat": 30.895128,
        "lon": 34.874702,
        "location_type": "country",
        "country_short_name": "IL",
    },
}


class Greenhouse(Scraper):
    base_url = "https://my.greenhouse.io"

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
        auth_cookies: dict[str, str] | None = None,
        xsrf_token: str | None = None,
    ):
        super().__init__(
            Site.GREENHOUSE,
            proxies=proxies,
            ca_cert=ca_cert,
            user_agent=user_agent,
        )
        self.auth_cookies = self._normalize_auth_cookies(auth_cookies)
        self.xsrf_token = self._safe_str(xsrf_token)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
            delay=3,
        )
        # Greenhouse rejects authenticated my.greenhouse.io requests that
        # advertise the generic requests default Accept: */*.
        self.session.headers["Accept"] = HTML_ACCEPT_HEADER
        if self.user_agent:
            self.session.headers["User-Agent"] = self.user_agent
        self.scraper_input = None
        self.inertia_version: str | None = None
        self.search_url: str | None = None
        self.seen_job_urls: set[str] = set()

    def _debug_enabled(self) -> bool:
        return bool(
            self.scraper_input
            and getattr(self.scraper_input, "greenhouse_debug_trace", False)
        )

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            log.info(f"[trace] {message}")

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.seen_job_urls.clear()

        if not self.auth_cookies:
            raise ValueError(
                "Greenhouse scrape requires greenhouse_auth_cookies with an "
                "authenticated my.greenhouse.io session"
            )

        search_params = self._resolve_search_params(scraper_input)
        self.search_url = self._build_search_url(search_params, page=None)
        self._apply_auth_cookies()
        self._bootstrap_session()

        fetch_all = (
            scraper_input.greenhouse_execution_mode
            == GreenhouseScrapeMode.UNTIL_LAST_PAGE
        )
        target_results = (
            None if fetch_all else scraper_input.results_wanted + scraper_input.offset
        )
        job_list: list[JobPost] = []
        requested_page: int | None = None
        request_count = 0

        self._debug(
            "Initialized Greenhouse search with "
            f"search_url={self.search_url!r}, target_results={target_results}, "
            f"execution_mode={scraper_input.greenhouse_execution_mode.value!r}, "
            f"offset={scraper_input.offset}, description_limit={scraper_input.description_limit}"
        )

        while fetch_all or len(job_list) < target_results:
            request_count += 1
            log.info(
                "search page: "
                + (str(request_count) if requested_page is None else str(requested_page))
            )
            page_payload = self._fetch_search_page(search_params, requested_page)
            props = page_payload.get("props", {})
            page_number = props.get("page")
            raw_jobs = props.get("jobPosts") or []
            more_results_available = bool(props.get("moreResultsAvailable"))
            log.info(
                f"page {page_number or 1}: jobs={len(raw_jobs)} more={more_results_available}"
            )
            self._debug(
                f"Greenhouse page response requested_page={requested_page!r} "
                f"page={page_number!r} jobs={len(raw_jobs)} "
                f"moreResultsAvailable={more_results_available}"
            )

            if not raw_jobs:
                log.info(f"found no jobs on page: {page_number or 1}")
                break

            for index, raw_job in enumerate(raw_jobs, start=1):
                job_post = self._process_job(raw_job)
                if job_post is None:
                    self._debug(
                        f"Skipped Greenhouse raw result {index}/{len(raw_jobs)} "
                        f"id={raw_job.get('id')!r}"
                    )
                    continue

                job_list.append(job_post)
                self._debug(
                    f"Accepted Greenhouse job id={job_post.id!r} "
                    f"title={job_post.title!r} job_url={job_post.job_url!r}"
                )
                if not fetch_all and len(job_list) >= target_results:
                    break

            if not fetch_all and len(job_list) >= target_results:
                break
            if not more_results_available:
                self._debug(
                    f"Stopping Greenhouse pagination after page={page_number!r} "
                    "because moreResultsAvailable is false"
                )
                break

            requested_page = 2 if requested_page is None else requested_page + 1

        if fetch_all:
            returned_jobs = job_list[scraper_input.offset :]
        else:
            returned_jobs = job_list[
                scraper_input.offset : scraper_input.offset + scraper_input.results_wanted
            ]
        self._debug(
            f"Greenhouse scrape complete with accumulated_jobs={len(job_list)} "
            f"and returned_jobs={len(returned_jobs)}"
        )
        return JobResponse(jobs=returned_jobs)

    def _resolve_search_params(self, scraper_input: ScraperInput) -> dict[str, Any]:
        location_name = self._safe_str(
            scraper_input.greenhouse_location_name or scraper_input.location
        )
        country_short_name = self._safe_str(scraper_input.greenhouse_country_short_name)
        location_type = self._safe_str(scraper_input.greenhouse_location_type)
        lat = scraper_input.greenhouse_lat
        lon = scraper_input.greenhouse_lon

        preset = self._resolve_location_preset(scraper_input, location_name)
        if preset:
            location_name = location_name or preset["location_name"]
            country_short_name = country_short_name or preset["country_short_name"]
            location_type = location_type or preset["location_type"]
            lat = lat if lat is not None else preset["lat"]
            lon = lon if lon is not None else preset["lon"]

        if (
            not location_name
            or lat is None
            or lon is None
            or not location_type
            or not country_short_name
        ):
            raise ValueError(
                "Greenhouse scrape requires location_name, lat, lon, "
                "location_type, and country_short_name. This first version "
                "auto-fills those values for Israel only."
            )

        date_posted = self._safe_str(scraper_input.greenhouse_date_posted) or "past_ten_days"
        resolved = {
            "location": location_name,
            "lat": lat,
            "lon": lon,
            "location_type": location_type,
            "country_short_name": country_short_name,
            "date_posted": date_posted,
        }
        self._debug(f"Resolved Greenhouse search params: {resolved}")
        return resolved

    def _resolve_location_preset(
        self,
        scraper_input: ScraperInput,
        location_name: str | None,
    ) -> dict[str, Any] | None:
        candidates: list[str] = []
        if location_name:
            candidates.append(location_name.lower())

        requested_country = getattr(scraper_input, "country", None)
        if requested_country == Country.ISRAEL:
            candidates.extend(["israel", "il"])
        elif isinstance(requested_country, str):
            candidates.append(requested_country.lower())

        for candidate in candidates:
            if candidate in GREENHOUSE_LOCATION_PRESETS:
                return GREENHOUSE_LOCATION_PRESETS[candidate]
        return None

    def _bootstrap_session(self) -> None:
        if not self.search_url:
            raise ValueError("Greenhouse search URL is not initialized")

        response = self.session.get(
            self.search_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        self._debug(
            f"Bootstrap response status={response.status_code} final_url={response.url!r} "
            f"cookies={sorted(self.session.cookies.get_dict().keys())}"
        )

        if "/users/sign_in" in response.url:
            raise ValueError(
                "Greenhouse auth cookies are invalid or expired; "
                "my.greenhouse.io redirected to sign-in"
            )

        page_data = self._extract_inertia_page_data(response.text)
        component = page_data.get("component")
        self.inertia_version = self._safe_str(page_data.get("version"))
        self.xsrf_token = self.xsrf_token or self._extract_xsrf_token()
        self._debug(
            f"Bootstrap page component={component!r} inertia_version={self.inertia_version!r} "
            f"xsrf_token_found={bool(self.xsrf_token)}"
        )

        if component != INERTIA_COMPONENT:
            raise ValueError(
                f"Greenhouse bootstrap returned component={component!r} instead of "
                f"{INERTIA_COMPONENT!r}; auth may be missing or the page structure changed"
            )
        if not self.inertia_version:
            raise ValueError("Greenhouse bootstrap did not expose an Inertia version")
        if not self.xsrf_token:
            raise ValueError(
                "Greenhouse scrape requires an XSRF token from MYGREENHOUSE-XSRF-TOKEN "
                "or XSRF-TOKEN"
            )

    def _fetch_search_page(
        self,
        search_params: dict[str, Any],
        page: int | None,
    ) -> dict[str, Any]:
        search_url = self._build_search_url(search_params, page)
        headers = self._build_inertia_headers()
        self._debug(
            f"Requesting Greenhouse API url={search_url!r} "
            f"with headers={{'x-inertia-version': {headers['x-inertia-version']!r}, "
            f"'x-csrf-token': {'set' if headers.get('x-csrf-token') else 'missing'}}}"
        )

        response = self.session.get(
            search_url,
            headers=headers,
            timeout=self.scraper_input.request_timeout,
            verify=False,
            allow_redirects=False,
        )
        if response.status_code == 409:
            self._debug(
                "Greenhouse API returned 409; refreshing bootstrap state and retrying once"
            )
            self._bootstrap_session()
            headers = self._build_inertia_headers()
            response = self.session.get(
                search_url,
                headers=headers,
                timeout=self.scraper_input.request_timeout,
                verify=False,
                allow_redirects=False,
            )

        redirect_location = response.headers.get("location")
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ValueError(
                "Greenhouse API redirected the search request to "
                f"{redirect_location!r}; auth cookies may be expired"
            )
        response.raise_for_status()
        self._debug(
            f"Greenhouse API response status={response.status_code} "
            f"x_inertia={response.headers.get('x-inertia')!r} "
            f"content_type={response.headers.get('content-type')!r}"
        )

        payload = response.json()
        component = payload.get("component")
        if component != INERTIA_COMPONENT:
            raise ValueError(
                f"Unexpected Greenhouse API component={component!r}; expected "
                f"{INERTIA_COMPONENT!r}"
            )
        return payload

    def _process_job(self, raw_job: dict[str, Any]) -> JobPost | None:
        summary_job_url = self._normalize_job_url(raw_job.get("publicUrl"))
        title = self._safe_str(raw_job.get("title"))
        if not title or not summary_job_url:
            return None
        if summary_job_url in self.seen_job_urls:
            self._debug(f"Skipping duplicate Greenhouse job_url={summary_job_url!r}")
            return None
        self.seen_job_urls.add(summary_job_url)

        detail_data = self._fetch_job_detail(summary_job_url) if self.claim_description_slot() else {}
        detail_job_url = self._normalize_job_url(detail_data.get("public_url"))
        job_url = detail_job_url or summary_job_url
        description_html = self._build_description_html(detail_data)
        description = self._convert_description(description_html)
        compensation = self._parse_compensation(
            detail_data.get("pay_ranges") or raw_job.get("payRanges")
        )
        listing_type = self._safe_str(raw_job.get("workType"))
        location = self._build_location(
            detail_data.get("job_post_location") or raw_job.get("locations")
        )
        date_posted = self._parse_date(
            detail_data.get("published_at") or raw_job.get("firstPublished")
        )
        apply_url = self._normalize_job_url(detail_data.get("redirect_to")) or job_url
        emails = extract_emails_from_text(description or "") or None
        company_url = self._build_company_url(job_url)

        return JobPost(
            id=(
                f"gh-{raw_job['id']}"
                if raw_job.get("id") is not None
                else self._build_id_from_url(job_url)
            ),
            title=title,
            company_name=self._safe_str(
                detail_data.get("company_name") or raw_job.get("companyName")
            ),
            job_url=job_url,
            apply_url=apply_url,
            job_url_direct=job_url,
            location=location,
            description=description,
            company_url=company_url,
            company_url_direct=company_url,
            job_type=self._parse_job_type(detail_data.get("employment")),
            compensation=compensation,
            date_posted=date_posted,
            emails=emails,
            is_remote=self._parse_is_remote(listing_type),
            listing_type=listing_type,
            company_logo=self._safe_str(raw_job.get("logoUrl")),
        )

    def _fetch_job_detail(self, job_url: str) -> dict[str, Any]:
        self._debug(f"Fetching Greenhouse job details from {job_url}")
        response = self.session.get(
            job_url,
            timeout=self.scraper_input.request_timeout,
            verify=False,
        )
        response.raise_for_status()
        self._debug(
            f"Greenhouse detail response status={response.status_code} "
            f"final_url={response.url!r} content_length={len(response.text)}"
        )

        job_post = self._extract_detail_job_post(response.text)
        if not job_post:
            self._debug(
                "Greenhouse detail page did not expose a supported job payload; "
                "continuing with search summary fields only"
            )
            return {}

        self._debug(
            "Greenhouse detail payload keys: "
            f"{sorted(job_post.keys())[:20]}"
        )
        return job_post

    def _build_inertia_headers(self) -> dict[str, str]:
        if not self.inertia_version:
            raise ValueError("Greenhouse Inertia version is not initialized")

        headers = {
            "accept": HTML_ACCEPT_HEADER,
            "x-inertia": "true",
            "x-inertia-version": self.inertia_version,
            "x-inertia-partial-component": INERTIA_COMPONENT,
            "x-inertia-partial-data": INERTIA_PARTIAL_DATA,
            "x-requested-with": "XMLHttpRequest",
        }
        if self.search_url:
            headers["referer"] = self.search_url
        if self.xsrf_token:
            headers["x-csrf-token"] = self.xsrf_token
        return headers

    def _build_search_url(
        self,
        search_params: dict[str, Any],
        page: int | None,
    ) -> str:
        params = {key: value for key, value in search_params.items() if value is not None}
        if page is not None:
            params["page"] = page
        query_string = urlencode(params, doseq=True)
        return f"{self.base_url}{JOBS_PATH}?{query_string}"

    def _extract_inertia_page_data(self, html_text: str) -> dict[str, Any]:
        match = INERTIA_DATA_PAGE_REGEX.search(html_text)
        if not match:
            raise ValueError("Greenhouse bootstrap page is missing the Inertia data-page payload")

        raw_data_page = html.unescape(match.group("data_page"))
        return json.loads(raw_data_page)

    def _extract_remix_context(self, html_text: str) -> dict[str, Any]:
        match = REMIX_CONTEXT_REGEX.search(html_text)
        if not match:
            raise ValueError("Greenhouse job page is missing window.__remixContext")
        return json.loads(match.group(1))

    def _extract_detail_job_post(self, html_text: str) -> dict[str, Any]:
        try:
            remix_context = self._extract_remix_context(html_text)
        except ValueError:
            remix_context = None

        if remix_context:
            job_post = (
                remix_context.get("state", {})
                .get("loaderData", {})
                .get("routes/$url_token_.jobs_.$job_post_id", {})
                .get("jobPost", {})
            )
            if isinstance(job_post, dict) and job_post:
                self._debug("Detected Greenhouse Remix detail payload")
                return job_post

        next_job_post = self._extract_next_job_post(html_text)
        if next_job_post:
            self._debug("Detected Greenhouse Next.js detail payload")
            return next_job_post

        return {}

    def _extract_next_job_post(self, html_text: str) -> dict[str, Any]:
        next_data_match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(?P<data>.*?)</script>',
            html_text,
            re.S,
        )
        if not next_data_match:
            return {}

        next_data = json.loads(next_data_match.group("data"))
        careers_data = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("careersData", {})
        )
        if not isinstance(careers_data, dict) or not careers_data:
            return {}

        return {
            "title": self._safe_str(careers_data.get("title")),
            "company_name": self._safe_str(careers_data.get("company_name")),
            "content": html.unescape(self._safe_str(careers_data.get("content")) or ""),
            "public_url": self._safe_str(careers_data.get("absolute_url")),
            "published_at": self._safe_str(careers_data.get("first_published")),
            "job_post_location": self._safe_str(
                (careers_data.get("location") or {}).get("name")
                if isinstance(careers_data.get("location"), dict)
                else None
            ),
            "employment": None,
            "pay_ranges": None,
            "redirect_to": None,
        }

    def _apply_auth_cookies(self) -> None:
        self.session.cookies.clear()
        for name, value in self.auth_cookies.items():
            self.session.cookies.set(name, value, domain="my.greenhouse.io", path="/")

    def _extract_xsrf_token(self) -> str | None:
        for cookie_name in ("MYGREENHOUSE-XSRF-TOKEN", "XSRF-TOKEN"):
            token = self._safe_str(
                self.auth_cookies.get(cookie_name) or self.session.cookies.get(cookie_name)
            )
            if token:
                return token
        return None

    def _normalize_auth_cookies(
        self,
        auth_cookies: dict[str, str] | None,
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        if not auth_cookies:
            return normalized

        for name, value in auth_cookies.items():
            normalized_name = self._safe_str(name)
            normalized_value = self._safe_str(value)
            if normalized_name and normalized_value:
                normalized[normalized_name] = normalized_value
        return normalized

    def _build_description_html(self, detail_data: dict[str, Any]) -> str | None:
        sections: list[str] = []
        for key in ("introduction", "content", "conclusion"):
            value = self._safe_str(detail_data.get(key))
            if value:
                sections.append(value)
        return "".join(sections) or None

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

    def _build_location(self, value: Any) -> Location | None:
        if isinstance(value, list):
            location_text = ", ".join(
                location_part
                for location_part in (self._safe_str(item) for item in value)
                if location_part
            )
        else:
            location_text = self._safe_str(value)

        if not location_text:
            return None

        parts = [part.strip() for part in location_text.split(",")]
        if len(parts) == 2:
            return Location(city=parts[0], state=parts[1])
        return Location(country=location_text)

    def _parse_compensation(self, value: Any) -> Compensation | None:
        if isinstance(value, str):
            interval, min_amount, max_amount, currency = extract_salary(value)
            compensation_interval = (
                CompensationInterval(interval) if interval else None
            )
            if min_amount is None or max_amount is None:
                return None
            return Compensation(
                interval=compensation_interval,
                min_amount=min_amount,
                max_amount=max_amount,
                currency=currency,
            )

        if not isinstance(value, list):
            return None

        mins: list[float] = []
        maxs: list[float] = []
        currencies: set[str] = set()
        for pay_range in value:
            if not isinstance(pay_range, dict):
                continue
            min_text = self._safe_str(pay_range.get("min"))
            max_text = self._safe_str(pay_range.get("max"))
            currency = self._safe_str(pay_range.get("currency_type"))
            if min_text and max_text:
                mins.append(currency_parser(min_text))
                maxs.append(currency_parser(max_text))
            if currency:
                currencies.add(currency)

        if not mins or not maxs:
            return None

        return Compensation(
            interval=CompensationInterval.YEARLY,
            min_amount=min(mins),
            max_amount=max(maxs),
            currency=(currencies.pop() if len(currencies) == 1 else "USD"),
        )

    def _parse_job_type(self, employment: Any) -> list[JobType] | None:
        employment_text = (self._safe_str(employment) or "").lower()
        if not employment_text or employment_text == "hidden":
            return None

        mapping = {
            "full-time": JobType.FULL_TIME,
            "full time": JobType.FULL_TIME,
            "part-time": JobType.PART_TIME,
            "part time": JobType.PART_TIME,
            "contract": JobType.CONTRACT,
            "internship": JobType.INTERNSHIP,
        }
        job_type = mapping.get(employment_text)
        return [job_type] if job_type else None

    def _parse_is_remote(self, work_type: str | None) -> bool | None:
        normalized = (self._safe_str(work_type) or "").lower()
        if normalized == "remote":
            return True
        if normalized in {"in_person", "hybrid"}:
            return False
        return None

    def _parse_date(self, value: Any):
        date_text = self._safe_str(value)
        if not date_text:
            return None

        normalized = date_text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            return None

    def _normalize_job_url(self, job_url: Any) -> str | None:
        job_url_text = self._safe_str(job_url)
        if not job_url_text:
            return None

        parsed = urlparse(job_url_text)
        query_items = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() != "gh_src"
        ]
        normalized_query = urlencode(query_items, doseq=True)
        return urlunparse(parsed._replace(query=normalized_query, fragment=""))

    def _build_company_url(self, job_url: str | None) -> str | None:
        normalized_job_url = self._normalize_job_url(job_url)
        if not normalized_job_url:
            return None

        parsed = urlparse(normalized_job_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"

    def _build_id_from_url(self, job_url: str | None) -> str | None:
        if not job_url:
            return None
        match = re.search(r"(?:gh_jid=|/jobs/)(?P<job_id>\d+)", job_url)
        if not match:
            return None
        return f"gh-{match.group('job_id')}"

    def _safe_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None
