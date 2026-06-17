from __future__ import annotations

import json
import math
import random
import time
from html import unescape
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse, unquote, urlencode

import regex as re
from bs4 import BeautifulSoup
from bs4.element import Tag

from jobspy.exception import LinkedInException
from jobspy.jobs_table import LinkedInJobsTableLookup
from jobspy.linkedin.constant import headers
from jobspy.linkedin.util import (
    is_job_remote,
    job_type_code,
    parse_job_type,
    parse_job_level,
    parse_company_industry
)
from jobspy.model import (
    JobPost,
    Location,
    JobResponse,
    Country,
    Compensation,
    DescriptionFormat,
    LinkedInScrapeMode,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    extract_emails_from_text,
    currency_parser,
    markdown_converter,
    plain_converter,
    create_session,
    remove_attributes,
    create_logger,
)

log = create_logger("LinkedIn")


class LinkedIn(Scraper):
    base_url = "https://www.linkedin.com"
    guest_search_path = "/jobs-guest/jobs/api/seeMoreJobPostings/search"
    authenticated_search_path = "/jobs/search/"
    delay = 1.5
    band_delay = 1.5
    jobs_per_page = 25
    search_page_retry_attempts = 3
    transient_status_codes = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
        auth_cookies: dict[str, str] | None = None,
    ):
        """
        Initializes LinkedInScraper with the LinkedIn job search url
        """
        super().__init__(
            Site.LINKEDIN,
            proxies=proxies,
            ca_cert=ca_cert,
            user_agent=user_agent,
        )
        self.auth_cookies = self._normalize_auth_cookies(auth_cookies)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
            delay=5,
            clear_cookies=not bool(self.auth_cookies),
        )
        self.session.headers.update(headers)
        if self.user_agent:
            self.session.headers["User-Agent"] = self.user_agent
        self._apply_auth_cookies()
        self.scraper_input = None
        self.country = "worldwide"
        self.job_url_direct_regex = re.compile(r'(?<=\?url=)[^"]+')
        self.linkedin_job_id_regex = re.compile(
            r"/jobs/view/(?:[^/?#]+-)?(?P<job_id>\d+)(?:/|$)"
        )
        self.applications_count_regex = re.compile(
            r"(?i)^(?P<count>\d[\d,]*)\s+applicants?\s*$"
        )
        self.clicked_apply_count_regex = re.compile(
            r"(?i)\b(?P<count>\d[\d,]*)\s+(?:people|person|members?)\s+clicked\s+apply\b"
        )
        self.jobs_table_lookup = None
        self._jobs_table_lookup_failed = False
        self._guest_canonical_session = None

    def inspect_job(self, job_url: str) -> dict[str, object]:
        normalized_job_url = self._normalize_linkedin_job_url(job_url)
        job_id = self._extract_job_id(normalized_job_url)
        if not normalized_job_url or not job_id:
            raise LinkedInException(f"Invalid LinkedIn job URL: {job_url}")

        if self.scraper_input is None:
            self.scraper_input = ScraperInput(
                site_type=[Site.LINKEDIN],
                country=Country.USA,
                description_format=DescriptionFormat.PLAIN,
                linkedin_fetch_description=True,
                linkedin_execution_mode=LinkedInScrapeMode.INSPECT_SINGLE_JOB,
            )

        response = self.session.get(normalized_job_url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        canonical_job_url = self._resolve_job_url(
            job_id,
            soup,
            response.url,
            response.text,
        )
        applicants_caption = soup.find(
            "figcaption",
            class_=lambda value: self._class_contains(value, "num-applicants__caption"),
        )
        session_redirect_values = []
        for session_redirect in soup.find_all("input", attrs={"name": "session_redirect"}):
            value = session_redirect.get("value")
            if not value:
                continue
            value = unescape(value.strip())
            if value and value not in session_redirect_values:
                session_redirect_values.append(value)

        apply_button = soup.find(
            attrs={
                "data-modal": lambda value: value
                in {"job-details-topcard-apply-modal", "job-details-subnav-apply-modal"}
                if value
                else False
            }
        )
        description = None
        if div_content := soup.find(
            "div", class_=lambda value: value and "show-more-less-html__markup" in value
        ):
            description = plain_converter(
                remove_attributes(div_content).prettify(formatter="html")
            )

        raw_apply_url_code = None
        if apply_url_code := soup.find("code", id="applyUrl"):
            raw_apply_url_code = apply_url_code.decode_contents().strip()
        json_ld_job_posting = self._parse_job_posting_json_ld(soup)
        hidden_code_values = self._extract_hidden_code_values(soup)
        logged_in_offsite_apply_url = self._parse_logged_in_offsite_apply_url(
            response.text
        )
        logged_in_easy_apply_url = self._parse_logged_in_easy_apply_url(response.text)
        clicked_apply_text = self._parse_clicked_apply_text(soup, response.text)
        page_title = soup.title.get_text(" ", strip=True) if soup.title else None

        return {
            "input_job_url": job_url,
            "normalized_job_url": normalized_job_url,
            "job_id": job_id,
            "requested_url": normalized_job_url,
            "response_url": self._normalize_linkedin_job_url(response.url),
            "status_code": response.status_code,
            "signup_redirected": "linkedin.com/signup" in response.url,
            "auth": {
                "enabled": bool(self.auth_cookies),
                "cookie_names": sorted(self.auth_cookies.keys()),
            },
            "extracted": {
                "job_url": canonical_job_url,
                "apply_url": self._parse_apply_url(soup, response.url, response.text),
                "job_url_direct": self._parse_job_url_direct(soup, response.text),
                "applications_count": self._parse_applications_count(
                    soup, response.text
                ),
                "job_level": parse_job_level(soup),
                "company_industry": parse_company_industry(soup),
                "job_type": [
                    job_type.value[0] for job_type in parse_job_type(soup) or []
                ],
                "job_function": (
                    job_function_span.text.strip()
                    if (
                        h3_tag := soup.find(
                            "h3", text=lambda text: text and "Job function" in text.strip()
                        )
                    )
                    and (
                        job_function_span := h3_tag.find_next(
                            "span", class_="description__job-criteria-text"
                        )
                    )
                    else None
                ),
            },
            "signals": {
                "page_title": page_title,
                "page_variant": self._detect_page_variant(soup, response.text),
                "is_offsite_apply": self._is_offsite_apply(soup),
                "lnkd_url": (
                    meta.get("content")
                    if (meta := soup.find("meta", attrs={"property": "lnkd:url"}))
                    else None
                ),
                "og_url": (
                    meta.get("content")
                    if (meta := soup.find("meta", attrs={"property": "og:url"}))
                    else None
                ),
                "canonical_url": (
                    link.get("href")
                    if (link := soup.find("link", attrs={"rel": "canonical"}))
                    else None
                ),
                "meta_values": self._extract_meta_values(soup),
                "session_redirect_values": session_redirect_values,
                "num_applicants_caption": (
                    applicants_caption.get_text(" ", strip=True)
                    if applicants_caption
                    else None
                ),
                "clicked_apply_text": clicked_apply_text,
                "raw_apply_url_code": raw_apply_url_code,
                "json_ld_job_posting": json_ld_job_posting,
                "json_ld_summary": self._build_job_posting_summary(json_ld_job_posting),
                "hidden_code_values": hidden_code_values,
                "logged_in_offsite_apply_url": logged_in_offsite_apply_url,
                "logged_in_easy_apply_url": logged_in_easy_apply_url,
                "apply_button_tag": apply_button.name if apply_button else None,
                "apply_button_text": (
                    apply_button.get_text(" ", strip=True) if apply_button else None
                ),
                "apply_button_classes": (
                    apply_button.get("class") if apply_button else None
                ),
                "company_linkedin_url": (
                    company_link.get("href")
                    if (
                        company_link := soup.find(
                            "a",
                            class_=lambda value: self._class_contains(
                                value, "topcard__org-name-link"
                            ),
                        )
                    )
                    else None
                ),
                "company_links": [
                    link.get("href")
                    for link in soup.find_all(
                        "a",
                        href=lambda href: href and "/company/" in href,
                    )
                ],
                "description_urls": sorted(
                    set(
                        re.findall(
                            r"https?://[^\s<>\"]+",
                            description or "",
                        )
                    )
                ),
                "description_length": len(description) if description else 0,
                "description_preview": (
                    description[:500] if description else None
                ),
            },
        }

    def _get_seconds_old_filter(self, scraper_input: ScraperInput) -> int | None:
        if scraper_input.linkedin_execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE:
            if scraper_input.num_of_min is None:
                raise LinkedInException(
                    "LinkedIn until-last-page mode requires num_of_min"
                )
            if scraper_input.num_of_min <= 0:
                raise LinkedInException(
                    "LinkedIn num_of_min must be greater than 0"
                )
            return scraper_input.num_of_min * 60

        return scraper_input.hours_old * 3600 if scraper_input.hours_old else None

    def _log_page_progress(
        self,
        *,
        request_count: int,
        start: int,
        job_cards_count: int,
        new_jobs_count: int,
        duplicate_jobs_count: int,
        total_jobs: int,
        page_started_at: float,
    ) -> None:
        elapsed_seconds = max(0.0, time.perf_counter() - page_started_at)
        log.info(
            "LinkedIn page %s complete: start=%s cards=%s new=%s duplicates=%s total=%s elapsed=%.2fs",
            request_count,
            start,
            job_cards_count,
            new_jobs_count,
            duplicate_jobs_count,
            total_jobs,
            elapsed_seconds,
        )

    def _get_page_delay_bounds(self) -> tuple[float, float]:
        resolved_min = float(self.delay)
        resolved_max = float(self.delay + self.band_delay)
        if self.scraper_input is None:
            return resolved_min, resolved_max

        configured_min = self.scraper_input.linkedin_page_delay_min
        configured_max = self.scraper_input.linkedin_page_delay_max
        if configured_min is not None:
            resolved_min = float(configured_min)
        if configured_max is not None:
            resolved_max = float(configured_max)
        elif configured_min is not None and resolved_min > resolved_max:
            resolved_max = resolved_min

        if resolved_min < 0 or resolved_max < 0:
            raise LinkedInException(
                "LinkedIn page delay values must be non-negative"
            )
        if resolved_max < resolved_min:
            raise LinkedInException(
                "LinkedIn page delay max must be greater than or equal to min"
            )
        return resolved_min, resolved_max

    def _draw_page_delay_seconds(self, *, multiplier: float = 1.0) -> float:
        min_delay, max_delay = self._get_page_delay_bounds()
        return random.uniform(min_delay, max_delay) * multiplier

    def _sleep_before_page_retry(
        self,
        *,
        start: int,
        next_attempt: int,
        reason: str,
    ) -> None:
        multiplier = min(4.0, float(2 ** max(0, next_attempt - 1)))
        delay_seconds = self._draw_page_delay_seconds(multiplier=multiplier)
        log.warning(
            "LinkedIn page request retry scheduled: start=%s attempt=%s/%s reason=%s sleep=%.2fs",
            start,
            next_attempt,
            self.search_page_retry_attempts,
            reason,
            delay_seconds,
        )
        time.sleep(delay_seconds)

    def _fetch_search_page(
        self,
        *,
        params: dict[str, object],
        start: int,
    ):
        search_variants = self._build_search_request_variants(params)
        for attempt in range(1, self.search_page_retry_attempts + 1):
            retry_reason = None
            last_error = None
            for variant in search_variants:
                try:
                    response = self.session.get(
                        variant["url"],
                        params=params,
                        timeout=10,
                    )
                except Exception as exc:
                    last_error = str(exc)
                    if "Proxy responded with" in last_error:
                        log.error("LinkedIn: Bad proxy")
                        return None
                    retry_reason = last_error
                    continue

                if response.status_code in range(200, 400):
                    soup = BeautifulSoup(response.text, "html.parser")
                    if variant["authenticated"] and self._is_guest_search_markup(soup):
                        last_error = (
                            "LinkedIn authenticated search resolved to guest markup"
                        )
                        continue

                    if self._extract_search_job_cards(soup):
                        return response

                    if variant["authenticated"] and len(search_variants) > 1:
                        last_error = (
                            "LinkedIn authenticated search page returned no usable cards"
                        )
                        continue

                    return response

                if response.status_code in self.transient_status_codes:
                    retry_reason = f"status {response.status_code}"
                    last_error = retry_reason
                    continue

                if response.status_code == 429:
                    last_error = "429 Response - Blocked by LinkedIn for too many requests"
                else:
                    last_error = (
                        f"LinkedIn response status code {response.status_code}"
                        f" - {response.text}"
                    )

            if retry_reason and attempt < self.search_page_retry_attempts:
                self._sleep_before_page_retry(
                    start=start,
                    next_attempt=attempt + 1,
                    reason=retry_reason,
                )
                continue

            if last_error:
                log.error(last_error)
            return None

        return None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes LinkedIn for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        self.jobs_table_lookup = (
            LinkedInJobsTableLookup() if scraper_input.linkedin_fetch_description else None
        )
        self._jobs_table_lookup_failed = False
        job_list: list[JobPost] = []
        seen_ids = set()
        is_until_last_page = (
            scraper_input.linkedin_execution_mode
            == LinkedInScrapeMode.UNTIL_LAST_PAGE
        )
        start = (
            0
            if is_until_last_page
            else scraper_input.offset // 10 * 10 if scraper_input.offset else 0
        )
        request_count = 0
        seconds_old = self._get_seconds_old_filter(scraper_input)
        continue_search = (
            (lambda: True)
            if is_until_last_page
            else lambda: len(job_list) < scraper_input.results_wanted and start < 1000
        )
        try:
            while continue_search():
                request_count += 1
                page_started_at = time.perf_counter()
                if is_until_last_page:
                    log.info(f"search page: {request_count} (start={start})")
                else:
                    log.info(
                        f"search page: {request_count} / {math.ceil(scraper_input.results_wanted / 10)}"
                    )
                params = {
                    "keywords": (
                        scraper_input.search_term
                        if scraper_input.search_term is not None
                        else ""
                    ),
                    "location": scraper_input.location,
                    "distance": scraper_input.distance,
                    "f_WT": 2 if scraper_input.is_remote else None,
                    "f_JT": (
                        job_type_code(scraper_input.job_type)
                        if scraper_input.job_type
                        else None
                    ),
                    "f_AL": "true" if scraper_input.easy_apply else None,
                    "f_C": (
                        ",".join(map(str, scraper_input.linkedin_company_ids))
                        if scraper_input.linkedin_company_ids
                        else None
                    ),
                    "geoId": scraper_input.linkedin_geo_id,
                }
                if seconds_old is not None:
                    params["f_TPR"] = f"r{seconds_old}"
                params["pageNum"] = 0
                params["start"] = start

                params = {k: v for k, v in params.items() if v is not None}
                search_url = self._build_search_url(
                    params,
                    authenticated=self._should_use_authenticated_search(),
                )
                log.info(f"LinkedIn search page {request_count} URL: {search_url}")
                response = self._fetch_search_page(
                    params=params,
                    start=start,
                )
                if response is None:
                    return JobResponse(jobs=job_list)

                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = self._extract_search_job_cards(soup)
                if len(job_cards) == 0:
                    log.info(
                        "LinkedIn page %s returned 0 cards; stopping with total_jobs=%s",
                        request_count,
                        len(job_list),
                    )
                    return JobResponse(jobs=job_list)

                page_duplicate_count = 0
                page_new_count = 0
                for job_card in job_cards:
                    href_tag = job_card.find("a", class_="base-card__full-link")
                    if href_tag and "href" in href_tag.attrs:
                        apply_url = self._normalize_linkedin_job_url(
                            href_tag.attrs["href"]
                        )
                        job_id = self._extract_job_id(apply_url)
                        if not job_id:
                            continue

                        if job_id in seen_ids:
                            page_duplicate_count += 1
                            continue
                        seen_ids.add(job_id)

                        try:
                            fetch_desc = (
                                scraper_input.linkedin_fetch_description
                                and self.claim_description_slot()
                            )
                            job_post = self._process_job(
                                job_card,
                                job_id,
                                fetch_desc,
                                apply_url=apply_url,
                            )
                            if job_post:
                                job_list.append(job_post)
                                page_new_count += 1
                            if not continue_search():
                                break
                        except Exception as e:
                            raise LinkedInException(str(e))

                self._log_page_progress(
                    request_count=request_count,
                    start=start,
                    job_cards_count=len(job_cards),
                    new_jobs_count=page_new_count,
                    duplicate_jobs_count=page_duplicate_count,
                    total_jobs=len(job_list),
                    page_started_at=page_started_at,
                )

                if continue_search():
                    next_start = start + len(job_cards)
                    if (
                        is_until_last_page
                        and not self._should_use_authenticated_search()
                        and next_start >= 1000
                    ):
                        log.info(
                            "LinkedIn reached guest pagination limit at next_start=%s; stopping with total_jobs=%s",
                            next_start,
                            len(job_list),
                        )
                        break
                    delay_seconds = self._draw_page_delay_seconds()
                    log.info(
                        "LinkedIn waiting %.2fs before next page (next_start=%s)",
                        delay_seconds,
                        next_start,
                    )
                    time.sleep(delay_seconds)
                    start = next_start

            if not is_until_last_page:
                job_list = job_list[: scraper_input.results_wanted]
            return JobResponse(jobs=job_list)
        finally:
            if self.jobs_table_lookup is not None:
                self.jobs_table_lookup.close()
                self.jobs_table_lookup = None

    def _process_job(
        self,
        job_card: Tag,
        job_id: str,
        full_descr: bool,
        apply_url: str | None = None,
    ) -> Optional[JobPost]:
        compensation = self._parse_search_card_compensation(job_card)
        description = None
        title = self._parse_search_card_title(job_card)
        company, company_url = self._parse_search_card_company(job_card)
        location = self._parse_search_card_location(job_card)
        date_posted = self._parse_search_card_date(job_card)
        job_details = {}
        job_url = self._normalize_linkedin_job_url(apply_url) or f"{self.base_url}/jobs/view/{job_id}"
        resolved_apply_url = None
        job_url_direct = None
        applications_count = self._parse_applications_count(job_card)
        if full_descr:
            job_details = self._get_existing_job_details(job_url)
            live_job_details = self._get_job_details(job_id)
            if not job_details:
                job_details = live_job_details
            elif live_job_details:
                for key, value in live_job_details.items():
                    if key in {"applications_count"}:
                        job_details[key] = value
                    elif value is not None:
                        job_details[key] = value
            for ignored_key in ("company_logo",):
                job_details.pop(ignored_key, None)
            description = job_details.get("description")
            if job_details.get("job_url"):
                job_url = job_details["job_url"]
            if job_details.get("apply_url"):
                resolved_apply_url = job_details["apply_url"]
            if job_details.get("job_url_direct"):
                job_url_direct = job_details["job_url_direct"]
            if "applications_count" in job_details:
                applications_count = job_details.get("applications_count")
        is_remote = is_job_remote(title, description, location)

        return JobPost(
            id=f"li-{job_id}",
            title=title,
            company_name=company,
            company_url=company_url,
            location=location,
            is_remote=is_remote,
            date_posted=date_posted,
            job_url=job_url,
            apply_url=resolved_apply_url,
            job_url_direct=job_url_direct,
            compensation=compensation,
            job_type=job_details.get("job_type"),
            job_level=(job_details.get("job_level") or "").lower(),
            company_industry=job_details.get("company_industry"),
            description=job_details.get("description"),
            applications_count=applications_count,
            emails=extract_emails_from_text(description),
            job_function=job_details.get("job_function"),
        )

    def _get_existing_job_details(self, job_url: str) -> dict:
        if self.jobs_table_lookup is None or self._jobs_table_lookup_failed:
            return {}

        try:
            return self.jobs_table_lookup.get_job_details(job_url) or {}
        except Exception as exc:
            log.warning(f"LinkedIn DB lookup unavailable: {exc}")
            self._jobs_table_lookup_failed = True
            self.jobs_table_lookup.close()
            self.jobs_table_lookup = None
            return {}

    def _get_job_details(self, job_id: str) -> dict:
        """
        Retrieves job description and other job details by going to the job page url
        :param job_page_url:
        :return: dict
        """
        try:
            response = self.session.get(
                f"{self.base_url}/jobs/view/{job_id}", timeout=5
            )
            response.raise_for_status()
        except:
            return {}
        if "linkedin.com/signup" in response.url:
            return {}

        job_details = self._parse_job_details_response(job_id, response)
        if self.auth_cookies and not job_details.get("description"):
            guest_job_details = self._get_guest_job_details(job_id)
            if guest_job_details:
                job_details = self._merge_job_details(job_details, guest_job_details)
        return job_details

    def _get_guest_job_details(self, job_id: str) -> dict:
        try:
            response = self._get_guest_canonical_session().get(
                f"{self.base_url}/jobs/view/{job_id}",
                timeout=10,
            )
            response.raise_for_status()
        except Exception:
            return {}
        if "linkedin.com/signup" in response.url:
            return {}

        return self._parse_job_details_response(job_id, response)

    def _merge_job_details(self, primary: dict, fallback: dict) -> dict:
        merged = dict(primary or {})
        for key, value in (fallback or {}).items():
            if not self._has_job_detail_value(merged.get(key)) and self._has_job_detail_value(value):
                merged[key] = value
        return merged

    def _has_job_detail_value(self, value) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    def _parse_job_details_response(self, job_id: str, response) -> dict:
        soup = BeautifulSoup(response.text, "html.parser")
        canonical_job_url = self._resolve_job_url(
            job_id,
            soup,
            response.url,
            response.text,
        )
        description = self._parse_description(soup)
        job_function = self._parse_job_function(soup)
        return {
            "job_url": canonical_job_url,
            "apply_url": self._parse_apply_url(soup, response.url, response.text),
            "description": description,
            "job_level": parse_job_level(soup),
            "company_industry": parse_company_industry(soup),
            "job_type": parse_job_type(soup),
            "job_url_direct": self._parse_job_url_direct(soup, response.text),
            "applications_count": self._parse_applications_count(
                soup, response.text
            ),
            "job_function": job_function,
        }

    def _parse_description(self, soup: BeautifulSoup) -> str | None:
        div_content = soup.find(
            "div", class_=lambda x: x and "show-more-less-html__markup" in x
        )
        if div_content is not None:
            div_content = remove_attributes(div_content)
            description = div_content.prettify(formatter="html")
            return self._format_description(description)

        job_posting = self._parse_job_posting_json_ld(soup)
        if isinstance(job_posting, dict) and job_posting.get("description"):
            return self._format_description(unescape(str(job_posting["description"])))

        return None

    def _format_description(self, description: str | None) -> str | None:
        if description is None:
            return None
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(description)
        if self.scraper_input.description_format == DescriptionFormat.PLAIN:
            return plain_converter(description)
        return description

    def _parse_job_function(self, soup: BeautifulSoup) -> str | None:
        h3_tag = soup.find(
            "h3", text=lambda text: text and "Job function" in text.strip()
        )

        if h3_tag:
            job_function_span = h3_tag.find_next(
                "span", class_="description__job-criteria-text"
            )
            if job_function_span:
                return job_function_span.text.strip()
        return None

    def _build_search_url(
        self, params: dict[str, object], *, authenticated: bool = False
    ) -> str:
        query_string = urlencode(params, doseq=True)
        search_url = (
            f"{self.base_url}{self.authenticated_search_path}"
            if authenticated
            else f"{self.base_url}{self.guest_search_path}"
        )
        if query_string:
            return f"{search_url}?{query_string}"
        return search_url

    def _build_search_request_variants(
        self, params: dict[str, object]
    ) -> list[dict[str, object]]:
        variants: list[dict[str, object]] = []
        if self._should_use_authenticated_search():
            variants.append(
                {
                    "authenticated": True,
                    "label": "authenticated",
                    "url": f"{self.base_url}{self.authenticated_search_path}",
                }
            )
        variants.append(
            {
                "authenticated": False,
                "label": "guest",
                "url": f"{self.base_url}{self.guest_search_path}",
            }
        )
        return variants

    def _should_use_authenticated_search(self) -> bool:
        return bool(self.auth_cookies.get("li_at"))

    def _is_guest_search_markup(self, soup: BeautifulSoup) -> bool:
        page_key_tag = soup.find("code", id="pageKey")
        if not page_key_tag:
            return False
        return "d_jobs_guest_search" in page_key_tag.decode_contents()

    def _extract_search_job_cards(self, soup: BeautifulSoup) -> list[Tag]:
        guest_cards = soup.find_all("div", class_="base-search-card")
        if guest_cards:
            return guest_cards

        authenticated_cards = soup.find_all(
            "div",
            class_=lambda value: self._class_contains(value, "job-card-container"),
        )
        if authenticated_cards:
            return authenticated_cards

        wrapper_cards: list[Tag] = []
        for wrapper in soup.find_all(
            "li",
            class_=lambda value: value
            and (
                self._class_contains(value, "jobs-search-results__list-item")
                or self._class_contains(value, "scaffold-layout__list-item")
            ),
        ):
            if wrapper.find("a", href=lambda href: href and "/jobs/view/" in href):
                wrapper_cards.append(wrapper)
        return wrapper_cards

    def _parse_search_card_compensation(
        self, job_card: BeautifulSoup | Tag
    ) -> Compensation | None:
        salary_tag = job_card.find(
            attrs={
                "class": lambda value: value
                and (
                    self._class_contains(value, "job-search-card__salary-info")
                    or self._class_contains(value, "job-card-container__salary-info")
                )
            }
        )
        if not salary_tag:
            return None

        salary_text = salary_tag.get_text(separator=" ").strip()
        if "-" not in salary_text:
            return None

        salary_values = [currency_parser(value) for value in salary_text.split("-")]
        if len(salary_values) < 2:
            return None
        salary_min = salary_values[0]
        salary_max = salary_values[1]
        if salary_min is None or salary_max is None:
            return None
        currency = salary_text[0] if salary_text[0] != "$" else "USD"
        return Compensation(
            min_amount=int(salary_min),
            max_amount=int(salary_max),
            currency=currency,
        )

    def _parse_search_card_title(self, job_card: BeautifulSoup | Tag) -> str:
        title_tag = job_card.find("span", class_="sr-only")
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title:
                return title

        title_anchor = job_card.find(
            "a",
            attrs={
                "class": lambda value: value
                and (
                    self._class_contains(value, "base-card__full-link")
                    or self._class_contains(value, "base-card--link")
                    or self._class_contains(value, "job-card-list__title")
                    or self._class_contains(value, "job-card-container__link")
                )
            },
        )
        if title_anchor:
            title = title_anchor.get_text(" ", strip=True)
            if title:
                return title

        fallback_anchor = job_card.find(
            "a", href=lambda href: href and "/jobs/view/" in href
        )
        if fallback_anchor:
            title = fallback_anchor.get_text(" ", strip=True)
            if title:
                return title

        return "N/A"

    def _parse_search_card_company(
        self, job_card: BeautifulSoup | Tag
    ) -> tuple[str, str]:
        company_link = job_card.find(
            "a",
            href=lambda href: href and "/company/" in href,
        )
        if company_link:
            company_url = (
                urlunparse(urlparse(company_link.get("href"))._replace(query=""))
                if company_link.has_attr("href")
                else ""
            )
            company = company_link.get_text(" ", strip=True) or "N/A"
            return company, company_url

        company_tag = job_card.find("h4", class_="base-search-card__subtitle")
        company_a_tag = company_tag.find("a") if company_tag else None
        if company_a_tag:
            company_url = urlunparse(
                urlparse(company_a_tag.get("href"))._replace(query="")
            )
            company = company_a_tag.get_text(" ", strip=True) or "N/A"
            return company, company_url

        subtitle_tag = job_card.find(
            attrs={
                "class": lambda value: value
                and (
                    self._class_contains(
                        value, "job-card-container__primary-description"
                    )
                    or self._class_contains(value, "job-card-container__company-name")
                )
            }
        )
        if subtitle_tag:
            company = subtitle_tag.get_text(" ", strip=True)
            if company:
                return company, ""

        return "N/A", ""

    def _parse_search_card_location(self, job_card: BeautifulSoup | Tag) -> Location:
        location_string = self._parse_search_card_location_text(job_card)
        return self._build_location_from_string(location_string)

    def _parse_search_card_location_text(
        self, job_card: BeautifulSoup | Tag
    ) -> str | None:
        location_tag = job_card.find(
            attrs={
                "class": lambda value: value
                and (
                    self._class_contains(value, "job-search-card__location")
                    or self._class_contains(value, "job-card-container__metadata-item")
                    or self._class_contains(value, "artdeco-entity-lockup__caption")
                )
            }
        )
        if not location_tag:
            return None

        location_text = location_tag.get_text(" ", strip=True)
        return location_text or None

    def _build_location_from_string(self, location_string: str | None) -> Location:
        location = Location(country=Country.from_string(self.country))
        if not location_string:
            return location

        parts = [part.strip() for part in location_string.split(",") if part.strip()]
        if len(parts) == 2:
            city, state = parts
            return Location(
                city=city,
                state=state,
                country=Country.from_string(self.country),
            )
        if len(parts) >= 3:
            city = parts[0]
            state = parts[1]
            country = Country.from_string(parts[-1])
            return Location(city=city, state=state, country=country)
        return location

    def _parse_search_card_date(
        self, job_card: BeautifulSoup | Tag
    ) -> datetime | None:
        datetime_tag = job_card.find(
            "time",
            class_=lambda value: value
            and (
                self._class_contains(value, "job-search-card__listdate")
                or self._class_contains(value, "job-search-card__listdate--new")
            ),
        )
        if not datetime_tag:
            datetime_tag = job_card.find("time")
        if not datetime_tag:
            return None

        datetime_str = datetime_tag.get("datetime")
        if not datetime_str:
            return None
        try:
            return datetime.strptime(datetime_str, "%Y-%m-%d")
        except Exception:
            return None

    def _normalize_auth_cookies(
        self, auth_cookies: dict[str, str] | None
    ) -> dict[str, str]:
        normalized_auth_cookies: dict[str, str] = {}
        if not auth_cookies:
            return normalized_auth_cookies

        for name, value in auth_cookies.items():
            normalized_name = (name or "").strip()
            normalized_value = (value or "").strip()
            if normalized_name and normalized_value:
                normalized_auth_cookies[normalized_name] = normalized_value

        return normalized_auth_cookies

    def _apply_auth_cookies(self) -> None:
        if not self.auth_cookies:
            return

        for name, value in self.auth_cookies.items():
            self.session.cookies.set(name, value, domain=".linkedin.com", path="/")

        if jsessionid := self.auth_cookies.get("JSESSIONID"):
            self.session.headers["csrf-token"] = jsessionid.strip('"')

    def _get_location(self, metadata_card: Optional[Tag]) -> Location:
        """
        Extracts the location data from the job metadata card.
        :param metadata_card
        :return: location
        """
        if metadata_card is None:
            return Location(country=Country.from_string(self.country))

        location_tag = metadata_card.find(
            "span", class_="job-search-card__location"
        )
        location_string = location_tag.text.strip() if location_tag else None
        return self._build_location_from_string(location_string)

    def _parse_job_url_direct(
        self, soup: BeautifulSoup, raw_html: str | None = None
    ) -> str | None:
        """
        Gets the job url direct from job page
        :param soup:
        :return: str
        """
        job_url_direct = None
        job_url_direct_content = soup.find("code", id="applyUrl")
        if job_url_direct_content:
            job_url_direct_match = self.job_url_direct_regex.search(
                job_url_direct_content.decode_contents().strip()
            )
            if job_url_direct_match:
                job_url_direct = unquote(job_url_direct_match.group())

        if job_url_direct:
            return job_url_direct

        return self._parse_logged_in_offsite_apply_url(raw_html)

    def _parse_apply_url(
        self, soup: BeautifulSoup, response_url: str | None, raw_html: str | None = None
    ) -> str | None:
        external_apply_url = self._parse_job_url_direct(soup, raw_html)
        if external_apply_url:
            return external_apply_url

        logged_in_easy_apply_url = self._parse_logged_in_easy_apply_url(raw_html)
        if logged_in_easy_apply_url:
            return logged_in_easy_apply_url

        if self._is_offsite_apply(soup):
            return None

        return self._parse_canonical_job_url(soup, response_url)

    def _get_guest_canonical_session(self):
        if self._guest_canonical_session is None:
            self._guest_canonical_session = create_session(
                proxies=self.proxies,
                ca_cert=self.ca_cert,
                is_tls=False,
                has_retry=True,
                delay=5,
                clear_cookies=True,
            )
            self._guest_canonical_session.headers.update(headers)
            if self.user_agent:
                self._guest_canonical_session.headers["User-Agent"] = self.user_agent
        return self._guest_canonical_session

    def _fetch_guest_canonical_job_url(self, job_id: str) -> str | None:
        try:
            response = self._get_guest_canonical_session().get(
                f"{self.base_url}/jobs/view/{job_id}",
                timeout=10,
            )
            response.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        return self._parse_canonical_job_url_from_markup(soup)

    def _resolve_job_url(
        self,
        job_id: str,
        soup: BeautifulSoup,
        response_url: str | None,
        raw_html: str | None = None,
    ) -> str | None:
        canonical_job_url = self._parse_canonical_job_url_from_markup(soup)
        if canonical_job_url:
            return canonical_job_url

        page_variant = self._detect_page_variant(soup, raw_html)
        if page_variant == "authenticated_sdui":
            guest_canonical_job_url = self._fetch_guest_canonical_job_url(job_id)
            if guest_canonical_job_url:
                return guest_canonical_job_url

        normalized_response_url = self._normalize_linkedin_job_url(response_url)
        if normalized_response_url and self._extract_job_id(normalized_response_url):
            return normalized_response_url

        return None

    def _parse_canonical_job_url_from_markup(
        self, soup: BeautifulSoup
    ) -> str | None:
        candidates = [
            soup.find("link", attrs={"rel": "canonical"}),
            soup.find("meta", attrs={"property": "lnkd:url"}),
            soup.find("meta", attrs={"property": "og:url"}),
        ]

        for candidate in candidates:
            if not candidate:
                continue
            job_url = candidate.get("href") or candidate.get("content")
            normalized_job_url = self._normalize_linkedin_job_url(job_url)
            if normalized_job_url and self._extract_job_id(normalized_job_url):
                return normalized_job_url

        return None

    def _parse_canonical_job_url(
        self, soup: BeautifulSoup, response_url: str | None
    ) -> str | None:
        canonical_job_url = self._parse_canonical_job_url_from_markup(soup)
        if canonical_job_url:
            return canonical_job_url

        normalized_response_url = self._normalize_linkedin_job_url(response_url)
        if normalized_response_url and self._extract_job_id(normalized_response_url):
            return normalized_response_url

        return None

    def _decode_escaped_stream_value(self, value: str | None) -> str | None:
        if not value:
            return None

        try:
            return json.loads(f'"{value}"')
        except json.JSONDecodeError:
            return (
                value.replace("\\u0026", "&")
                .replace("\\/", "/")
                .replace('\\"', '"')
            )

    def _parse_logged_in_offsite_apply_url(self, raw_html: str | None) -> str | None:
        if not raw_html:
            return None

        match = re.search(
            r'offsiteApplyUrl\\":\\"(?P<url>https?://[^"]+?)\\"',
            raw_html,
        )
        if not match:
            return None

        return self._decode_escaped_stream_value(match.group("url"))

    def _parse_logged_in_easy_apply_url(self, raw_html: str | None) -> str | None:
        if not raw_html:
            return None

        match = re.search(
            r'url\\":\\"(?P<url>https://www\.linkedin\.com/jobs/view/\d+/apply/\?openSDUIApplyFlow=true[^"]+?)\\"',
            raw_html,
        )
        if not match:
            return None

        return self._decode_escaped_stream_value(match.group("url"))

    def _parse_clicked_apply_text(
        self, soup: BeautifulSoup | Tag, raw_html: str | None = None
    ) -> str | None:
        soup_text = soup.get_text(" ", strip=True)
        soup_match = self.clicked_apply_count_regex.search(soup_text)
        if soup_match:
            return soup_match.group(0)

        if not raw_html:
            return None

        html_match = self.clicked_apply_count_regex.search(raw_html)
        if not html_match:
            return None

        return html_match.group(0)

    def _detect_page_variant(
        self, soup: BeautifulSoup, raw_html: str | None = None
    ) -> str:
        if soup.find(attrs={"data-sdui-screen": True}):
            return "authenticated_sdui"

        if soup.find(
            "meta", attrs={"name": "pageKey", "content": "d_jobs_guest_details"}
        ):
            return "guest_details"

        if raw_html and "storage-inventory" in raw_html:
            return "authenticated_shell"

        return "unknown"

    def _parse_job_posting_json_ld(self, soup: BeautifulSoup) -> dict[str, object] | None:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_json = script.string or script.get_text(strip=True)
            if not raw_json:
                continue
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict) and parsed.get("@type") == "JobPosting":
                return parsed
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        return item

        return None

    def _extract_hidden_code_values(self, soup: BeautifulSoup) -> dict[str, str]:
        hidden_codes: dict[str, str] = {}
        for code_tag in soup.find_all("code", id=True):
            code_value = code_tag.get_text(strip=True)
            if code_value:
                hidden_codes[code_tag["id"]] = code_value
        return hidden_codes

    def _extract_meta_values(self, soup: BeautifulSoup) -> dict[str, str]:
        meta_values: dict[str, str] = {}
        for meta_tag in soup.find_all("meta"):
            meta_name = meta_tag.get("property") or meta_tag.get("name") or meta_tag.get("id")
            meta_value = meta_tag.get("content")
            if meta_name and meta_value:
                meta_values[meta_name] = meta_value
        return meta_values

    def _build_job_posting_summary(
        self, job_posting: dict[str, object] | None
    ) -> dict[str, object] | None:
        if not job_posting:
            return None

        hiring_organization = job_posting.get("hiringOrganization")
        identifier = job_posting.get("identifier")
        job_location = job_posting.get("jobLocation")
        address = (
            job_location.get("address")
            if isinstance(job_location, dict)
            else None
        )
        if not isinstance(hiring_organization, dict):
            hiring_organization = {}
        if not isinstance(identifier, dict):
            identifier = {}
        if not isinstance(address, dict):
            address = {}

        return {
            "title": job_posting.get("title"),
            "datePosted": job_posting.get("datePosted"),
            "validThrough": job_posting.get("validThrough"),
            "employmentType": job_posting.get("employmentType"),
            "industry": job_posting.get("industry"),
            "identifier_name": identifier.get("name"),
            "identifier_value": identifier.get("value"),
            "hiring_org_name": hiring_organization.get("name"),
            "hiring_org_sameAs": hiring_organization.get("sameAs"),
            "hiring_org_logo": hiring_organization.get("logo"),
            "job_location_country": address.get("addressCountry"),
            "job_location_locality": address.get("addressLocality"),
            "job_location_region": address.get("addressRegion"),
            "experience_months": (
                job_posting.get("experienceRequirements", {}) or {}
            ).get("monthsOfExperience")
            if isinstance(job_posting.get("experienceRequirements"), dict)
            else None,
            "education_category": (
                job_posting.get("educationRequirements", {}) or {}
            ).get("credentialCategory")
            if isinstance(job_posting.get("educationRequirements"), dict)
            else None,
            "description_length": len(unescape(str(job_posting.get("description") or ""))),
        }

    def _normalize_linkedin_job_url(self, job_url: str | None) -> str | None:
        if not job_url:
            return None

        parsed = urlparse(urljoin(self.base_url, job_url.strip()))
        if not parsed.scheme or not parsed.netloc:
            return None
        if "linkedin.com" not in parsed.netloc.lower():
            return None

        return urlunparse(parsed._replace(query="", fragment=""))

    def _extract_job_id(self, job_url: str | None) -> str | None:
        normalized_job_url = self._normalize_linkedin_job_url(job_url)
        if not normalized_job_url:
            return None

        match = self.linkedin_job_id_regex.search(urlparse(normalized_job_url).path)
        return match.group("job_id") if match else None

    def _parse_applications_count(
        self, soup_or_tag: BeautifulSoup | Tag, raw_html: str | None = None
    ) -> int | None:
        for class_name in ("num-applicants__caption", "num-applicants__figure"):
            applicants_tag = soup_or_tag.find(
                attrs={
                    "class": lambda value, class_name=class_name: self._class_contains(
                        value, class_name
                    )
                }
            )
            if applicants_tag:
                applicants_count = self._parse_applications_count_text(
                    applicants_tag.get_text(" ", strip=True)
                )
                if applicants_count is not None:
                    return applicants_count

        clicked_apply_text = self._parse_clicked_apply_text(soup_or_tag, raw_html)
        if clicked_apply_text:
            clicked_apply_match = self.clicked_apply_count_regex.search(
                clicked_apply_text
            )
            if clicked_apply_match:
                return int(clicked_apply_match.group("count").replace(",", ""))

        return None

    def _is_offsite_apply(self, soup: BeautifulSoup | Tag) -> bool:
        offsite_icon = soup.find(
            attrs={
                "data-svg-class-name": lambda value: value
                and "apply-button__offsite-apply-icon-svg" in value
            }
        )
        if offsite_icon:
            return True

        offsite_modal = soup.find(
            attrs={
                "data-impression-id": lambda value: value
                and "public_jobs_apply-link-offsite" in value
            }
        )
        if offsite_modal:
            return True

        if soup.find(
            attrs={
                "aria-label": lambda value: value
                and "Apply on company website" in value
            }
        ):
            return True

        soup_text = soup.get_text(" ", strip=True)
        if "Responses managed off LinkedIn" in soup_text:
            return True

        return bool(
            soup.find(
                attrs={
                    "data-is-offsite-apply": lambda value: value
                    and value.lower() == "true"
                }
            )
        )

    def _class_contains(self, value: str | list[str] | None, class_name: str) -> bool:
        if not value:
            return False
        if isinstance(value, list):
            return class_name in value
        return class_name in value.split()

    def _parse_applications_count_text(self, text: str | None) -> int | None:
        if not text:
            return None

        normalized_text = " ".join(text.split())
        match = self.applications_count_regex.search(normalized_text)
        if not match:
            return None

        return int(match.group("count").replace(",", ""))
