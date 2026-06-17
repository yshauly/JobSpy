from __future__ import annotations

import math
from datetime import datetime
from typing import Tuple

from jobspy.indeed.constant import job_search_query, api_headers
from jobspy.indeed.util import is_job_remote, get_compensation, get_job_type
from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    Location,
    JobResponse,
    JobType,
    DescriptionFormat,
)
from jobspy.util import (
    extract_emails_from_text,
    markdown_converter,
    create_session,
    create_logger,
)

log = create_logger("Indeed")


class Indeed(Scraper):
    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes IndeedScraper with the Indeed API url
        """
        super().__init__(Site.INDEED, proxies=proxies)

        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False
        )
        self.scraper_input = None
        self.jobs_per_page = 100
        self.num_workers = 10
        self.seen_urls = set()
        self.headers = None
        self.api_country_code = None
        self.base_url = None
        self.api_url = "https://apis.indeed.com/graphql"

    def _debug_enabled(self) -> bool:
        return bool(
            self.scraper_input
            and getattr(self.scraper_input, "indeed_debug_trace", False)
        )

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            log.info(f"[trace] {message}")

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes Indeed for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        domain, self.api_country_code = self.scraper_input.country.indeed_domain_value
        self.base_url = f"https://{domain}.indeed.com"
        self.headers = api_headers.copy()
        self.headers["indeed-co"] = self.api_country_code
        job_list = []
        page = 1

        cursor = None
        self._debug(
            "Initialized Indeed search with "
            f"country={self.scraper_input.country.value[0]!r}, "
            f"domain={domain!r}, api_country_code={self.api_country_code!r}, "
            f"search_term={self.scraper_input.search_term!r}, "
            f"location={self.scraper_input.location!r}, "
            f"distance={self.scraper_input.distance!r}, "
            f"results_wanted={self.scraper_input.results_wanted!r}, "
            f"offset={self.scraper_input.offset!r}, "
            f"hours_old={self.scraper_input.hours_old!r}, "
            f"job_type={self.scraper_input.job_type!r}, "
            f"is_remote={self.scraper_input.is_remote!r}, "
            f"easy_apply={self.scraper_input.easy_apply!r}, "
            f"description_limit={self.scraper_input.description_limit!r}"
        )

        while len(self.seen_urls) < scraper_input.results_wanted + scraper_input.offset:
            log.info(
                f"search page: {page} / {math.ceil(scraper_input.results_wanted / self.jobs_per_page)}"
            )
            self._debug(
                f"Requesting page={page} with cursor={cursor!r}; "
                f"seen_urls={len(self.seen_urls)} target={scraper_input.results_wanted + scraper_input.offset}"
            )
            jobs, cursor = self._scrape_page(cursor)
            self._debug(
                f"Page={page} returned jobs={len(jobs)} next_cursor={cursor!r}; "
                f"seen_urls_now={len(self.seen_urls)}"
            )
            if not jobs:
                log.info(f"found no jobs on page: {page}")
                break
            job_list += jobs
            page += 1
        self._debug(
            f"Indeed scrape complete with accumulated_jobs={len(job_list)} "
            f"and returned_jobs={len(job_list[scraper_input.offset : scraper_input.offset + scraper_input.results_wanted])}"
        )
        return JobResponse(
            jobs=job_list[
                scraper_input.offset : scraper_input.offset
                + scraper_input.results_wanted
            ]
        )

    def _scrape_page(self, cursor: str | None) -> Tuple[list[JobPost], str | None]:
        """
        Scrapes a page of Indeed for jobs with scraper_input criteria
        :param cursor:
        :return: jobs found on page, next page cursor
        """
        jobs = []
        new_cursor = None
        target_results = (
            self.scraper_input.results_wanted + self.scraper_input.offset
            if self.scraper_input
            else None
        )
        filters = self._build_filters()
        search_term = (
            self.scraper_input.search_term.replace('"', '\\"')
            if self.scraper_input.search_term
            else ""
        )
        location_query = ""
        if self.scraper_input.location:
            if self.scraper_input.distance is None:
                location_query = (
                    f'location: {{where: "{self.scraper_input.location}"}}'
                )
            else:
                location_query = (
                    "location: {"
                    f'where: "{self.scraper_input.location}", '
                    f"radius: {self.scraper_input.distance}, "
                    "radiusUnit: MILES}"
                )
        query = job_search_query.format(
            what=(f'what: "{search_term}"' if search_term else ""),
            location=location_query,
            dateOnIndeed=self.scraper_input.hours_old,
            cursor=f'cursor: "{cursor}"' if cursor else "",
            filters=filters,
        )
        payload = {
            "query": query,
        }
        api_headers_temp = api_headers.copy()
        api_headers_temp["indeed-co"] = self.api_country_code
        self._debug(
            f"Posting Indeed GraphQL search to {self.api_url} "
            f"with indeed-co={api_headers_temp['indeed-co']!r}, "
            f"locale={api_headers_temp.get('indeed-locale')!r}"
        )
        self._debug(f"Resolved filters: {filters.strip() if filters.strip() else 'none'}")
        self._debug(f"GraphQL query:\n{query.strip()}")
        response = self.session.post(
            self.api_url,
            headers=api_headers_temp,
            json=payload,
            timeout=10,
            verify=False,
        )
        self._debug(
            f"Indeed response status={response.status_code} ok={response.ok} "
            f"content_length={len(response.text)}"
        )
        if not response.ok:
            log.info(
                f"responded with status code: {response.status_code} (submit GitHub issue if this appears to be a bug)"
            )
            self._debug(f"Indeed response body preview: {response.text[:1000]}")
            return jobs, new_cursor
        data = response.json()
        self._debug(f"Top-level response keys: {list(data.keys())}")
        if data.get("errors"):
            self._debug(f"GraphQL errors: {data['errors']}")

        job_search = data.get("data", {}).get("jobSearch", {})
        if not job_search:
            self._debug(
                "Indeed response did not include data.jobSearch; returning no jobs"
            )
            return jobs, new_cursor

        jobs = job_search.get("results", [])
        new_cursor = job_search.get("pageInfo", {}).get("nextCursor")
        self._debug(
            f"Indeed response contained {len(jobs)} raw results with next_cursor={new_cursor!r}"
        )

        job_list = []
        for index, job in enumerate(jobs, start=1):
            raw_job = job.get("job", {})
            self._debug(
                f"Processing raw result {index}/{len(jobs)} "
                f"key={raw_job.get('key')!r} title={raw_job.get('title')!r}"
            )
            processed_job = self._process_job(job["job"])
            if processed_job:
                job_list.append(processed_job)
                self._debug(
                    f"Accepted Indeed job id={processed_job.id!r} title={processed_job.title!r}"
                )
            else:
                self._debug(
                    f"Skipped raw result {index}/{len(jobs)} "
                    f"key={raw_job.get('key')!r}"
                )
            if target_results is not None and len(self.seen_urls) >= target_results:
                self._debug(
                    f"Reached target_results={target_results}; "
                    "stopping Indeed page processing early"
                )
                break

        return job_list, new_cursor

    def _build_filters(self):
        """
        Builds the filters dict for job type/is_remote. If hours_old is provided, composite filter for job_type/is_remote is not possible.
        IndeedApply: filters: { keyword: { field: "indeedApplyScope", keys: ["DESKTOP"] } }
        """
        filters_str = ""
        if self.scraper_input.hours_old:
            filters_str = """
            filters: {{
                date: {{
                  field: "dateOnIndeed",
                  start: "{start}h"
                }}
            }}
            """.format(
                start=self.scraper_input.hours_old
            )
        elif self.scraper_input.easy_apply:
            filters_str = """
            filters: {
                keyword: {
                  field: "indeedApplyScope",
                  keys: ["DESKTOP"]
                }
            }
            """
        elif self.scraper_input.job_type or self.scraper_input.is_remote:
            job_type_key_mapping = {
                JobType.FULL_TIME: "CF3CP",
                JobType.PART_TIME: "75GKK",
                JobType.CONTRACT: "NJXCK",
                JobType.INTERNSHIP: "VDTG7",
            }

            keys = []
            if self.scraper_input.job_type:
                key = job_type_key_mapping[self.scraper_input.job_type]
                keys.append(key)

            if self.scraper_input.is_remote:
                keys.append("DSQF7")

            if keys:
                keys_str = '", "'.join(keys)
                filters_str = f"""
                filters: {{
                  composite: {{
                    filters: [{{
                      keyword: {{
                        field: "attributes",
                        keys: ["{keys_str}"]
                      }}
                    }}]
                  }}
                }}
                """
        self._debug(
            f"_build_filters produced: {filters_str.strip() if filters_str.strip() else 'none'}"
        )
        return filters_str

    def _process_job(self, job: dict) -> JobPost | None:
        """
        Parses the job dict into JobPost model
        :param job: dict to parse
        :return: JobPost if it's a new job
        """
        job_url = f'{self.base_url}/viewjob?jk={job["key"]}'
        self._debug(f"Normalizing Indeed job key={job.get('key')!r} to url={job_url}")
        if job_url in self.seen_urls:
            self._debug(f"Skipping duplicate Indeed job url={job_url}")
            return
        self.seen_urls.add(job_url)
        raw_description = job.get("description", {}).get("html")
        description = None
        description_claimed = bool(raw_description and self.claim_description_slot())
        if description_claimed:
            description = raw_description
            if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
                description = markdown_converter(description)
        self._debug(
            f"Description captured={description is not None} "
            f"claimed_slot={description_claimed} "
            f"raw_length={len(raw_description) if raw_description else 0}"
        )

        job_type = get_job_type(job["attributes"])
        timestamp_seconds = job["datePublished"] / 1000
        date_posted = datetime.fromtimestamp(timestamp_seconds).strftime("%Y-%m-%d")
        employer_payload = job.get("employer")
        employer = employer_payload.get("dossier") if employer_payload else None
        employer_details = employer.get("employerDetails", {}) if employer else {}
        rel_url = (
            employer_payload.get("relativeCompanyPageUrl") if employer_payload else None
        )
        compensation = get_compensation(
            job.get("compensation") or {"baseSalary": None, "estimated": None}
        )
        job_post = JobPost(
            id=f'in-{job["key"]}',
            title=job["title"],
            description=description,
            company_name=employer_payload.get("name") if employer_payload else None,
            company_url=(f"{self.base_url}{rel_url}" if employer_payload else None),
            company_url_direct=(
                employer["links"]["corporateWebsite"] if employer else None
            ),
            location=Location(
                city=job.get("location", {}).get("city"),
                state=job.get("location", {}).get("admin1Code"),
                country=job.get("location", {}).get("countryCode"),
            ),
            job_type=job_type,
            compensation=compensation,
            date_posted=date_posted,
            job_url=job_url,
            job_url_direct=(
                job["recruit"].get("viewJobUrl") if job.get("recruit") else None
            ),
            emails=extract_emails_from_text(description) if description else None,
            is_remote=is_job_remote(job, description or ""),
            company_addresses=(
                employer_details["addresses"][0]
                if employer_details.get("addresses")
                else None
            ),
            company_industry=(
                employer_details["industry"]
                .replace("Iv1", "")
                .replace("_", " ")
                .title()
                .strip()
                if employer_details.get("industry")
                else None
            ),
            company_num_employees=employer_details.get("employeesLocalizedLabel"),
            company_revenue=employer_details.get("revenueLocalizedLabel"),
            company_description=employer_details.get("briefDescription"),
            company_logo=(
                employer["images"].get("squareLogoUrl")
                if employer and employer.get("images")
                else None
            ),
        )
        location_display = (
            job_post.location.display_location() if job_post.location else None
        )
        compensation_summary = None
        if job_post.compensation:
            compensation_summary = (
                f"{job_post.compensation.interval.value if job_post.compensation.interval else None}: "
                f"{job_post.compensation.min_amount}-{job_post.compensation.max_amount} "
                f"{job_post.compensation.currency}"
            )
        self._debug(
            "Built Indeed job post "
            f"id={job_post.id!r}, title={job_post.title!r}, "
            f"company={job_post.company_name!r}, location={location_display!r}, "
            f"job_type={[job_type.value[0] for job_type in (job_post.job_type or [])]!r}, "
            f"is_remote={job_post.is_remote!r}, compensation={compensation_summary!r}"
        )
        return job_post
