from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from jobspy import scrape_jobs
from jobspy.apple import DEFAULT_APPLE_SEARCH_URL
from jobspy.chromium_cookies import (
    load_linkedin_builtin_cookies,
    load_linkedin_chromium_cookies,
    resolve_linkedin_auth_context,
)
from jobspy.google_careers import DEFAULT_GOOGLE_CAREERS_URL
from jobspy.model import (
    Country,
    DescriptionFormat,
    GreenhouseScrapeMode,
    LinkedInScrapeMode,
    ScraperInput,
    Site,
)
from jobspy.microsoft import DEFAULT_MICROSOFT_BASE_URL
from jobspy.redhat import DEFAULT_REDHAT_BASE_URL
from jobspy.jobs_table import NICE_GREENHOUSE_JOBS_URL, NICE_JSON_FEED_CONFIG

DEFAULT_LINKEDIN_OUTPUT = "linkedin_jobs.json"
DEFAULT_INDEED_OUTPUT = "indeed_jobs.json"
DEFAULT_COMEET_OUTPUT = "comeet_jobs.json"
DEFAULT_GREENHOUSE_OUTPUT = "greenhouse_jobs.json"
DEFAULT_GLASSDOOR_OUTPUT = "glassdoor_jobs.json"
DEFAULT_AMDOCS_OUTPUT = "amdocs_jobs.json"
DEFAULT_APPLE_OUTPUT = "apple_jobs.json"
DEFAULT_GOOGLE_CAREERS_OUTPUT = "google_careers_jobs.json"
DEFAULT_MICROSOFT_OUTPUT = "microsoft_jobs.json"
DEFAULT_REDHAT_OUTPUT = "redhat_jobs.json"
DEFAULT_MARVELL_OUTPUT = "marvell_jobs.json"
DEFAULT_VARONIS_OUTPUT = "varonis_jobs.json"
DEFAULT_COMPANY_CAREER_PAGES_OUTPUT = "company_career_pages_jobs.json"
DEFAULT_VARONIS_BASE_URL = "https://careers.varonis.com/"
DEFAULT_MARVELL_BASE_URL = (
    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
    "?Country=084562884af243748dad7c84c304d89a"
)
DEFAULT_AMDOCS_BASE_URL = (
    "https://jobs.amdocs.com/careers"
    "?start=0&location=Israel&pid=563431010318975"
    "&sort_by=match&filter_include_remote=1"
)
DEFAULT_GLASSDOOR_COUNTRY = "USA"
DEFAULT_GLASSDOOR_LOCATION = "San Francisco, CA"
DEFAULT_GLASSDOOR_FROM_AGE_DAYS = 3
DEFAULT_LINKEDIN_ISRAEL_GEO_ID = 101620260
DEFAULT_LINKEDIN_INDIA_GEO_ID = 102713980
DEFAULT_LINKEDIN_INDIA_SHARD_WORKERS = 4
DEFAULT_LINKEDIN_DESCRIPTION_WORKERS = 4
LINKEDIN_INDIA_SCHEDULER_TIMEZONE = ZoneInfo("Asia/Kolkata")
LINKEDIN_INDIA_SCHEDULER_FIRST_RUN_HOUR = 8
LINKEDIN_INDIA_SCHEDULER_LAST_RUN_HOUR = 22
LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE = 0
LINKEDIN_INDIA_SCHEDULER_INTERVAL_MINUTES = 60
DEFAULT_GREENHOUSE_LAT = 30.895128
DEFAULT_GREENHOUSE_LON = 34.874702
DEFAULT_GREENHOUSE_LOCATION_TYPE = "country"
DEFAULT_GREENHOUSE_COUNTRY_SHORT_NAME = "IL"
DEFAULT_GREENHOUSE_DATE_POSTED = "past_ten_days"
DEFAULT_GREENHOUSE_COOKIE_FILE = (
    Path(__file__).resolve().parent / "greenhouse" / "greenhouse.cookies"
)
MIN_LINKEDIN_SCHEDULER_INTERVAL_MINUTES = 60
FIRST_SCHEDULER_INTERVAL_MINUTES = 24 * 60
SCHEDULER_THREE_HOUR_INTERVAL_HOURS = 3
SCHEDULER_RUN_MINUTE = 30
SCHEDULER_FIRST_RUN_HOUR = 7
SCHEDULER_LAST_RUN_HOUR = 22
SCHEDULER_TIMEZONE = ZoneInfo("Asia/Jerusalem")
COMPANY_CAREER_PAGES_TABLE_ONLY_INTERVAL_HOURS = 2

LINKEDIN_INDIA_SHARDS = (
    {
        "name": "bengaluru",
        "location": "Bengaluru, Karnataka, India",
        "linkedin_geo_id": None,
        "is_remote": False,
    },
    {
        "name": "pune",
        "location": "Pune, Maharashtra, India",
        "linkedin_geo_id": None,
        "is_remote": False,
    },
)

SET_COOKIE_ATTRIBUTES = {
    "domain",
    "expires",
    "httponly",
    "max-age",
    "path",
    "priority",
    "samesite",
    "secure",
}
COMPANY_CAREER_PAGE_SCRAPER_SITE_ALIASES = {
    "amdocs": "eightfold",
    "nvidia": "eightfold",
    "nice": "json_feed",
    "generic_json": "json_feed",
    "json": "json_feed",
}
COMPANY_CAREER_PAGE_JOB_BOARD_SITES = (
    "indeed",
    "glassdoor",
    "comeet",
    "greenhouse",
)
COMPANY_CAREER_PAGE_URL_KWARG_BY_SITE = {
    "apple": "apple_search_url",
    "comeet": "comeet_company_url",
    "eightfold": "eightfold_company_url",
    "google_careers": "google_careers_url",
    "json_feed": "json_feed_url",
    "meta": "meta_careers_url",
    "microsoft": "microsoft_base_url",
    "redhat": "redhat_base_url",
    "varonis": "varonis_base_url",
    "workday": "workday_company_url",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the existing LinkedIn JobSpy flow, an Indeed-only debug "
            "search, an Indeed persistence run, a Glassdoor persistence run, "
            "a Glassdoor one-job persistence test, a Comeet base URL population run, a "
            "Comeet one-company test scrape, a Comeet Israel batch scrape, "
            "a Comeet Israel persistence run, a Comeet India link-print run, a LinkedIn India link-print run, a LinkedIn India sharded link-print run, a Greenhouse one-job "
            "authenticated debug scrape, a Greenhouse fetch-all "
            "persistence run, an Amdocs persistence run, an Amdocs test scrape, "
            "an Apple Israel persistence run, a Google Careers Israel persistence run, "
            "a Microsoft Israel persistence run, "
            "a Red Hat Israel Workday test scrape, a Red Hat Israel "
            "Workday persistence run, "
            "a Marvell Israel Workday test scrape, or a Marvell Israel "
            "Workday persistence run, a Varonis Israel test scrape, or a "
            "Varonis Israel persistence run"
        )
    )
    parser.add_argument(
        "--search-term",
        default=None,
        help="Optional LinkedIn keyword query",
    )
    parser.add_argument(
        "--location",
        default="Israel",
        help="LinkedIn location to search in",
    )
    parser.add_argument(
        "--linkedin-geo-id",
        type=int,
        default=None,
        help=(
            "Optional LinkedIn geoId to send alongside --location. "
            f"When omitted and --location is Israel, defaults to {DEFAULT_LINKEDIN_ISRAEL_GEO_ID}"
        ),
    )
    parser.add_argument(
        "--results",
        type=int,
        default=1000,
        help=(
            "Maximum number of LinkedIn jobs to fetch. Ignored by "
            "--execution-mode until-last-page"
        ),
    )
    parser.add_argument(
        "--distance",
        type=int,
        default=None,
        help="Optional search radius in miles",
    )
    parser.add_argument(
        "--hours-old",
        type=int,
        default=24,
        help="Only include LinkedIn jobs newer than this many hours",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_LINKEDIN_OUTPUT,
        help=(
            "Path to the JSON output file; also used as input with "
            "--populate-only and --populate-comeet-base-urls. Defaults "
            "to a site-specific JSON filename depending on mode"
        ),
    )
    parser.add_argument(
        "--fetch-description",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fetch full LinkedIn job descriptions and guest-visible metadata",
    )
    parser.add_argument(
        "--save-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Populate the jobs table from the JSON file after scraping",
    )
    parser.add_argument(
        "--populate-only",
        action="store_true",
        help="Skip scraping and populate the jobs table from the JSON file only",
    )
    parser.add_argument(
        "--company-career-pages",
        action="store_true",
        help=(
            "Run the configured company career-page priority scheduler: every "
            "hour at hh:30 Israel time between 07:30 and 22:30, scrape enabled "
            "company_career_pages rows first, then scrape Indeed, Glassdoor, "
            "Comeet, and Greenhouse, and mark job-board rows for "
            "configured companies as duplicates during DB import"
        ),
    )
    parser.add_argument(
        "--company-career-pages-now",
        action="store_true",
        help=(
            "Run the configured company career-page priority flow immediately "
            "once, scraping enabled company_career_pages rows first, then "
            "Indeed, Glassdoor, Comeet, and Greenhouse, and exit "
            "after the combined JSON/DB import finishes"
        ),
    )
    parser.add_argument(
        "--company-career-pages-table-only",
        action="store_true",
        help=(
            "Run only enabled company_career_pages rows immediately, persist "
            "to the jobs table, log new jobs per company, then repeat every "
            "2 hours without scraping the general job boards"
        ),
    )
    parser.add_argument(
        "--company-career-page-probe",
        action="store_true",
        help=(
            "Detect and validate one company career-page URL. Intended for a "
            "UI flow before activating a company_career_pages row"
        ),
    )
    parser.add_argument(
        "--company-key",
        default=None,
        help="Stable company key for --company-career-page-probe",
    )
    parser.add_argument(
        "--company-name",
        default=None,
        help="Company display name for --company-career-page-probe",
    )
    parser.add_argument(
        "--career-page-url",
        default=None,
        help="Career page URL for --company-career-page-probe",
    )
    parser.add_argument(
        "--activate-company-career-page",
        action="store_true",
        help=(
            "With --company-career-page-probe, upsert the validated row as "
            "enabled only when validation succeeds"
        ),
    )
    parser.add_argument(
        "--company-career-page-sample-size",
        type=int,
        default=5,
        help="Number of jobs to fetch while validating a career-page URL",
    )
    parser.add_argument(
        "--populate-comeet-base-urls",
        action="store_true",
        help=(
            "Skip scraping and populate the company_comeet_job_urls table "
            "from the JSON file referenced by --output"
        ),
    )
    parser.add_argument(
        "--comeet-test-scrape",
        action="store_true",
        help=(
            "Fetch one company base URL from company_comeet_job_urls and "
            "scrape that Comeet company with detailed trace prints"
        ),
    )
    parser.add_argument(
        "--comeet-base-url",
        default=None,
        help=(
            "Optional specific company Comeet base URL to use with "
            "--comeet-test-scrape. When omitted, the most recently updated "
            "row is selected from company_comeet_job_urls"
        ),
    )
    parser.add_argument(
        "--comeet-scrape-all-israel",
        action="store_true",
        help=(
            "Run Comeet scraping for every company in company_comeet_job_urls, "
            "keep all Israel-based jobs, and print the job links at the end"
        ),
    )
    parser.add_argument(
        "--comeet-persist-all-israel",
        action="store_true",
        help=(
            "Run Comeet scraping for every company in company_comeet_job_urls, "
            "bulk persist all Israel-based jobs into jobs, and publish the "
            "scrape.finished event"
        ),
    )
    parser.add_argument(
        "--comeet-persist-all-india",
        action="store_true",
        help=(
            "Run Comeet scraping for every company in company_comeet_job_urls, "
            "keep all India-based jobs, and print the job links at the end. "
            "Persistence is currently disabled for this mode"
        ),
    )
    parser.add_argument(
        "--linkedin-scrape-india",
        action="store_true",
        help=(
            "Run a LinkedIn-only India scrape with geoId "
            f"{DEFAULT_LINKEDIN_INDIA_GEO_ID}, use a 60-minute recency filter, "
            "and print the results without JSON or DB persistence"
        ),
    )
    parser.add_argument(
        "--linkedin-scrape-india-sharded",
        action="store_true",
        help=(
            "Run a LinkedIn-only India scrape across metro shards in parallel, "
            "dedupe the merged jobs, and print the results without JSON or DB persistence"
        ),
    )
    parser.add_argument(
        "--linkedin-persist-india-sharded",
        action="store_true",
        help=(
            "Run a LinkedIn-only India sharded scrape across metro shards, "
            "hydrate descriptions, save the merged results to JSON, persist them "
            "into jobs, and publish the scrape.finished event"
        ),
    )
    parser.add_argument(
        "--linkedin-persist-india-sharded-scheduler",
        action="store_true",
        help=(
            "Run the India sharded LinkedIn persistence flow every hour on the "
            "round hour between 08:00 and 22:00 India time"
        ),
    )
    parser.add_argument(
        "--indeed-debug-search",
        action="store_true",
        help=(
            "Run an Indeed-only debug search for exactly 1 job, print the full "
            "search flow, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--indeed-persist",
        action="store_true",
        help=(
            "Run an Indeed-only persistence flow for Israel jobs from the last "
            "24 hours with no search term, save them to the DB, and publish "
            "a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--glassdoor-debug-search",
        action="store_true",
        help=(
            "Run a Glassdoor-only debug search for exactly 1 job, print the "
            "main flow, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--glassdoor-persist",
        action="store_true",
        help=(
            "Run a Glassdoor-only persistence flow for Israel jobs from the last "
            "3 days with no search term, save them to JSON/DB, and publish "
            "a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--glassdoor-persist-one",
        action="store_true",
        help=(
            "Run a Glassdoor-only persistence test for exactly 1 Israel job from "
            "the last 3 days, save it to JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--greenhouse-debug-search",
        action="store_true",
        help=(
            "Run a Greenhouse-only authenticated debug search for exactly 1 "
            "job, print the page fetch flow, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--greenhouse-persist",
        action="store_true",
        help=(
            "Run a Greenhouse-only authenticated fetch-all flow, save the "
            "results to JSON, bulk persist them into jobs, and publish the "
            "scrape.finished event"
        ),
    )
    parser.add_argument(
        "--amdocs-test-scrape",
        action="store_true",
        help=(
            "Run an Amdocs-only test scrape against the public Eightfold feed, "
            "print a preview, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--amdocs-persist",
        action="store_true",
        help=(
            "Run an Amdocs-only persistence flow against the public Eightfold feed, "
            "save the results to JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--amdocs-base-url",
        default=None,
        help=(
            "Optional Amdocs careers URL to bootstrap the Amdocs scrape flow. "
            f"Defaults to {DEFAULT_AMDOCS_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--apple-persist",
        action="store_true",
        help=(
            "Run an Apple Israel persistence flow, save the results to "
            "JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--apple-search-url",
        default=None,
        help=(
            "Optional Apple careers search URL to bootstrap the Apple Israel "
            f"scrape flow. Defaults to {DEFAULT_APPLE_SEARCH_URL}"
        ),
    )
    parser.add_argument(
        "--google-careers-persist",
        action="store_true",
        help=(
            "Run a Google Careers Israel persistence flow, save the results to "
            "JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--google-careers-url",
        default=None,
        help=(
            "Optional Google Careers results URL to bootstrap the Google Careers "
            f"Israel scrape flow. Defaults to {DEFAULT_GOOGLE_CAREERS_URL}"
        ),
    )
    parser.add_argument(
        "--microsoft-persist",
        action="store_true",
        help=(
            "Run a Microsoft Israel persistence flow, save the results to "
            "JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--microsoft-base-url",
        default=None,
        help=(
            "Optional Microsoft careers search URL to bootstrap the Microsoft "
            f"Israel scrape flow. Defaults to {DEFAULT_MICROSOFT_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--marvell-israel-test-scrape",
        action="store_true",
        help=(
            "Run a Marvell Israel Workday test scrape, print a preview plus one "
            "normalized JSON row, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--marvell-base-url",
        default=None,
        help=(
            "Optional Marvell Workday careers URL to bootstrap the Marvell Israel "
            f"scrape flow. Defaults to {DEFAULT_MARVELL_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--marvell-persist",
        action="store_true",
        help=(
            "Run a Marvell Israel Workday persistence flow, save the results to "
            "JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--redhat-test-scrape",
        action="store_true",
        help=(
            "Run a Red Hat Israel Workday test scrape, print exactly one "
            "normalized job, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--redhat-base-url",
        default=None,
        help=(
            "Optional Red Hat Workday careers URL to bootstrap the Red Hat Israel "
            f"scrape flow. Defaults to {DEFAULT_REDHAT_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--redhat-persist",
        action="store_true",
        help=(
            "Run a Red Hat Israel Workday persistence flow, save all Israel "
            "results to JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--varonis-test-scrape",
        action="store_true",
        help=(
            "Run a Varonis Israel test scrape, print exactly one normalized "
            "job, and skip JSON/DB persistence"
        ),
    )
    parser.add_argument(
        "--varonis-base-url",
        default=None,
        help=(
            "Optional Varonis careers base URL to bootstrap the Varonis scrape "
            f"flow. Defaults to {DEFAULT_VARONIS_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--varonis-persist",
        action="store_true",
        help=(
            "Run a Varonis Israel persistence flow, save all Israel results "
            "to JSON/DB, and publish a scrape.finished event"
        ),
    )
    parser.add_argument(
        "--country-indeed",
        default="Israel",
        help="Indeed/Glassdoor country override for site-specific modes",
    )
    parser.add_argument(
        "--greenhouse-location-name",
        default=None,
        help=(
            "Greenhouse search location label. Defaults to --location and "
            "auto-fills the remaining search coordinates for Israel"
        ),
    )
    parser.add_argument(
        "--greenhouse-lat",
        type=float,
        default=DEFAULT_GREENHOUSE_LAT,
        help="Greenhouse search latitude",
    )
    parser.add_argument(
        "--greenhouse-lon",
        type=float,
        default=DEFAULT_GREENHOUSE_LON,
        help="Greenhouse search longitude",
    )
    parser.add_argument(
        "--greenhouse-location-type",
        default=DEFAULT_GREENHOUSE_LOCATION_TYPE,
        help="Greenhouse search location_type value",
    )
    parser.add_argument(
        "--greenhouse-country-short-name",
        default=DEFAULT_GREENHOUSE_COUNTRY_SHORT_NAME,
        help="Greenhouse search country_short_name value",
    )
    parser.add_argument(
        "--greenhouse-date-posted",
        default=DEFAULT_GREENHOUSE_DATE_POSTED,
        help="Greenhouse search date_posted value",
    )
    parser.add_argument(
        "--execution-mode",
        choices=[mode.value for mode in LinkedInScrapeMode],
        default=LinkedInScrapeMode.DEFAULT.value,
        help=(
            "LinkedIn scrape mode. Use until-last-page to keep requesting "
            "start=X until the seeMoreJobPostings endpoint returns no jobs"
        ),
    )
    parser.add_argument(
        "--num-of-min",
        type=int,
        default=None,
        help=(
            "Time filter in minutes for --execution-mode until-last-page. "
            "Converted to the correct f_TPR value"
        ),
    )
    parser.add_argument(
        "--linkedin-page-delay-min",
        type=float,
        default=None,
        help=(
            "Minimum seconds to wait between successful LinkedIn search page "
            "requests. When omitted, JobSpy uses the built-in default."
        ),
    )
    parser.add_argument(
        "--linkedin-page-delay-max",
        type=float,
        default=None,
        help=(
            "Maximum seconds to wait between successful LinkedIn search page "
            "requests. When omitted, JobSpy uses the built-in default."
        ),
    )
    parser.add_argument(
        "--scheduler",
        action="store_true",
        help=(
            "Run scheduler mode. Scheduler waits for the next hh:30 Israel "
            "time between 07:30 and 22:30, uses a 1440-minute scrape window "
            "only for the scheduled 07:30 LinkedIn run, then uses a "
            "60-minute window for later hourly LinkedIn runs, also runs "
            "Indeed, Glassdoor, Amdocs, Apple, Microsoft, Marvell, Red Hat, "
            "and Varonis persistence on each hourly tick, and runs Comeet "
            "Israel plus Greenhouse persistence every 3 hours"
        ),
    )
    parser.add_argument(
        "--schedule-every-minutes",
        type=int,
        default=MIN_LINKEDIN_SCHEDULER_INTERVAL_MINUTES,
        help=(
            "Deprecated in scheduler mode. The scheduler now always runs "
            "hourly at hh:30 Israel time between 07:30 and 22:30. The first "
            "scheduled 07:30 run uses 1440 minutes; later scheduled runs use "
            "60 minutes"
        ),
    )
    parser.add_argument(
        "--print-all",
        action="store_true",
        help="Print all fetched rows instead of only the first 20",
    )
    parser.add_argument(
        "--print-html",
        action="store_true",
        help="Print raw response HTML for LinkedIn inspect modes",
    )
    parser.add_argument(
        "--job-url",
        default=None,
        help="LinkedIn job URL to inspect with --execution-mode inspect-single-job",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="LinkedIn job ID to inspect with --execution-mode inspect-single-job",
    )
    parser.add_argument(
        "--profile-url",
        default=None,
        help=(
            "LinkedIn profile URL to inspect with --execution-mode "
            "inspect-single-profile"
        ),
    )
    parser.add_argument(
        "--linkedin-cookie",
        action="append",
        default=[],
        help=(
            "Repeatable LinkedIn session cookie in NAME=VALUE form. "
            "Example: --linkedin-cookie \"li_at=...\" --linkedin-cookie "
            "\"JSESSIONID=...\""
        ),
    )
    parser.add_argument(
        "--linkedin-cookie-header",
        default=os.getenv("LINKEDIN_COOKIE_HEADER"),
        help=(
            "Raw LinkedIn Cookie header value. Can also be provided with the "
            "LINKEDIN_COOKIE_HEADER environment variable"
        ),
    )
    parser.add_argument(
        "--linkedin-cookie-file",
        default=os.getenv("LINKEDIN_COOKIE_FILE"),
        help=(
            "Path to a file containing LinkedIn cookies. Supports a raw Cookie "
            "header or one NAME=VALUE entry per line. Scheduler mode rereads "
            "this file on each run"
        ),
    )
    parser.add_argument(
        "--linkedin-li-at",
        default=os.getenv("LINKEDIN_LI_AT"),
        help=(
            "LinkedIn li_at session cookie. Can also be provided with the "
            "LINKEDIN_LI_AT environment variable"
        ),
    )
    parser.add_argument(
        "--linkedin-jsessionid",
        default=os.getenv("LINKEDIN_JSESSIONID"),
        help=(
            "LinkedIn JSESSIONID cookie. Can also be provided with the "
            "LINKEDIN_JSESSIONID environment variable"
        ),
    )
    parser.add_argument(
        "--greenhouse-cookie",
        action="append",
        default=[],
        help=(
            "Repeatable Greenhouse session cookie in NAME=VALUE form. "
            'Example: --greenhouse-cookie "_session_id=..." '
            '--greenhouse-cookie "MYGREENHOUSE-XSRF-TOKEN=..."'
        ),
    )
    parser.add_argument(
        "--greenhouse-cookie-header",
        default=os.getenv("GREENHOUSE_COOKIE_HEADER"),
        help=(
            "Raw Greenhouse Cookie header value. Can also be provided with "
            "the GREENHOUSE_COOKIE_HEADER environment variable"
        ),
    )
    parser.add_argument(
        "--greenhouse-cookie-file",
        default=os.getenv("GREENHOUSE_COOKIE_FILE"),
        help=(
            "Path to a file containing Greenhouse cookies. Supports a raw "
            "Cookie header or one NAME=VALUE entry per line. Scheduler mode "
            "defaults to the bundled greenhouse cookie file when omitted"
        ),
    )
    parser.add_argument(
        "--greenhouse-xsrf-token",
        default=os.getenv("GREENHOUSE_XSRF_TOKEN"),
        help=(
            "Optional Greenhouse XSRF token override. Defaults to the "
            "MYGREENHOUSE-XSRF-TOKEN or XSRF-TOKEN cookie value"
        ),
    )
    return parser


def _parse_cookie_assignment(raw_value: str) -> tuple[str, str]:
    name, separator, value = (raw_value or "").partition("=")
    if not separator:
        raise ValueError(f"Invalid cookie value '{raw_value}'. Expected NAME=VALUE")

    cookie_name = name.strip()
    cookie_value = value.strip()
    if not cookie_name or not cookie_value:
        raise ValueError(f"Invalid cookie value '{raw_value}'. Expected NAME=VALUE")

    return cookie_name, cookie_value


def _merge_cookie_text(
    cookies: dict[str, str],
    raw_cookie_text: str | None,
) -> None:
    if not raw_cookie_text:
        return

    for raw_line in raw_cookie_text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith(("cookie:", "set-cookie:")):
            line = line.split(":", 1)[1].strip()
        if not line:
            continue

        for cookie_part in line.split(";"):
            cookie_part = cookie_part.strip()
            if not cookie_part or "=" not in cookie_part:
                continue

            cookie_name, cookie_value = _parse_cookie_assignment(cookie_part)
            if cookie_name.lower() in SET_COOKIE_ATTRIBUTES:
                continue
            cookies[cookie_name] = cookie_value


def _load_cookie_file(cookie_file: str | None, *, label: str) -> str | None:
    cookie_file_path = (cookie_file or "").strip()
    if not cookie_file_path:
        return None

    path = Path(cookie_file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{label} cookie file not found: {path}")

    return path.read_text(encoding="utf-8")


def _build_linkedin_auth_cookies(args: argparse.Namespace) -> dict[str, str]:
    cookies: dict[str, str] = {}

    _merge_cookie_text(
        cookies,
        _load_cookie_file(
            getattr(args, "linkedin_cookie_file", None),
            label="LinkedIn",
        ),
    )
    _merge_cookie_text(cookies, args.linkedin_cookie_header)

    for raw_cookie in args.linkedin_cookie:
        cookie_name, cookie_value = _parse_cookie_assignment(raw_cookie)
        cookies[cookie_name] = cookie_value

    explicit_cookie_values = {
        "li_at": args.linkedin_li_at,
        "JSESSIONID": args.linkedin_jsessionid,
    }
    for cookie_name, cookie_value in explicit_cookie_values.items():
        normalized_cookie_value = (cookie_value or "").strip()
        if normalized_cookie_value:
            cookies[cookie_name] = normalized_cookie_value

    return {name: value for name, value in cookies.items() if name and value}


def _build_linkedin_auth_context(
    args: argparse.Namespace,
) -> tuple[dict[str, str], str]:
    return resolve_linkedin_auth_context(
        _build_linkedin_auth_cookies(args),
        builtin_cookie_loader=load_linkedin_builtin_cookies,
        browser_cookie_loader=load_linkedin_chromium_cookies,
    )


def _format_linkedin_auth_cookies(cookies: dict[str, str]) -> str:
    if not cookies:
        return "disabled"
    return ", ".join(
        f"{cookie_name}={cookie_value}"
        for cookie_name, cookie_value in sorted(cookies.items())
    )


def _print_linkedin_auth_context(
    cookies: dict[str, str],
    auth_source: str,
    *,
    context: str,
) -> None:
    print(f"LinkedIn auth context: {context}")
    print(f"LinkedIn auth cookies: {_format_linkedin_auth_cookies(cookies)}")
    print(f"LinkedIn auth source: {auth_source}")


def _resolve_and_print_linkedin_auth_context(
    args: argparse.Namespace,
    *,
    context: str,
) -> tuple[dict[str, str], str]:
    cookies, auth_source = _build_linkedin_auth_context(args)
    _print_linkedin_auth_context(cookies, auth_source, context=context)
    return cookies, auth_source


def _should_print_linkedin_auth_at_startup(args: argparse.Namespace) -> bool:
    if any(
        (
            getattr(args, "scheduler", False),
            getattr(args, "linkedin_scrape_india", False),
            getattr(args, "linkedin_scrape_india_sharded", False),
            getattr(args, "linkedin_persist_india_sharded", False),
            getattr(args, "linkedin_persist_india_sharded_scheduler", False),
        )
    ):
        return True

    if any(
        (
            getattr(args, "indeed_debug_search", False),
            getattr(args, "indeed_persist", False),
            getattr(args, "glassdoor_debug_search", False),
            getattr(args, "glassdoor_persist", False),
            getattr(args, "glassdoor_persist_one", False),
            getattr(args, "company_career_pages", False),
            getattr(args, "company_career_pages_now", False),
            getattr(args, "company_career_pages_table_only", False),
            getattr(args, "company_career_page_probe", False),
            getattr(args, "greenhouse_debug_search", False),
            getattr(args, "greenhouse_persist", False),
            getattr(args, "populate_comeet_base_urls", False),
            getattr(args, "comeet_test_scrape", False),
            getattr(args, "comeet_scrape_all_israel", False),
            getattr(args, "comeet_persist_all_israel", False),
            getattr(args, "comeet_persist_all_india", False),
            getattr(args, "amdocs_test_scrape", False),
            getattr(args, "amdocs_persist", False),
            getattr(args, "apple_persist", False),
            getattr(args, "google_careers_persist", False),
            getattr(args, "microsoft_persist", False),
            getattr(args, "marvell_israel_test_scrape", False),
            getattr(args, "marvell_persist", False),
            getattr(args, "redhat_test_scrape", False),
            getattr(args, "redhat_persist", False),
            getattr(args, "varonis_test_scrape", False),
            getattr(args, "varonis_persist", False),
        )
    ):
        return False

    return True


def _build_greenhouse_auth_cookies(args: argparse.Namespace) -> dict[str, str]:
    cookies: dict[str, str] = {}

    _merge_cookie_text(
        cookies,
        _load_cookie_file(
            getattr(args, "greenhouse_cookie_file", None),
            label="Greenhouse",
        ),
    )
    _merge_cookie_text(cookies, args.greenhouse_cookie_header)

    for raw_cookie in args.greenhouse_cookie:
        cookie_name, cookie_value = _parse_cookie_assignment(raw_cookie)
        cookies[cookie_name] = cookie_value

    return {name: value for name, value in cookies.items() if name and value}


def _resolve_greenhouse_xsrf_token(
    args: argparse.Namespace,
    auth_cookies: dict[str, str],
) -> str | None:
    explicit_token = (args.greenhouse_xsrf_token or "").strip()
    if explicit_token:
        return explicit_token

    for cookie_name in ("MYGREENHOUSE-XSRF-TOKEN", "XSRF-TOKEN"):
        cookie_value = (auth_cookies.get(cookie_name) or "").strip()
        if cookie_value:
            return cookie_value
    return None


def save_jobs_to_json(output_path: Path, jobs) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jobs.to_json(
        output_path,
        orient="records",
        date_format="iso",
        force_ascii=False,
        indent=2,
    )


def _resolve_output_path(raw_output: str, *, site: str) -> Path:
    resolved_output = raw_output
    if site == "indeed" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_INDEED_OUTPUT
    if site == "glassdoor" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_GLASSDOOR_OUTPUT
    if site == "comeet" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_COMEET_OUTPUT
    if site == "greenhouse" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_GREENHOUSE_OUTPUT
    if site == "amdocs" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_AMDOCS_OUTPUT
    if site == "apple" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_APPLE_OUTPUT
    if site == "google_careers" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_GOOGLE_CAREERS_OUTPUT
    if site == "microsoft" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_MICROSOFT_OUTPUT
    if site == "redhat" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_REDHAT_OUTPUT
    if site == "marvell" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_MARVELL_OUTPUT
    if site == "varonis" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_VARONIS_OUTPUT
    if site == "company_career_pages" and raw_output == DEFAULT_LINKEDIN_OUTPUT:
        resolved_output = DEFAULT_COMPANY_CAREER_PAGES_OUTPUT
    return Path(resolved_output).expanduser().resolve()


def _print_console_safe(text: str) -> None:
    stdout_encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(stdout_encoding, errors="backslashreplace").decode(stdout_encoding))


def _print_compact_db_summary(db_summary: dict[str, Any] | None) -> None:
    if db_summary is None:
        return
    print(
        "DB upsert summary: "
        f"inserted={db_summary.get('inserted', 'n/a')} "
        f"updated={db_summary.get('updated', 'n/a')}"
    )
    _print_updated_change_summary(db_summary)


def _print_updated_change_summary(db_summary: dict[str, Any] | None) -> None:
    if not isinstance(db_summary, dict):
        return

    updated_changes = db_summary.get("updated_changes")
    updated_fields = [
        str(field_name)
        for field_name in db_summary.get("updated_fields", [])
        if field_name is not None
    ]
    if not isinstance(updated_changes, list) or not updated_changes:
        if updated_fields:
            print(f"Updated fields in run: {', '.join(updated_fields)}")
        return

    print("Updated job field changes:")
    for change in updated_changes:
        if not isinstance(change, dict):
            continue
        job_id = change.get("job_id", "n/a")
        field_name = change.get("field", "n/a")
        before_value = json.dumps(
            change.get("before"),
            ensure_ascii=False,
            default=str,
        )
        after_value = json.dumps(
            change.get("after"),
            ensure_ascii=False,
            default=str,
        )
        print(
            f"  job_id={job_id} "
            f"field={field_name} "
            f"before={before_value} "
            f"after={after_value}"
        )
    if updated_fields:
        print(f"Updated fields in run: {', '.join(updated_fields)}")


def _safe_config_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def _safe_config_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _safe_config_str(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _deep_merge_config(
    defaults: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in overrides.items():
        existing_value = merged.get(key)
        if isinstance(existing_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_config(existing_value, value)
        else:
            merged[key] = value
    return merged


def _is_nice_company_career_page_row(
    company_record: dict[str, Any],
    configured_scraper_site: str,
) -> bool:
    if configured_scraper_site.casefold() == "nice":
        return True

    company_key = _safe_config_str(company_record.get("company_key"))
    if company_key and company_key.casefold() == "nice":
        return True

    company_name = _safe_config_str(company_record.get("company_name"))
    return bool(
        company_name
        and company_name.casefold() in {"nice", "nice ltd", "nice ltd.", "nice systems"}
    )


def _apply_company_career_page_special_config(
    company_record: dict[str, Any],
    configured_scraper_site: str,
    career_page_url: str,
    extra_params: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    if not _is_nice_company_career_page_row(company_record, configured_scraper_site):
        return configured_scraper_site, career_page_url, extra_params

    defaults = {"json_feed_config": NICE_JSON_FEED_CONFIG}
    return (
        "json_feed",
        NICE_GREENHOUSE_JOBS_URL,
        _deep_merge_config(defaults, extra_params),
    )


def _build_company_career_page_scrape_kwargs(
    company_record: dict[str, Any],
) -> dict[str, Any]:
    configured_scraper_site = _safe_config_str(company_record.get("scraper_site"))
    career_page_url = _safe_config_str(company_record.get("career_page_url"))
    original_career_page_url = career_page_url
    resolved_fetch_url = _safe_config_str(company_record.get("resolved_fetch_url"))
    if not configured_scraper_site:
        raise ValueError("company_career_pages row is missing scraper_site")
    if not career_page_url:
        raise ValueError("company_career_pages row is missing career_page_url")

    extra_params = company_record.get("extra_params") or {}
    if not isinstance(extra_params, dict):
        extra_params = {}

    configured_scraper_site, career_page_url, extra_params = (
        _apply_company_career_page_special_config(
            company_record,
            configured_scraper_site,
            career_page_url,
            extra_params,
        )
    )
    if resolved_fetch_url and resolved_fetch_url != original_career_page_url:
        career_page_url = resolved_fetch_url
    scraper_site = COMPANY_CAREER_PAGE_SCRAPER_SITE_ALIASES.get(
        configured_scraper_site,
        configured_scraper_site,
    )
    url_kwarg = COMPANY_CAREER_PAGE_URL_KWARG_BY_SITE.get(scraper_site)
    if not url_kwarg:
        raise ValueError(
            "Unsupported company_career_pages "
            f"scraper_site={configured_scraper_site!r}"
        )

    description_limit = company_record.get("description_limit")
    results_wanted = _safe_config_int(company_record.get("results_wanted"))
    request_timeout = _safe_config_int(company_record.get("request_timeout"))

    kwargs: dict[str, Any] = {
        "site_name": scraper_site,
        "search_term": _safe_config_str(company_record.get("search_term")),
        "location": _safe_config_str(company_record.get("location")),
        "results_wanted": results_wanted if results_wanted is not None else 0,
        "country_indeed": _safe_config_str(company_record.get("country_indeed"))
        or "Israel",
        "description_format": _safe_config_str(
            company_record.get("description_format")
        )
        or "markdown",
        "description_limit": description_limit,
        "verbose": 0,
        url_kwarg: career_page_url,
    }
    if request_timeout is not None:
        kwargs["request_timeout"] = request_timeout
    kwargs.update(extra_params)
    return kwargs


def _stamp_company_career_page_metadata(jobs, company_record: dict[str, Any]):
    if jobs is None or getattr(jobs, "empty", False):
        return jobs
    jobs = jobs.copy()
    company_source = _safe_config_str(
        company_record.get("company_name")
    ) or _safe_config_str(company_record.get("company_key"))
    if company_source:
        jobs["source"] = company_source
    jobs["direct_company_career_page_id"] = company_record.get("id")
    jobs["direct_company_career_page_key"] = company_record.get("company_key")
    jobs["direct_company_career_page_company"] = company_record.get("company_name")
    return jobs


def _scrape_company_career_page_row(
    company_record: dict[str, Any],
    args: argparse.Namespace,
):
    kwargs = _build_company_career_page_scrape_kwargs(company_record)
    company_name = company_record.get("company_name") or company_record.get(
        "company_key"
    )
    print(
        "Fetching configured company career page: "
        f"{company_name} (site={kwargs['site_name']})"
    )
    jobs = scrape_jobs(**kwargs)
    jobs = _stamp_company_career_page_metadata(jobs, company_record)
    return jobs, {
        "company_key": company_record.get("company_key"),
        "company_name": company_record.get("company_name"),
        "scraper_site": kwargs["site_name"],
        "jobs": 0 if jobs is None else len(jobs),
    }


def _scrape_company_career_page_rows(
    company_records: list[dict[str, Any]],
    args: argparse.Namespace,
):
    import pandas as pd

    frames = []
    row_summaries: list[dict[str, Any]] = []
    failed = 0
    for index, company_record in enumerate(company_records, start=1):
        try:
            jobs, row_summary = _scrape_company_career_page_row(
                company_record,
                args,
            )
        except Exception as exc:
            failed += 1
            row_summary = {
                "company_key": company_record.get("company_key"),
                "company_name": company_record.get("company_name"),
                "scraper_site": company_record.get("scraper_site"),
                "jobs": 0,
                "error": str(exc),
            }
            print(
                f"[{index}/{len(company_records)}] "
                f"{company_record.get('company_name') or company_record.get('company_key')} "
                f"failed: {exc}"
            )
            row_summaries.append(row_summary)
            continue

        row_summaries.append(row_summary)
        if jobs is not None and not getattr(jobs, "empty", False):
            frames.append(jobs)
        print(
            f"[{index}/{len(company_records)}] "
            f"{row_summary['company_name'] or row_summary['company_key']} "
            f"jobs={row_summary['jobs']}"
        )

    combined_jobs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined_jobs, {
        "companies": len(company_records),
        "companies_with_jobs": sum(
            1 for summary in row_summaries if summary["jobs"] > 0
        ),
        "failed": failed,
        "jobs": len(combined_jobs),
        "rows": row_summaries,
    }


def _resolve_company_career_pages_board_hours_old(args: argparse.Namespace) -> int:
    if getattr(args, "num_of_min", None) is not None:
        return _get_scheduler_hours_old(int(args.num_of_min))

    hours_old = getattr(args, "hours_old", None)
    return int(hours_old) if hours_old is not None else 24


def _scrape_company_career_pages_linkedin_board(args: argparse.Namespace):
    linkedin_auth_cookies, _ = _build_linkedin_auth_context(args)
    linkedin_geo_id = _resolve_linkedin_geo_id(args)
    scrape_verbose = (
        2
        if args.execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE.value
        else 0
    )
    description_limit = (
        None
        if (
            args.fetch_description
            and args.execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE.value
        )
        else args.results if args.fetch_description else 0
    )

    return scrape_jobs(
        site_name="linkedin",
        search_term=args.search_term,
        location=args.location,
        distance=args.distance,
        results_wanted=args.results,
        hours_old=args.hours_old,
        linkedin_fetch_description=args.fetch_description,
        linkedin_geo_id=linkedin_geo_id,
        linkedin_page_delay_min=args.linkedin_page_delay_min,
        linkedin_page_delay_max=args.linkedin_page_delay_max,
        linkedin_execution_mode=args.execution_mode,
        num_of_min=args.num_of_min,
        description_limit=description_limit,
        verbose=scrape_verbose,
        linkedin_auth_cookies=linkedin_auth_cookies,
    )


def _scrape_company_career_pages_indeed_board(args: argparse.Namespace):
    board_args = _build_scheduler_indeed_args(
        args,
        hours_old=_resolve_company_career_pages_board_hours_old(args),
    )
    effective_distance = board_args.distance if board_args.distance is not None else 50
    return scrape_jobs(
        site_name="indeed",
        search_term=None,
        location=board_args.location,
        distance=effective_distance,
        results_wanted=board_args.results,
        hours_old=board_args.hours_old,
        country_indeed=board_args.country_indeed,
        description_limit=None,
        verbose=0,
    )


def _scrape_company_career_pages_glassdoor_board(args: argparse.Namespace):
    board_args = _build_scheduler_glassdoor_args(args)
    return scrape_jobs(
        site_name="glassdoor",
        search_term=None,
        location=board_args.location,
        results_wanted=board_args.results,
        hours_old=board_args.hours_old,
        country_indeed=board_args.country_indeed,
        description_limit=None,
        verbose=2,
    )


def _scrape_company_career_pages_comeet_board(args: argparse.Namespace):
    import pandas as pd

    from jobspy.jobs_table import list_company_comeet_job_urls

    company_records = list_company_comeet_job_urls()
    if not company_records:
        print("Skipping job-board jobs: Comeet (company_comeet_job_urls is empty)")
        return pd.DataFrame()

    jobs, _, scrape_summary = _collect_comeet_israel_jobs(company_records)
    print(
        "Comeet job-board collection summary: "
        f"companies={scrape_summary['companies']} "
        f"companies_with_jobs={scrape_summary['companies_with_jobs']} "
        f"failed={scrape_summary['failed']} "
        f"job_links={scrape_summary['job_links']}"
    )
    return jobs


def _scrape_company_career_pages_greenhouse_board(args: argparse.Namespace):
    board_args = _build_scheduler_greenhouse_args(args)
    greenhouse_auth_cookies = _build_greenhouse_auth_cookies(board_args)
    greenhouse_xsrf_token = _resolve_greenhouse_xsrf_token(
        board_args,
        greenhouse_auth_cookies,
    )
    if not greenhouse_auth_cookies:
        raise ValueError(
            "Greenhouse job-board scrape requires authenticated cookies. Provide "
            "--greenhouse-cookie, --greenhouse-cookie-header, or "
            "--greenhouse-cookie-file."
        )

    effective_location_name = board_args.greenhouse_location_name or board_args.location
    return scrape_jobs(
        site_name="greenhouse",
        search_term=None,
        location=board_args.location,
        results_wanted=1,
        country_indeed=board_args.country_indeed,
        description_limit=None,
        verbose=2,
        greenhouse_auth_cookies=greenhouse_auth_cookies,
        greenhouse_xsrf_token=greenhouse_xsrf_token,
        greenhouse_location_name=effective_location_name,
        greenhouse_lat=board_args.greenhouse_lat,
        greenhouse_lon=board_args.greenhouse_lon,
        greenhouse_location_type=board_args.greenhouse_location_type,
        greenhouse_country_short_name=board_args.greenhouse_country_short_name,
        greenhouse_date_posted=board_args.greenhouse_date_posted,
        greenhouse_execution_mode=GreenhouseScrapeMode.UNTIL_LAST_PAGE,
        greenhouse_debug_trace=False,
    )


def _scrape_company_career_pages_job_board_rows(args: argparse.Namespace):
    import pandas as pd

    board_scrapers: list[tuple[str, str, Callable[[], Any]]] = [
        (
            "Indeed",
            "indeed",
            lambda: _scrape_company_career_pages_indeed_board(args),
        ),
        (
            "Glassdoor",
            "glassdoor",
            lambda: _scrape_company_career_pages_glassdoor_board(args),
        ),
        (
            "Comeet",
            "comeet",
            lambda: _scrape_company_career_pages_comeet_board(args),
        ),
        (
            "Greenhouse",
            "greenhouse",
            lambda: _scrape_company_career_pages_greenhouse_board(args),
        ),
    ]

    frames = []
    row_summaries: list[dict[str, Any]] = []
    failed = 0
    for label, site, scrape_board in board_scrapers:
        print(f"Fetching job-board jobs: {label}")
        try:
            jobs = scrape_board()
        except Exception as exc:
            failed += 1
            row_summaries.append(
                {
                    "site": site,
                    "jobs": 0,
                    "error": str(exc),
                }
            )
            print(f"{label} job-board scrape failed: {exc}")
            continue

        job_count = 0 if jobs is None else len(jobs)
        row_summaries.append({"site": site, "jobs": job_count})
        if jobs is not None and not getattr(jobs, "empty", False):
            frames.append(jobs)
        print(f"{label} job-board jobs={job_count}")

    combined_jobs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined_jobs, {
        "boards": len(board_scrapers),
        "failed": failed,
        "jobs": len(combined_jobs),
        "rows": row_summaries,
    }


def _call_with_output_controls(
    callback: Callable[..., Any],
    *args,
    suppress_stdout: bool = False,
    suppress_logging: bool = False,
    **kwargs,
) -> Any:
    previous_disable_level = logging.root.manager.disable
    try:
        if suppress_logging:
            logging.disable(logging.CRITICAL)
        if suppress_stdout:
            with redirect_stdout(io.StringIO()):
                return callback(*args, **kwargs)
        return callback(*args, **kwargs)
    finally:
        if suppress_logging:
            logging.disable(previous_disable_level)


def _should_skip_jobs_preview(args: argparse.Namespace, jobs: object | None) -> bool:
    return bool(
        jobs is None
        or getattr(jobs, "empty", False)
        or getattr(args, "suppress_preview", False)
        or getattr(args, "save_db", False)
        or getattr(args, "populate_only", False)
    )


def _country_supports_glassdoor(country_name: str) -> bool:
    try:
        Country.from_string(country_name).get_glassdoor_url()
        return True
    except Exception:
        return False


def _count_jobs_for_site(jobs, site: str) -> int | None:
    if jobs is None:
        return None

    try:
        columns = getattr(jobs, "columns", [])
        if "site" in columns:
            site_values = jobs["site"]
            matches = site_values == site
            if hasattr(matches, "sum"):
                return int(matches.sum())
    except Exception:
        pass

    try:
        return len(jobs)
    except Exception:
        return None


def _resolve_linkedin_geo_id(args: argparse.Namespace) -> int | None:
    if getattr(args, "linkedin_geo_id", None) is not None:
        return int(args.linkedin_geo_id)

    location = (getattr(args, "location", None) or "").strip().lower()
    if location == "israel":
        return DEFAULT_LINKEDIN_ISRAEL_GEO_ID

    return None


def _get_linkedin_india_shards() -> list[dict[str, Any]]:
    return [dict(shard) for shard in LINKEDIN_INDIA_SHARDS]


def _append_linkedin_shard_metadata(jobs, shard: dict[str, Any]):
    if jobs is None or getattr(jobs, "empty", True):
        return jobs

    jobs = jobs.copy()
    jobs["search_shard"] = shard["name"]
    jobs["search_location"] = shard["location"]
    jobs["search_is_remote"] = bool(shard.get("is_remote", False))
    return jobs


def _dedupe_sharded_linkedin_jobs(jobs):
    import pandas as pd

    if jobs is None or getattr(jobs, "empty", True):
        return jobs, {"raw_rows": 0, "unique_rows": 0, "duplicates_removed": 0}

    dedupe_key = None
    for column in ("job_url", "id", "apply_url"):
        if column not in jobs.columns:
            continue

        column_values = jobs[column].fillna("").astype(str).str.strip()
        if dedupe_key is None:
            dedupe_key = column_values
        else:
            dedupe_key = dedupe_key.where(dedupe_key != "", column_values)

    if dedupe_key is None:
        dedupe_key = pd.Series(
            [f"row-{index}" for index in range(len(jobs))],
            index=jobs.index,
            dtype="object",
        )
    else:
        dedupe_key = dedupe_key.where(
            dedupe_key != "",
            pd.Series(
                [f"row-{index}" for index in range(len(jobs))],
                index=jobs.index,
                dtype="object",
            ),
        )

    raw_rows = len(jobs)
    deduped_jobs = (
        jobs.assign(_dedupe_key=dedupe_key)
        .drop_duplicates(subset=["_dedupe_key"])
        .drop(columns=["_dedupe_key"])
        .reset_index(drop=True)
    )
    unique_rows = len(deduped_jobs)
    return deduped_jobs, {
        "raw_rows": raw_rows,
        "unique_rows": unique_rows,
        "duplicates_removed": raw_rows - unique_rows,
    }


def _print_linkedin_jobs_preview(jobs, *, include_search_shard: bool = False) -> None:
    if jobs is None or jobs.empty:
        return

    preview_columns = []
    if include_search_shard and "search_shard" in jobs.columns:
        preview_columns.append("search_shard")
    preview_columns.extend(
        column
        for column in [
            "site",
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
        ]
        if column in jobs.columns and column not in preview_columns
    )
    preview_df = jobs[preview_columns].head(20)
    _print_console_safe(preview_df.to_string(index=False))


def _build_linkedin_description_scraper(
    auth_cookies: dict[str, str] | None = None,
):
    from jobspy.linkedin import LinkedIn

    scraper = LinkedIn(auth_cookies=auth_cookies)
    scraper.scraper_input = ScraperInput(
        site_type=[Site.LINKEDIN],
        country=Country.INDIA,
        description_format=DescriptionFormat.MARKDOWN,
        linkedin_fetch_description=True,
        linkedin_execution_mode=LinkedInScrapeMode.INSPECT_SINGLE_JOB,
    )
    return scraper


def _hydrate_linkedin_description_batch(
    batch: list[tuple[int, str]],
    *,
    auth_cookies: dict[str, str] | None = None,
) -> tuple[list[tuple[int, dict[str, Any]]], dict[str, int]]:
    scraper = _build_linkedin_description_scraper(auth_cookies=auth_cookies)
    updates: list[tuple[int, dict[str, Any]]] = []
    hydrated = 0
    failed = 0

    for row_index, job_url in batch:
        normalized_job_url = scraper._normalize_linkedin_job_url(job_url)
        job_id = scraper._extract_job_id(normalized_job_url)
        if not normalized_job_url or not job_id:
            failed += 1
            continue

        try:
            job_details = scraper._get_job_details(job_id) or {}
        except Exception:
            failed += 1
            continue

        row_updates: dict[str, Any] = {}
        if description := job_details.get("description"):
            row_updates["description"] = description
        if canonical_job_url := job_details.get("job_url"):
            row_updates["job_url"] = canonical_job_url
        if apply_url := job_details.get("apply_url"):
            row_updates["apply_url"] = apply_url
        if job_url_direct := job_details.get("job_url_direct"):
            row_updates["job_url_direct"] = job_url_direct
        if "applications_count" in job_details:
            row_updates["applications_count"] = job_details.get("applications_count")
        if job_level := job_details.get("job_level"):
            row_updates["job_level"] = (job_level or "").lower()
        if company_industry := job_details.get("company_industry"):
            row_updates["company_industry"] = company_industry
        if job_function := job_details.get("job_function"):
            row_updates["job_function"] = job_function

        if row_updates:
            hydrated += 1
            updates.append((row_index, row_updates))
        else:
            failed += 1

    return updates, {"hydrated": hydrated, "failed": failed}


def _hydrate_linkedin_jobs_with_descriptions(
    jobs,
    worker_count: int = DEFAULT_LINKEDIN_DESCRIPTION_WORKERS,
    *,
    auth_cookies: dict[str, str] | None = None,
) -> tuple[object, dict[str, Any]]:
    if jobs is None or getattr(jobs, "empty", True):
        return jobs, {"requested": 0, "hydrated": 0, "failed": 0}
    if "job_url" not in jobs.columns:
        return jobs, {"requested": 0, "hydrated": 0, "failed": 0}

    jobs = jobs.copy()
    rows_to_hydrate = []
    for row_index, row in jobs.iterrows():
        job_url = str(row.get("job_url") or "").strip()
        if not job_url:
            continue
        rows_to_hydrate.append((int(row_index), job_url))

    if not rows_to_hydrate:
        return jobs, {"requested": 0, "hydrated": 0, "failed": 0}

    effective_workers = max(1, min(worker_count, len(rows_to_hydrate)))
    chunk_size = max(1, (len(rows_to_hydrate) + effective_workers - 1) // effective_workers)
    batches = [
        rows_to_hydrate[index : index + chunk_size]
        for index in range(0, len(rows_to_hydrate), chunk_size)
    ]

    hydrated = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        future_to_batch_size = {
            executor.submit(
                _hydrate_linkedin_description_batch,
                batch,
                auth_cookies=auth_cookies,
            ): len(batch)
            for batch in batches
        }
        for future in as_completed(future_to_batch_size):
            try:
                batch_updates, batch_summary = future.result()
            except Exception:
                failed += future_to_batch_size[future]
                continue
            hydrated += batch_summary["hydrated"]
            failed += batch_summary["failed"]
            for row_index, row_updates in batch_updates:
                for column_name, value in row_updates.items():
                    jobs.at[row_index, column_name] = value

    return jobs, {
        "requested": len(rows_to_hydrate),
        "hydrated": hydrated,
        "failed": failed,
    }


def _scrape_linkedin_india_shard(
    shard: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> tuple[object, dict[str, Any]]:
    started_at = time.perf_counter()
    linkedin_auth_cookies, _ = _build_linkedin_auth_context(args)
    jobs = scrape_jobs(
        site_name="linkedin",
        search_term=args.search_term,
        location=shard["location"],
        distance=args.distance,
        results_wanted=args.results,
        hours_old=None,
        country_indeed="India",
        is_remote=bool(shard.get("is_remote", False)),
        linkedin_fetch_description=False,
        linkedin_geo_id=shard.get("linkedin_geo_id"),
        linkedin_page_delay_min=args.linkedin_page_delay_min,
        linkedin_page_delay_max=args.linkedin_page_delay_max,
        linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
        num_of_min=60,
        description_limit=0,
        verbose=0,
        linkedin_auth_cookies=linkedin_auth_cookies,
    )
    jobs = _append_linkedin_shard_metadata(jobs, shard)
    elapsed_seconds = time.perf_counter() - started_at
    return jobs, {
        "name": shard["name"],
        "location": shard["location"],
        "is_remote": bool(shard.get("is_remote", False)),
        "jobs": 0 if jobs is None else len(jobs),
        "elapsed_seconds": elapsed_seconds,
    }


def _build_linkedin_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "linkedin",
        "search_term": args.search_term,
        "location": args.location,
        "linkedin_geo_id": _resolve_linkedin_geo_id(args),
        "distance": args.distance,
        "results_requested": (
            args.results
            if args.execution_mode == LinkedInScrapeMode.DEFAULT.value
            else None
        ),
        "jobs_retrieved": _count_jobs_for_site(jobs, "linkedin"),
        "hours_old": (
            args.hours_old
            if args.execution_mode == LinkedInScrapeMode.DEFAULT.value
            else None
        ),
        "execution_mode": args.execution_mode,
        "num_of_min": (
            args.num_of_min
            if args.execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE.value
            else None
        ),
        "fetch_description": args.fetch_description,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(args.scheduler),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_comeet_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "comeet",
        "mode": "persist-all-israel",
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_requested": None,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": True,
        "populate_only": False,
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_linkedin_india_sharded_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "linkedin",
        "mode": "persist-india-sharded",
        "search_term": args.search_term,
        "location": "India",
        "country_indeed": "India",
        "linkedin_geo_id": DEFAULT_LINKEDIN_INDIA_GEO_ID,
        "results_requested": None,
        "jobs_retrieved": _count_jobs_for_site(jobs, "linkedin"),
        "execution_mode": LinkedInScrapeMode.UNTIL_LAST_PAGE.value,
        "num_of_min": 60,
        "fetch_description": True,
        "output_path": str(output_path),
        "save_db": True,
        "populate_only": False,
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_greenhouse_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "greenhouse",
        "mode": "persist-all-pages",
        "search_term": None,
        "location": args.greenhouse_location_name or args.location,
        "country_indeed": args.country_indeed,
        "results_requested": None,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "date_posted": args.greenhouse_date_posted,
        "output_path": str(output_path),
        "save_db": True,
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_indeed_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "indeed",
        "search_term": None,
        "location": args.location,
        "country_indeed": args.country_indeed,
        "results_requested": args.results,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "hours_old": args.hours_old,
        "distance": args.distance if args.distance is not None else 50,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_glassdoor_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
    results_requested: int | None = None,
) -> dict[str, object]:
    return {
        "site": "glassdoor",
        "search_term": None,
        "location": args.location or "Israel",
        "country_indeed": args.country_indeed or "Israel",
        "results_requested": (
            args.results if results_requested is None else results_requested
        ),
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "hours_old": DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_apple_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "apple",
        "platform": "apple-careers",
        "search_term": None,
        "location": "Israel",
        "base_url": _build_apple_search_url(args),
        "results_requested": args.results,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_google_careers_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "google_careers",
        "platform": "google-careers",
        "search_term": None,
        "location": "Israel",
        "base_url": _build_google_careers_url(args),
        "results_requested": args.results,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_microsoft_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "microsoft",
        "platform": "eightfold",
        "search_term": None,
        "location": "Israel",
        "base_url": _build_microsoft_base_url(args),
        "results_requested": args.results,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_amdocs_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    amdocs_base_url = (args.amdocs_base_url or DEFAULT_AMDOCS_BASE_URL).strip()
    return {
        "site": "amdocs",
        "platform": "eightfold",
        "search_term": None,
        "location": None,
        "base_url": amdocs_base_url,
        "results_requested": args.results,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_marvell_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    marvell_base_url = (args.marvell_base_url or DEFAULT_MARVELL_BASE_URL).strip()
    return {
        "site": "marvell",
        "platform": "workday",
        "search_term": None,
        "location": "Israel",
        "base_url": marvell_base_url,
        "results_requested": args.results,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_redhat_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "redhat",
        "platform": "workday",
        "search_term": None,
        "location": "Israel",
        "base_url": _build_redhat_base_url(args),
        "results_requested": None,
        "jobs_retrieved": _count_jobs_for_site(jobs, "redhat"),
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_varonis_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "site": "varonis",
        "platform": "jobvite",
        "search_term": None,
        "location": "Israel",
        "base_url": _build_varonis_base_url(args),
        "results_requested": None,
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_company_career_pages_scrape_run_report(
    args: argparse.Namespace,
    *,
    output_path: Path,
    jobs,
    db_summary: dict[str, Any] | None,
    mode: str = "priority-config",
    job_board_sites: tuple[str, ...] = COMPANY_CAREER_PAGE_JOB_BOARD_SITES,
) -> dict[str, object]:
    return {
        "site": "company_career_pages",
        "mode": mode,
        "job_board_site": ",".join(job_board_sites),
        "job_board_sites": list(job_board_sites),
        "search_term": args.search_term,
        "location": args.location,
        "linkedin_geo_id": _resolve_linkedin_geo_id(args),
        "results_requested": (
            args.results
            if args.execution_mode == LinkedInScrapeMode.DEFAULT.value
            else None
        ),
        "jobs_retrieved": len(jobs) if jobs is not None else None,
        "output_path": str(output_path),
        "save_db": bool(args.save_db),
        "populate_only": bool(args.populate_only),
        "scheduler": bool(getattr(args, "scheduler", False)),
        "scraped": jobs is not None,
        "persisted": db_summary is not None,
        "db_summary": db_summary,
    }


def _build_apple_search_url(args: argparse.Namespace) -> str:
    return (args.apple_search_url or DEFAULT_APPLE_SEARCH_URL).strip()


def _build_google_careers_url(args: argparse.Namespace) -> str:
    return (args.google_careers_url or DEFAULT_GOOGLE_CAREERS_URL).strip()


def _build_microsoft_base_url(args: argparse.Namespace) -> str:
    return (args.microsoft_base_url or DEFAULT_MICROSOFT_BASE_URL).strip()


def _build_varonis_base_url(args: argparse.Namespace) -> str:
    return (args.varonis_base_url or DEFAULT_VARONIS_BASE_URL).strip()


def _build_redhat_base_url(args: argparse.Namespace) -> str:
    return (args.redhat_base_url or DEFAULT_REDHAT_BASE_URL).strip()


def _should_publish_scrape_finished_event(run_report: dict[str, object] | None) -> bool:
    return bool(
        run_report
        and run_report.get("scraped")
        and run_report.get("persisted")
    )


def _build_scrape_finished_payload(
    args: argparse.Namespace,
    *,
    runs: list[dict[str, object]],
) -> dict[str, object]:
    sites = [str(run["site"]) for run in runs if run.get("site")]
    return {
        "source": "jobspy",
        "scheduler": bool(getattr(args, "scheduler", False)),
        "site_count": len(sites),
        "sites": sites,
        "runs": runs,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }


def _publish_scrape_finished_event(
    args: argparse.Namespace,
    *,
    runs: list[dict[str, object]],
    quiet: bool = False,
) -> None:
    from jobspy.event_publisher import publish_scrape_finished_event

    publishable_runs = [
        run_report for run_report in runs if _should_publish_scrape_finished_event(run_report)
    ]
    if not publishable_runs:
        return

    sites = ", ".join(str(run["site"]) for run in publishable_runs)
    if not quiet:
        print(f"Publishing SQS event: scrape.finished (sites={sites})")
    try:
        payload = _build_scrape_finished_payload(
            args,
            runs=publishable_runs,
        )
        if quiet:
            _call_with_output_controls(
                publish_scrape_finished_event,
                payload,
                suppress_stdout=True,
                suppress_logging=True,
            )
        else:
            publish_scrape_finished_event(payload)
        if not quiet:
            print(f"Published SQS event: scrape.finished (sites={sites})")
    except Exception as exc:
        print(
            "Warning: failed to publish SQS event scrape.finished; "
            f"continuing because DB persistence already succeeded ({type(exc).__name__}: {exc})"
        )


def _build_single_job_url(args: argparse.Namespace) -> str:
    if args.job_url:
        return args.job_url.strip()
    if args.job_id:
        return f"https://www.linkedin.com/jobs/view/{args.job_id.strip()}/"
    raise ValueError(
        "--job-url or --job-id is required with --execution-mode inspect-single-job"
    )


def _build_single_profile_url(args: argparse.Namespace) -> str:
    if args.profile_url:
        return args.profile_url.strip()
    raise ValueError(
        "--profile-url is required with --execution-mode inspect-single-profile"
    )


def _build_inspection_summary(inspection: dict[str, object] | None) -> dict[str, object] | None:
    if not inspection:
        return None

    extracted = inspection.get("extracted", {})
    signals = inspection.get("signals", {})
    if not isinstance(extracted, dict):
        extracted = {}
    if not isinstance(signals, dict):
        signals = {}

    return {
        "requested_url": inspection.get("requested_url"),
        "response_url": inspection.get("response_url"),
        "auth": inspection.get("auth"),
        "job_url": extracted.get("job_url"),
        "apply_url": extracted.get("apply_url"),
        "job_url_direct": extracted.get("job_url_direct"),
        "applications_count": extracted.get("applications_count"),
        "page_title": signals.get("page_title"),
        "page_variant": signals.get("page_variant"),
        "is_offsite_apply": signals.get("is_offsite_apply"),
        "canonical_url": signals.get("canonical_url"),
        "lnkd_url": signals.get("lnkd_url"),
        "og_url": signals.get("og_url"),
        "num_applicants_caption": signals.get("num_applicants_caption"),
        "clicked_apply_text": signals.get("clicked_apply_text"),
        "raw_apply_url_code": signals.get("raw_apply_url_code"),
        "logged_in_offsite_apply_url": signals.get("logged_in_offsite_apply_url"),
        "logged_in_easy_apply_url": signals.get("logged_in_easy_apply_url"),
        "session_redirect_values": signals.get("session_redirect_values"),
        "json_ld_summary": signals.get("json_ld_summary"),
    }


def _build_profile_inspection_summary(
    inspection: dict[str, object] | None,
) -> dict[str, object] | None:
    if not inspection:
        return None

    extracted = inspection.get("extracted", {})
    signals = inspection.get("signals", {})
    if not isinstance(extracted, dict):
        extracted = {}
    if not isinstance(signals, dict):
        signals = {}
    sections = inspection.get("sections", {})
    if not isinstance(sections, dict):
        sections = {}

    return {
        "requested_url": inspection.get("requested_url"),
        "response_url": inspection.get("response_url"),
        "status_code": inspection.get("status_code"),
        "auth": inspection.get("auth"),
        "redirect_issue": inspection.get("redirect_issue"),
        "profile_url": extracted.get("profile_url"),
        "profile_slug": extracted.get("profile_slug"),
        "full_name": extracted.get("full_name"),
        "headline": extracted.get("headline"),
        "location": extracted.get("location"),
        "summary": sections.get("summary") or extracted.get("summary"),
        "about": sections.get("about") or extracted.get("about"),
        "skills": sections.get("skills"),
        "experience": sections.get("experience"),
        "education": sections.get("education"),
        "languages": sections.get("languages"),
        "website": extracted.get("website"),
        "page_title": signals.get("page_title"),
        "page_variant": signals.get("page_variant"),
        "canonical_url": signals.get("canonical_url"),
        "lnkd_url": signals.get("lnkd_url"),
        "og_url": signals.get("og_url"),
        "meta_description": signals.get("meta_description"),
        "json_ld_summary": signals.get("json_ld_summary"),
        "section_headings": signals.get("section_headings"),
    }


def _build_profile_sections_output(
    inspection: dict[str, object] | None,
) -> dict[str, object] | None:
    if not inspection:
        return None

    sections = inspection.get("sections", {})
    if not isinstance(sections, dict):
        sections = {}

    extracted = inspection.get("extracted", {})
    if not isinstance(extracted, dict):
        extracted = {}

    summary_text = sections.get("summary") or extracted.get("summary")
    about_text = sections.get("about") or extracted.get("about") or summary_text
    if not summary_text:
        summary_text = about_text

    return {
        "summary": summary_text,
        "about": about_text,
        "skills": sections.get("skills") or [],
        "experience": sections.get("experience") or [],
        "education": sections.get("education") or [],
        "languages": sections.get("languages") or [],
    }


def run_single_job_inspect(args: argparse.Namespace) -> tuple[dict[str, object], None]:
    from jobspy.linkedin import LinkedIn

    job_url = _build_single_job_url(args)
    linkedin_auth_cookies, _ = _resolve_and_print_linkedin_auth_context(
        args,
        context="inspect-single-job",
    )
    scraper = LinkedIn(auth_cookies=linkedin_auth_cookies)
    print(f"Inspecting LinkedIn job: {job_url}")
    original_fetch = scraper.inspect_job(job_url)

    canonical_job_url = None
    if isinstance(original_fetch.get("extracted"), dict):
        canonical_job_url = original_fetch["extracted"].get("job_url")

    canonical_resolution_fetch = None
    if not canonical_job_url or (
        canonical_job_url == original_fetch.get("normalized_job_url")
        and isinstance(original_fetch.get("signals"), dict)
        and not original_fetch["signals"].get("canonical_url")
    ):
        canonical_resolution_fetch = LinkedIn(
            auth_cookies=linkedin_auth_cookies
        ).inspect_job(job_url)
        if isinstance(canonical_resolution_fetch.get("extracted"), dict):
            canonical_job_url = (
                canonical_resolution_fetch["extracted"].get("job_url")
                or canonical_job_url
            )

    canonical_fetch = (
        scraper.inspect_job(str(canonical_job_url))
        if canonical_job_url
        else None
    )

    inspection = {
        "original_fetch": original_fetch,
        "canonical_resolution_fetch": canonical_resolution_fetch,
        "canonical_fetch": canonical_fetch,
        "side_by_side": {
            "original": _build_inspection_summary(original_fetch),
            "canonical_resolution": _build_inspection_summary(canonical_resolution_fetch),
            "canonical": _build_inspection_summary(canonical_fetch),
        },
    }
    print(json.dumps(inspection, ensure_ascii=False, indent=2))
    return inspection, None


def run_single_profile_inspect(
    args: argparse.Namespace,
) -> tuple[dict[str, object], None]:
    from jobspy.linkedin.profile import LinkedInProfileInspector

    profile_url = _build_single_profile_url(args)
    linkedin_auth_cookies, linkedin_auth_source = _resolve_and_print_linkedin_auth_context(
        args,
        context="inspect-single-profile",
    )
    inspector = LinkedInProfileInspector(auth_cookies=linkedin_auth_cookies)
    print(f"Inspecting LinkedIn profile: {profile_url}")
    profile_fetch = inspector.inspect_profile(
        profile_url,
        include_raw_html=args.print_html,
    )
    if args.print_html and isinstance(profile_fetch.get("raw_html"), str):
        print(profile_fetch["raw_html"])
        profile_fetch = dict(profile_fetch)
        profile_fetch.pop("raw_html", None)
    rendered_sections = _build_profile_sections_output(profile_fetch)
    inspection = {
        "auth_source": linkedin_auth_source,
        "profile_fetch": profile_fetch,
        "summary": _build_profile_inspection_summary(profile_fetch),
        "sections": rendered_sections,
    }
    print(json.dumps(rendered_sections, ensure_ascii=False, indent=2))
    return inspection, None


def run_indeed_debug_search(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    search_term = args.search_term or "jobs"
    effective_distance = args.distance if args.distance is not None else 50
    print("Starting Indeed debug search")
    print(f"Search term: {search_term}")
    print(f"Location: {args.location}")
    print(f"Country: {args.country_indeed}")
    if args.distance is None:
        print(
            "Distance: not provided, defaulting to 50 miles because Indeed "
            "requires a radius when location is set"
        )
    else:
        print(f"Distance: {effective_distance}")
    print(f"Hours old filter: {args.hours_old}")
    print("Result target: 1")
    print("Persistence: disabled (search only)")

    jobs = scrape_jobs(
        site_name="indeed",
        search_term=search_term,
        location=args.location,
        distance=effective_distance,
        results_wanted=1,
        hours_old=args.hours_old,
        country_indeed=args.country_indeed,
        description_limit=1,
        verbose=2,
        indeed_debug_trace=True,
    )

    print(f"Indeed debug search finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Indeed debug search returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "job_url_direct",
            "job_type",
            "is_remote",
            "interval",
            "min_amount",
            "max_amount",
            "description",
        ]
        if column in jobs.columns
    ]
    print("Indeed preview:")
    _print_console_safe(jobs[preview_columns].to_string(index=False))
    print("Indeed first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def run_glassdoor_debug_search(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    effective_search_term = args.search_term
    effective_country = args.country_indeed
    effective_location = args.location
    effective_hours_old = DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24

    if not _country_supports_glassdoor(effective_country):
        print(
            f"Glassdoor is not available for country={effective_country!r}; "
            f"defaulting to {DEFAULT_GLASSDOOR_COUNTRY}"
        )
        effective_country = DEFAULT_GLASSDOOR_COUNTRY
        if not args.location or args.location == "Israel":
            effective_location = DEFAULT_GLASSDOOR_LOCATION

    if not effective_location:
        effective_location = DEFAULT_GLASSDOOR_LOCATION

    print("Starting Glassdoor debug search")
    print(f"Search term: {effective_search_term or '<none>'}")
    print(f"Location: {effective_location}")
    print(f"Country: {effective_country}")
    print(f"Date filter: last {DEFAULT_GLASSDOOR_FROM_AGE_DAYS} days")
    print("Result target: 1")
    print("Persistence: disabled (search only)")

    jobs = scrape_jobs(
        site_name="glassdoor",
        search_term=effective_search_term,
        location=effective_location,
        results_wanted=1,
        country_indeed=effective_country,
        hours_old=effective_hours_old,
        description_limit=1,
        verbose=2,
    )

    print(f"Glassdoor debug search finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Glassdoor debug search returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "job_type",
            "is_remote",
            "interval",
            "min_amount",
            "max_amount",
            "description",
        ]
        if column in jobs.columns
    ]
    print("Glassdoor preview:")
    _print_console_safe(jobs[preview_columns].to_string(index=False))
    print("Glassdoor first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def run_greenhouse_debug_search(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    greenhouse_auth_cookies = _build_greenhouse_auth_cookies(args)
    greenhouse_xsrf_token = _resolve_greenhouse_xsrf_token(
        args,
        greenhouse_auth_cookies,
    )
    if not greenhouse_auth_cookies:
        raise ValueError(
            "Greenhouse debug search requires authenticated cookies. Provide "
            "--greenhouse-cookie, --greenhouse-cookie-header, or "
            "--greenhouse-cookie-file."
        )

    effective_location_name = args.greenhouse_location_name or args.location
    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Greenhouse first-pass debug mode currently uses the location feed only"
        )

    print("Starting Greenhouse debug search")
    print(f"Location label: {effective_location_name}")
    print(
        "Coordinates: "
        f"lat={args.greenhouse_lat}, lon={args.greenhouse_lon}, "
        f"location_type={args.greenhouse_location_type}, "
        f"country_short_name={args.greenhouse_country_short_name}"
    )
    print(f"Date posted filter: {args.greenhouse_date_posted}")
    print(
        "Greenhouse auth cookies: "
        + ", ".join(sorted(greenhouse_auth_cookies.keys()))
    )
    print(
        "Greenhouse XSRF token: "
        + ("provided" if greenhouse_xsrf_token else "missing")
    )
    print("Result target: 1")
    print("Persistence: disabled (search only)")

    jobs = scrape_jobs(
        site_name="greenhouse",
        search_term=None,
        location=args.location,
        results_wanted=1,
        country_indeed=args.country_indeed,
        description_limit=1,
        verbose=2,
        greenhouse_auth_cookies=greenhouse_auth_cookies,
        greenhouse_xsrf_token=greenhouse_xsrf_token,
        greenhouse_location_name=effective_location_name,
        greenhouse_lat=args.greenhouse_lat,
        greenhouse_lon=args.greenhouse_lon,
        greenhouse_location_type=args.greenhouse_location_type,
        greenhouse_country_short_name=args.greenhouse_country_short_name,
        greenhouse_date_posted=args.greenhouse_date_posted,
        greenhouse_debug_trace=True,
    )

    print(f"Greenhouse debug search finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Greenhouse debug search returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "apply_url",
            "job_type",
            "is_remote",
            "listing_type",
            "interval",
            "min_amount",
            "max_amount",
            "currency",
            "description",
        ]
        if column in jobs.columns
    ]
    print("Greenhouse preview:")
    _print_console_safe(jobs[preview_columns].to_string(index=False))
    print("Greenhouse first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def run_greenhouse_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="greenhouse")
    greenhouse_auth_cookies = _build_greenhouse_auth_cookies(args)
    greenhouse_xsrf_token = _resolve_greenhouse_xsrf_token(
        args,
        greenhouse_auth_cookies,
    )
    effective_location_name = args.greenhouse_location_name or args.location
    jobs = None
    db_summary: dict[str, Any] | None = None

    if not greenhouse_auth_cookies and not args.populate_only:
        raise ValueError(
            "Greenhouse persistence requires authenticated cookies. Provide "
            "--greenhouse-cookie, --greenhouse-cookie-header, or "
            "--greenhouse-cookie-file."
        )

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Greenhouse persistence currently uses the location feed only"
        )

    if not args.populate_only:
        print("Starting Greenhouse persistence run")
        print(f"Location: {effective_location_name}")
        print(f"Date posted filter: {args.greenhouse_date_posted}")
        print("Execution mode: until-last-page")
        print("Descriptions: always enabled for persistence/parsing")
        print(
            "Greenhouse auth cookies: "
            + ", ".join(sorted(greenhouse_auth_cookies.keys()))
        )

        jobs = scrape_jobs(
            site_name="greenhouse",
            search_term=None,
            location=args.location,
            results_wanted=1,
            country_indeed=args.country_indeed,
            description_limit=None,
            verbose=2,
            greenhouse_auth_cookies=greenhouse_auth_cookies,
            greenhouse_xsrf_token=greenhouse_xsrf_token,
            greenhouse_location_name=effective_location_name,
            greenhouse_lat=args.greenhouse_lat,
            greenhouse_lon=args.greenhouse_lon,
            greenhouse_location_type=args.greenhouse_location_type,
            greenhouse_country_short_name=args.greenhouse_country_short_name,
            greenhouse_date_posted=args.greenhouse_date_posted,
            greenhouse_execution_mode=GreenhouseScrapeMode.UNTIL_LAST_PAGE,
            greenhouse_debug_trace=False,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Greenhouse jobs from {output_path}")

    db_summary = populate_jobs_table_from_file(output_path)
    _print_compact_db_summary(db_summary)
    return jobs, db_summary


def run_amdocs_test_scrape(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    amdocs_base_url = (args.amdocs_base_url or DEFAULT_AMDOCS_BASE_URL).strip()
    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Amdocs test mode currently uses the filters embedded in --amdocs-base-url"
        )

    print("Starting Amdocs test scrape")
    print(f"Base URL: {amdocs_base_url}")
    print(f"Requested jobs: {args.results}")
    print("Description hydration: first row only")
    print("Persistence: disabled (search only)")

    jobs = scrape_jobs(
        site_name="eightfold",
        search_term=None,
        location=None,
        results_wanted=args.results,
        description_format="markdown",
        description_limit=1,
        verbose=2,
        eightfold_company_url=amdocs_base_url,
        eightfold_debug_trace=True,
    )

    print(f"Amdocs test scrape finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Amdocs test scrape returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "listing_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    print("Amdocs preview:")
    _print_console_safe(preview_df.to_string(index=False))
    print("Amdocs first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def run_marvell_israel_test_scrape(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    marvell_base_url = (args.marvell_base_url or DEFAULT_MARVELL_BASE_URL).strip()
    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Marvell test mode currently uses the filters embedded in --marvell-base-url"
        )

    print("Starting Marvell Israel test scrape")
    print("Configuration: site=workday, company=Marvell, location=Israel")
    print(f"Base URL: {marvell_base_url}")
    print(f"Requested jobs: {args.results}")
    print("Descriptions: enabled for all returned jobs")
    print("Persistence: disabled (print only)")

    jobs = scrape_jobs(
        site_name="workday",
        search_term=None,
        location=None,
        results_wanted=args.results,
        country_indeed="Israel",
        description_format="markdown",
        description_limit=None,
        verbose=2,
        workday_company_url=marvell_base_url,
        workday_debug_trace=True,
    )

    print(f"Marvell test scrape finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Marvell test scrape returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    print("Marvell preview:")
    _print_console_safe(preview_df.to_string(index=False))
    print("Marvell first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def run_redhat_test_scrape(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    redhat_base_url = _build_redhat_base_url(args)
    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Red Hat test mode uses the Israel filter embedded in --redhat-base-url"
        )

    print("Starting Red Hat Israel test scrape")
    print("Configuration: site=redhat, platform=workday, location=Israel")
    print(f"Base URL: {redhat_base_url}")
    print("Requested jobs: 1")
    print("Descriptions: enabled for the returned job")
    print("Persistence: disabled (print only)")

    jobs = scrape_jobs(
        site_name="redhat",
        search_term=None,
        location="Israel",
        results_wanted=1,
        country_indeed="Israel",
        description_format="markdown",
        description_limit=1,
        verbose=2,
        redhat_base_url=redhat_base_url,
        redhat_debug_trace=True,
    )

    print(f"Red Hat test scrape finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Red Hat test scrape returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    print("Red Hat preview:")
    _print_console_safe(jobs[preview_columns].head(1).to_string(index=False))
    print("Red Hat first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            indent=2,
            ensure_ascii=False,
        )
    )
    return jobs, None


def run_redhat_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="redhat")
    redhat_base_url = _build_redhat_base_url(args)
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Red Hat persistence uses the Israel filter embedded in --redhat-base-url"
        )

    if not args.populate_only:
        print("Starting Red Hat Israel persistence run")
        print("Configuration: site=redhat, platform=workday, location=Israel")
        print(f"Base URL: {redhat_base_url}")
        print("Requested jobs: all Israel jobs")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="redhat",
            search_term=None,
            location="Israel",
            results_wanted=0,
            country_indeed="Israel",
            description_format="markdown",
            description_limit=None,
            verbose=0,
            redhat_base_url=redhat_base_url,
            redhat_debug_trace=False,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Red Hat jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    print("Red Hat persistence preview:")
    _print_console_safe(jobs[preview_columns].head(20).to_string(index=False))
    return jobs, db_summary


def run_varonis_test_scrape(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    varonis_base_url = _build_varonis_base_url(args)
    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Varonis test mode selects the Israel country filter"
        )

    print("Starting Varonis Israel test scrape")
    print("Configuration: site=varonis, country=Israel")
    print(f"Base URL: {varonis_base_url}")
    print("Requested jobs: 1")
    print("Descriptions: enabled for the returned job")
    print("Persistence: disabled (print only)")

    jobs = scrape_jobs(
        site_name="varonis",
        search_term=None,
        location="Israel",
        results_wanted=1,
        country_indeed="Israel",
        description_format="markdown",
        description_limit=1,
        verbose=2,
        varonis_base_url=varonis_base_url,
        varonis_debug_trace=True,
    )

    print(f"Varonis test scrape finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Varonis test scrape returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "job_function",
            "listing_type",
            "job_url",
            "apply_url",
            "description",
        ]
        if column in jobs.columns
    ]
    print("Varonis preview:")
    _print_console_safe(jobs[preview_columns].head(1).to_string(index=False))
    print("Varonis first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def run_varonis_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="varonis")
    varonis_base_url = _build_varonis_base_url(args)
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Varonis persistence selects the Israel country filter"
        )

    if not args.populate_only:
        print("Starting Varonis Israel persistence run")
        print("Configuration: site=varonis, country=Israel")
        print(f"Base URL: {varonis_base_url}")
        print("Requested jobs: all Israel jobs")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="varonis",
            search_term=None,
            location="Israel",
            results_wanted=0,
            country_indeed="Israel",
            description_format="markdown",
            description_limit=None,
            verbose=0,
            varonis_base_url=varonis_base_url,
            varonis_debug_trace=False,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Varonis jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "job_function",
            "listing_type",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_apple_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="apple")
    apple_search_url = _build_apple_search_url(args)
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Apple persistence uses the filters embedded in --apple-search-url"
        )

    if not args.populate_only:
        print("Starting Apple Israel persistence run")
        print("Configuration: site=apple, platform=apple-careers, location=Israel")
        print(f"Search URL: {apple_search_url}")
        print(f"Requested jobs: {args.results}")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="apple",
            search_term=None,
            location=None,
            results_wanted=args.results,
            country_indeed="Israel",
            description_format="markdown",
            description_limit=None,
            verbose=0,
            apple_search_url=apple_search_url,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Apple jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_function",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_google_careers_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="google_careers")
    google_careers_url = _build_google_careers_url(args)
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Google Careers persistence uses the filters embedded in "
            "--google-careers-url"
        )

    if not args.populate_only:
        print("Starting Google Careers Israel persistence run")
        print(
            "Configuration: site=google_careers, platform=google-careers, "
            "location=Israel"
        )
        print(f"Results URL: {google_careers_url}")
        print(f"Requested jobs: {args.results}")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="google_careers",
            search_term=None,
            location=None,
            results_wanted=args.results,
            country_indeed="Israel",
            description_format="markdown",
            description_limit=None,
            verbose=0,
            google_careers_url=google_careers_url,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Google Careers jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "is_remote",
            "job_url",
            "apply_url",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_microsoft_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="microsoft")
    microsoft_base_url = _build_microsoft_base_url(args)
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Microsoft persistence uses the filters embedded in --microsoft-base-url"
        )

    if not args.populate_only:
        print("Starting Microsoft Israel persistence run")
        print("Configuration: site=microsoft, platform=eightfold, location=Israel")
        print(f"Base URL: {microsoft_base_url}")
        print(f"Requested jobs: {args.results}")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="microsoft",
            search_term=None,
            location=None,
            results_wanted=args.results,
            country_indeed="Israel",
            description_format="markdown",
            description_limit=None,
            verbose=0,
            microsoft_base_url=microsoft_base_url,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Microsoft jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "listing_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_marvell_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="marvell")
    marvell_base_url = (args.marvell_base_url or DEFAULT_MARVELL_BASE_URL).strip()
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Marvell persistence uses the filters embedded in --marvell-base-url"
        )

    if not args.populate_only:
        print("Starting Marvell Israel persistence run")
        print("Configuration: site=workday, company=Marvell, location=Israel")
        print(f"Base URL: {marvell_base_url}")
        print(f"Requested jobs: {args.results}")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="workday",
            search_term=None,
            location=None,
            results_wanted=args.results,
            country_indeed="Israel",
            description_format="markdown",
            description_limit=None,
            verbose=0,
            workday_company_url=marvell_base_url,
            workday_debug_trace=False,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Marvell jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_amdocs_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="amdocs")
    amdocs_base_url = (args.amdocs_base_url or DEFAULT_AMDOCS_BASE_URL).strip()
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "Amdocs persistence uses the filters embedded in --amdocs-base-url"
        )

    if not args.populate_only:
        print("Starting Amdocs persistence run")
        print("Configuration: site=eightfold, company=Amdocs")
        print(f"Base URL: {amdocs_base_url}")
        print(f"Requested jobs: {args.results}")
        print("Descriptions: enabled for all returned jobs")

        jobs = scrape_jobs(
            site_name="eightfold",
            search_term=None,
            location=None,
            results_wanted=args.results,
            description_format="markdown",
            description_limit=None,
            verbose=0,
            eightfold_company_url=amdocs_base_url,
            eightfold_debug_trace=False,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Amdocs jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "listing_type",
            "is_remote",
            "job_url",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_indeed_persist(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="indeed")
    effective_distance = args.distance if args.distance is not None else 50
    effective_hours_old = args.hours_old if args.hours_old is not None else 24
    effective_location = args.location or "Israel"
    effective_country = args.country_indeed or "Israel"
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "--indeed-persist uses no search term"
        )

    if not args.populate_only:
        print("Starting Indeed persistence run")
        print(
            "Configuration: "
            f"site=indeed, location={effective_location}, country={effective_country}"
        )
        print(
            "Configuration: "
            f"search_term=None, hours_old={effective_hours_old}"
        )
        print(f"Requested jobs: {args.results}")
        print(f"Distance: {effective_distance}")
        print("Descriptions: always enabled for persistence/parsing")

        jobs = scrape_jobs(
            site_name="indeed",
            search_term=None,
            location=effective_location,
            distance=effective_distance,
            results_wanted=args.results,
            hours_old=effective_hours_old,
            country_indeed=effective_country,
            description_limit=None,
            verbose=0,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Indeed jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "job_url_direct",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_glassdoor_persist(
    args: argparse.Namespace,
    *,
    results_wanted: int | None = None,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="glassdoor")
    effective_location = args.location or "Israel"
    effective_country = args.country_indeed or "Israel"
    effective_hours_old = DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24
    effective_results_wanted = args.results if results_wanted is None else results_wanted
    jobs = None
    db_summary: dict[str, Any] | None = None

    if args.search_term:
        print(
            f"Ignoring --search-term={args.search_term!r}; "
            "--glassdoor-persist uses no search term"
        )

    if not args.populate_only:
        print("Starting Glassdoor persistence run")
        print(
            "Configuration: "
            f"site=glassdoor, location={effective_location}, country={effective_country}"
        )
        print(
            "Configuration: "
            f"search_term=None, hours_old={effective_hours_old}"
        )
        print(f"Requested jobs: {effective_results_wanted}")
        print("Descriptions: always enabled for persistence/parsing")

        jobs = scrape_jobs(
            site_name="glassdoor",
            search_term=None,
            location=effective_location,
            results_wanted=effective_results_wanted,
            hours_old=effective_hours_old,
            country_indeed=effective_country,
            description_limit=None,
            verbose=2,
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading Glassdoor jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "job_type",
            "is_remote",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_populate_comeet_base_urls(
    args: argparse.Namespace,
) -> tuple[None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_company_comeet_job_urls_from_file

    input_path = Path(args.output).expanduser().resolve()
    print(f"Populating company_comeet_job_urls from {input_path}")
    db_summary = populate_company_comeet_job_urls_from_file(input_path)
    return None, db_summary


def run_comeet_test_scrape(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import get_company_comeet_job_url

    company_record = get_company_comeet_job_url(args.comeet_base_url)
    if not company_record:
        if args.comeet_base_url:
            raise ValueError(
                "No company_comeet_job_urls row found for "
                f"{args.comeet_base_url!r}"
            )
        raise ValueError(
            "company_comeet_job_urls is empty. Populate it first with "
            "--populate-comeet-base-urls."
        )

    print("Selected Comeet company row:")
    print(
        json.dumps(
            {
                key: (
                    value.isoformat()
                    if hasattr(value, "isoformat")
                    else value
                )
                for key, value in company_record.items()
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    company_url = company_record["comeet_base_url"]
    print(f"Starting Comeet test scrape for {company_url}")
    print(
        "Configuration: "
        f"results={args.results}, company_name={company_record.get('company_name')}, "
        "description_format=markdown, trace=enabled"
    )

    jobs = scrape_jobs(
        site_name="comeet",
        results_wanted=args.results,
        country_indeed=args.country_indeed,
        description_format="markdown",
        comeet_company_url=company_url,
        comeet_debug_trace=True,
        verbose=2,
    )

    print(f"Comeet test scrape finished. Retrieved {len(jobs)} job(s)")
    if jobs.empty:
        print("Comeet test scrape returned no jobs")
        return jobs, None

    preview_columns = [
        column
        for column in [
            "title",
            "company",
            "location",
            "date_posted",
            "job_type",
            "is_remote",
            "job_url",
            "job_url_direct",
        ]
        if column in jobs.columns
    ]
    preview_df = jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    print("Comeet preview:")
    _print_console_safe(preview_df.to_string(index=False))
    print("Comeet first row JSON:")
    _print_console_safe(
        json.dumps(
            json.loads(
                jobs.head(1).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return jobs, None


def _collect_comeet_country_jobs(
    company_records: list[dict[str, Any]],
    *,
    country_indeed: str,
) -> tuple[object, list[tuple[str, str]], dict[str, Any]]:
    import pandas as pd

    job_frames = []
    collected_job_links: list[tuple[str, str]] = []
    total_jobs = 0
    failed_companies = 0
    companies_with_jobs = 0

    for index, company_record in enumerate(company_records, start=1):
        company_name = (
            company_record.get("company_name") or company_record["comeet_base_url"]
        )
        company_url = company_record["comeet_base_url"]

        try:
            jobs = scrape_jobs(
                site_name="comeet",
                results_wanted=0,
                country_indeed=country_indeed,
                description_format="markdown",
                comeet_company_url=company_url,
                comeet_debug_trace=False,
                verbose=0,
            )
        except Exception as exc:
            failed_companies += 1
            print(
                f"[{index}/{len(company_records)}] {company_name} -> FAILED: {exc}"
            )
            continue

        company_job_links = []
        if not jobs.empty and "job_url" in jobs.columns:
            job_frames.append(jobs)
            for job_url in jobs["job_url"].dropna().astype(str).tolist():
                company_job_links.append(job_url)

        company_job_links = list(dict.fromkeys(company_job_links))
        total_jobs += len(company_job_links)
        if company_job_links:
            companies_with_jobs += 1

        collected_job_links.extend(
            (company_name, job_url) for job_url in company_job_links
        )
        print(
            f"[{index}/{len(company_records)}] {company_name} -> "
            f"{len(company_job_links)} {country_indeed} job(s)"
        )

    if job_frames:
        combined_jobs = pd.concat(job_frames, ignore_index=True)
    else:
        combined_jobs = pd.DataFrame()

    summary = {
        "companies": len(company_records),
        "companies_with_jobs": companies_with_jobs,
        "failed": failed_companies,
        "job_links": total_jobs,
    }
    return combined_jobs, collected_job_links, summary


def _collect_comeet_israel_jobs(
    company_records: list[dict[str, Any]],
) -> tuple[object, list[tuple[str, str]], dict[str, Any]]:
    return _collect_comeet_country_jobs(
        company_records,
        country_indeed="Israel",
    )


def run_comeet_scrape_all_israel(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import list_company_comeet_job_urls

    company_records = list_company_comeet_job_urls()
    if not company_records:
        raise ValueError(
            "company_comeet_job_urls is empty. Populate it first with "
            "--populate-comeet-base-urls."
        )

    print(
        f"Starting Comeet Israel batch scrape for {len(company_records)} company row(s)"
    )
    print(
        "Configuration: "
        "country=Israel, results=all, persistence=disabled, trace=disabled"
    )
    _, collected_job_links, summary = _collect_comeet_israel_jobs(company_records)

    print("Comeet Israel batch scrape finished")
    print(
        "Summary: "
        f"companies={summary['companies']} "
        f"companies_with_jobs={summary['companies_with_jobs']} "
        f"failed={summary['failed']} "
        f"job_links={summary['job_links']}"
    )
    print("Israel job links:")
    for company_name, job_url in collected_job_links:
        print(f"{company_name}: {job_url}")

    return None, summary


def run_comeet_persist_all_israel(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import list_company_comeet_job_urls, populate_comeet_jobs_table

    company_records = list_company_comeet_job_urls()
    if not company_records:
        raise ValueError(
            "company_comeet_job_urls is empty. Populate it first with "
            "--populate-comeet-base-urls."
        )

    output_path = _resolve_output_path(args.output, site="comeet")
    print(
        f"Starting Comeet Israel persistence run for {len(company_records)} company row(s)"
    )
    print(
        "Configuration: "
        "country=Israel, results=all, persistence=bulk, trace=disabled"
    )

    jobs, _, scrape_summary = _collect_comeet_israel_jobs(company_records)

    print("Comeet Israel scrape collection finished")
    print(
        "Summary: "
        f"companies={scrape_summary['companies']} "
        f"companies_with_jobs={scrape_summary['companies_with_jobs']} "
        f"failed={scrape_summary['failed']} "
        f"job_links={scrape_summary['job_links']}"
    )
    save_jobs_to_json(output_path, jobs)
    db_summary = populate_comeet_jobs_table(jobs)
    _print_compact_db_summary(db_summary)
    return jobs, db_summary


def run_comeet_persist_all_india(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import list_company_comeet_job_urls

    company_records = list_company_comeet_job_urls()
    if not company_records:
        raise ValueError(
            "company_comeet_job_urls is empty. Populate it first with "
            "--populate-comeet-base-urls."
        )

    print(
        f"Starting Comeet India link-print run for {len(company_records)} company row(s)"
    )
    print(
        "Configuration: "
        "country=India, results=all, persistence=disabled, trace=disabled"
    )
    _, collected_job_links, summary = _collect_comeet_country_jobs(
        company_records,
        country_indeed="India",
    )

    print("Comeet India link-print run finished")
    print(
        "Summary: "
        f"companies={summary['companies']} "
        f"companies_with_jobs={summary['companies_with_jobs']} "
        f"failed={summary['failed']} "
        f"job_links={summary['job_links']}"
    )
    print("India job links:")
    for company_name, job_url in collected_job_links:
        print(f"{company_name}: {job_url}")

    return None, summary


def run_linkedin_scrape_india(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    linkedin_auth_cookies, _ = _resolve_and_print_linkedin_auth_context(
        args,
        context="linkedin-scrape-india",
    )
    print("Starting LinkedIn India scrape")
    print(
        "Configuration: "
        f"site=linkedin, location=India, geoId={DEFAULT_LINKEDIN_INDIA_GEO_ID}"
    )
    print(
        "Configuration: "
        "execution_mode=until-last-page, minutes_filter=60, persistence=disabled"
    )
    print(f"Search term: {args.search_term or 'None'}")
    print("Descriptions enabled: True (hydrated after discovery)")

    jobs = scrape_jobs(
        site_name="linkedin",
        search_term=args.search_term,
        location="India",
        distance=args.distance,
        results_wanted=args.results,
        hours_old=None,
        country_indeed="India",
        linkedin_fetch_description=False,
        linkedin_geo_id=DEFAULT_LINKEDIN_INDIA_GEO_ID,
        linkedin_page_delay_min=args.linkedin_page_delay_min,
        linkedin_page_delay_max=args.linkedin_page_delay_max,
        linkedin_execution_mode=LinkedInScrapeMode.UNTIL_LAST_PAGE,
        num_of_min=60,
        description_limit=0,
        verbose=2,
        linkedin_auth_cookies=linkedin_auth_cookies,
    )

    print("Hydrating LinkedIn India descriptions")
    jobs, hydration_summary = _hydrate_linkedin_jobs_with_descriptions(
        jobs,
        auth_cookies=linkedin_auth_cookies,
    )
    print(
        "Description hydration summary: "
        f"requested={hydration_summary['requested']} "
        f"hydrated={hydration_summary['hydrated']} "
        f"failed={hydration_summary['failed']}"
    )

    linkedin_count = _count_jobs_for_site(jobs, "linkedin") or 0
    print(f"Scrape finished. Retrieved {linkedin_count} LinkedIn India job(s)")

    if jobs is None or jobs.empty or getattr(args, "suppress_preview", False):
        return jobs, None

    if args.print_all:
        _print_console_safe(jobs.to_string(index=False))
    else:
        _print_linkedin_jobs_preview(jobs)
    return jobs, None


def run_linkedin_scrape_india_sharded(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    import pandas as pd

    linkedin_auth_cookies, _ = _resolve_and_print_linkedin_auth_context(
        args,
        context="linkedin-scrape-india-sharded",
    )
    shards = _get_linkedin_india_shards()
    worker_count = min(DEFAULT_LINKEDIN_INDIA_SHARD_WORKERS, len(shards))

    print("Starting LinkedIn India sharded scrape")
    print(
        "Configuration: "
        f"site=linkedin, shards={len(shards)}, workers={worker_count}, minutes_filter=60"
    )
    print(f"Search term: {args.search_term or 'None'}")
    print(
        "Shard plan: "
        + ", ".join(shard["name"] for shard in shards)
    )
    print("Descriptions enabled: True (hydrated after shard discovery)")

    shard_frames = []
    shard_summaries: list[dict[str, Any]] = []
    failed_shards = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_shard = {
            executor.submit(
                _scrape_linkedin_india_shard,
                shard,
                args=args,
            ): shard
            for shard in shards
        }

        for completed_index, future in enumerate(as_completed(future_to_shard), start=1):
            shard = future_to_shard[future]
            try:
                shard_jobs, shard_summary = future.result()
            except Exception as exc:
                failed_shards += 1
                print(
                    f"[{completed_index}/{len(shards)}] "
                    f"shard={shard['name']} location={shard['location']} "
                    f"remote={bool(shard.get('is_remote', False))} -> FAILED: {exc}"
                )
                continue

            shard_summaries.append(shard_summary)
            if shard_jobs is not None and not shard_jobs.empty:
                shard_frames.append(shard_jobs)
            print(
                f"[{completed_index}/{len(shards)}] "
                f"shard={shard_summary['name']} location={shard_summary['location']} "
                f"remote={shard_summary['is_remote']} jobs={shard_summary['jobs']} "
                f"elapsed={shard_summary['elapsed_seconds']:.2f}s"
            )

    if shard_frames:
        combined_jobs = pd.concat(shard_frames, ignore_index=True)
    else:
        combined_jobs = pd.DataFrame()

    deduped_jobs, dedupe_summary = _dedupe_sharded_linkedin_jobs(combined_jobs)
    shards_with_jobs = sum(1 for summary in shard_summaries if summary["jobs"] > 0)

    print(
        f"Hydrating descriptions for {dedupe_summary['unique_rows']} unique LinkedIn India job(s)"
    )
    deduped_jobs, hydration_summary = _hydrate_linkedin_jobs_with_descriptions(
        deduped_jobs,
        auth_cookies=linkedin_auth_cookies,
    )

    print("LinkedIn India sharded scrape finished")
    print(
        "Summary: "
        f"shards={len(shards)} "
        f"shards_with_jobs={shards_with_jobs} "
        f"failed={failed_shards} "
        f"raw_job_rows={dedupe_summary['raw_rows']} "
        f"unique_job_rows={dedupe_summary['unique_rows']} "
        f"duplicates_removed={dedupe_summary['duplicates_removed']} "
        f"descriptions_hydrated={hydration_summary['hydrated']} "
        f"description_failures={hydration_summary['failed']}"
    )

    if deduped_jobs is None or deduped_jobs.empty or getattr(args, "suppress_preview", False):
        return deduped_jobs, {
            "shards": len(shards),
            "shards_with_jobs": shards_with_jobs,
            "failed": failed_shards,
            **dedupe_summary,
            **{
                "descriptions_requested": hydration_summary["requested"],
                "descriptions_hydrated": hydration_summary["hydrated"],
                "description_failures": hydration_summary["failed"],
            },
        }

    if args.print_all:
        _print_console_safe(deduped_jobs.to_string(index=False))
    else:
        _print_linkedin_jobs_preview(deduped_jobs, include_search_shard=True)

    return deduped_jobs, {
        "shards": len(shards),
        "shards_with_jobs": shards_with_jobs,
        "failed": failed_shards,
        **dedupe_summary,
        **{
            "descriptions_requested": hydration_summary["requested"],
            "descriptions_hydrated": hydration_summary["hydrated"],
            "description_failures": hydration_summary["failed"],
        },
    }


def run_linkedin_persist_india_sharded(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import populate_jobs_table_from_file

    output_path = _resolve_output_path(args.output, site="linkedin")
    scrape_args = argparse.Namespace(**vars(args))
    scrape_args.suppress_preview = True
    jobs, _ = run_linkedin_scrape_india_sharded(scrape_args)

    save_jobs_to_json(output_path, jobs)

    db_summary = None
    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    return jobs, db_summary


def run_company_career_pages_priority(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    import pandas as pd

    from jobspy.jobs_table import (
        list_company_career_pages,
        populate_jobs_table_from_file,
    )

    output_path = _resolve_output_path(args.output, site="company_career_pages")
    jobs = None
    db_summary: dict[str, Any] | None = None

    if not args.populate_only:
        company_records = list_company_career_pages(seed_defaults=True)
        if not company_records:
            raise ValueError(
                "company_career_pages is empty. Insert at least one enabled row "
                "before running --company-career-pages."
            )

        print("Starting configured company career-page priority run")
        print(
            "Configuration: "
            f"job_boards={','.join(COMPANY_CAREER_PAGE_JOB_BOARD_SITES)}, "
            f"company_rows={len(company_records)}, "
            "order=direct-then-job-board, "
            "persistence=combined, duplicate_marking=enabled"
        )

        company_jobs, company_summary = _scrape_company_career_page_rows(
            company_records,
            args,
        )

        board_jobs, board_summary = _scrape_company_career_pages_job_board_rows(
            args,
        )

        frames = [
            frame
            for frame in (company_jobs, board_jobs)
            if frame is not None and not getattr(frame, "empty", False)
        ]
        jobs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        board_counts = ", ".join(
            f"{row['site']}={row['jobs']}"
            for row in board_summary["rows"]
            if "error" not in row
        )
        print(
            "Configured company career-page run finished: "
            f"direct_jobs={company_summary['jobs']} "
            f"direct_failed={company_summary['failed']} "
            f"job_board_jobs={board_summary['jobs']} "
            f"job_board_failed={board_summary['failed']} "
            f"job_board_counts={board_counts or 'none'} "
            f"combined_jobs={len(jobs)}"
        )
        save_jobs_to_json(output_path, jobs)
    else:
        print(f"Skipping scrape. Reading configured company jobs from {output_path}")

    if args.save_db or args.populate_only:
        db_summary = populate_jobs_table_from_file(
            output_path,
            mark_configured_company_job_board_duplicates=True,
        )
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "site",
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "direct_company_career_page_key",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def _build_company_career_page_new_job_counts(
    jobs,
    db_summary: dict[str, Any] | None,
) -> dict[str, int]:
    inserted_job_urls = {
        _safe_config_str(job_url)
        for job_url in (db_summary or {}).get("inserted_job_urls", [])
    }
    inserted_job_urls.discard(None)
    if (
        not inserted_job_urls
        or jobs is None
        or getattr(jobs, "empty", False)
        or "job_url" not in jobs.columns
        or "direct_company_career_page_key" not in jobs.columns
    ):
        return {}

    new_jobs = jobs[jobs["job_url"].isin(inserted_job_urls)]
    if getattr(new_jobs, "empty", False):
        return {}
    counts = new_jobs.groupby("direct_company_career_page_key").size()
    return {str(company_key): int(count) for company_key, count in counts.items()}


def _print_company_career_page_new_job_summary(
    company_summary: dict[str, Any],
    jobs,
    db_summary: dict[str, Any] | None,
) -> None:
    new_job_counts = _build_company_career_page_new_job_counts(jobs, db_summary)
    print("Configured company career-page new jobs by company:")
    for row_summary in company_summary.get("rows", []):
        company_key = _safe_config_str(row_summary.get("company_key")) or "unknown"
        company_name = (
            _safe_config_str(row_summary.get("company_name")) or company_key
        )
        message = (
            f"- {company_name}: new_jobs={new_job_counts.get(company_key, 0)} "
            f"scraped_jobs={int(row_summary.get('jobs') or 0)}"
        )
        error = _safe_config_str(row_summary.get("error"))
        if error:
            message = f"{message} error={error}"
        print(message)


def run_company_career_pages_table_only_once(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    from jobspy.jobs_table import (
        list_company_career_pages,
        populate_jobs_table_from_file,
    )

    output_path = _resolve_output_path(args.output, site="company_career_pages")
    jobs = None
    db_summary: dict[str, Any] | None = None

    company_records = list_company_career_pages(seed_defaults=True)
    if not company_records:
        raise ValueError(
            "company_career_pages is empty. Insert at least one enabled row "
            "before running --company-career-pages-table-only."
        )

    print("Starting configured company career-page table-only run")
    print(
        "Configuration: "
        f"company_rows={len(company_records)}, "
        "order=direct-only, "
        "job_boards=disabled, "
        "persistence=jobs-table"
    )

    jobs, company_summary = _scrape_company_career_page_rows(company_records, args)
    print(
        "Configured company career-page table-only scrape finished: "
        f"direct_jobs={company_summary['jobs']} "
        f"direct_failed={company_summary['failed']} "
        f"combined_jobs={len(jobs)}"
    )
    save_jobs_to_json(output_path, jobs)

    if args.save_db:
        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    _print_company_career_page_new_job_summary(company_summary, jobs, db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "site",
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "direct_company_career_page_key",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def run_company_career_page_probe(args: argparse.Namespace) -> dict[str, Any]:
    from jobspy.company_career_probe import probe_company_career_page
    from jobspy.jobs_table import upsert_company_career_page_from_validation

    result = probe_company_career_page(
        company_name=args.company_name,
        company_key=args.company_key,
        career_page_url=args.career_page_url,
        location=args.location,
        country_indeed=args.country_indeed,
        sample_size=args.company_career_page_sample_size,
        request_timeout=getattr(args, "timeout", 60),
    )
    if args.activate_company_career_page:
        result["db_summary"] = upsert_company_career_page_from_validation(
            result,
            activate=True,
        )
    _print_console_safe(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


def run_once(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    if args.execution_mode == LinkedInScrapeMode.INSPECT_SINGLE_JOB.value:
        return run_single_job_inspect(args)
    if args.execution_mode == LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value:
        return run_single_profile_inspect(args)

    linkedin_auth_cookies, _ = _build_linkedin_auth_context(args)
    output_path = _resolve_output_path(args.output, site="linkedin")
    jobs = None
    db_summary: dict[str, Any] | None = None
    scrape_verbose = (
        2
        if args.execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE.value
        else 0
    )

    if not args.populate_only:
        linkedin_geo_id = _resolve_linkedin_geo_id(args)
        description_limit = (
            None
            if (
                args.fetch_description
                and args.execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE.value
            )
            else args.results if args.fetch_description else 0
        )
        jobs = scrape_jobs(
            site_name=["linkedin", "redhat"],
            search_term=args.search_term,
            location=args.location,
            distance=args.distance,
            results_wanted=args.results,
            hours_old=args.hours_old,
            linkedin_fetch_description=args.fetch_description,
            linkedin_geo_id=linkedin_geo_id,
            linkedin_page_delay_min=args.linkedin_page_delay_min,
            linkedin_page_delay_max=args.linkedin_page_delay_max,
            linkedin_execution_mode=args.execution_mode,
            num_of_min=args.num_of_min,
            description_limit=description_limit,
            redhat_base_url=_build_redhat_base_url(args),
            verbose=scrape_verbose,
            linkedin_auth_cookies=linkedin_auth_cookies,
        )

        save_jobs_to_json(output_path, jobs)

    if args.save_db or args.populate_only:
        from jobspy.jobs_table import populate_jobs_table_from_file

        db_summary = populate_jobs_table_from_file(output_path)
        _print_compact_db_summary(db_summary)

    if _should_skip_jobs_preview(args, jobs):
        return jobs, db_summary

    preview_columns = [
        column
        for column in [
            "site",
            "title",
            "company",
            "location",
            "date_posted",
            "job_url",
            "description",
        ]
        if column in jobs.columns
    ]
    preview_df = (
        jobs[preview_columns] if args.print_all else jobs[preview_columns].head(20)
    )
    _print_console_safe(preview_df.to_string(index=False))
    return jobs, db_summary


def _get_next_scheduler_run_at(from_time: datetime) -> datetime:
    first_run_at = from_time.replace(
        hour=SCHEDULER_FIRST_RUN_HOUR,
        minute=SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )
    if from_time < first_run_at:
        return first_run_at

    last_run_at = from_time.replace(
        hour=SCHEDULER_LAST_RUN_HOUR,
        minute=SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )
    next_run_at = from_time.replace(
        minute=SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )
    if from_time >= next_run_at:
        next_run_at += timedelta(hours=1)
    if next_run_at <= last_run_at:
        return next_run_at
    next_day = from_time + timedelta(days=1)
    return next_day.replace(
        hour=SCHEDULER_FIRST_RUN_HOUR,
        minute=SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )


def _get_scheduler_num_of_min(
    scheduled_run_at: datetime,
) -> int:
    if (
        scheduled_run_at.hour == SCHEDULER_FIRST_RUN_HOUR
        and scheduled_run_at.minute == SCHEDULER_RUN_MINUTE
    ):
        return FIRST_SCHEDULER_INTERVAL_MINUTES
    return MIN_LINKEDIN_SCHEDULER_INTERVAL_MINUTES


def _get_scheduler_hours_old(num_of_min: int) -> int:
    return max(1, (num_of_min + 59) // 60)


def _should_run_three_hour_scheduler_sites(scheduled_run_at: datetime) -> bool:
    return (
        scheduled_run_at.minute == SCHEDULER_RUN_MINUTE
        and SCHEDULER_FIRST_RUN_HOUR <= scheduled_run_at.hour <= SCHEDULER_LAST_RUN_HOUR
        and (
            (scheduled_run_at.hour - SCHEDULER_FIRST_RUN_HOUR)
            % SCHEDULER_THREE_HOUR_INTERVAL_HOURS
            == 0
        )
    )


def _build_scheduler_linkedin_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.fetch_description = True
    schedule_args.execution_mode = LinkedInScrapeMode.UNTIL_LAST_PAGE.value
    schedule_args.hours_old = None
    schedule_args.linkedin_geo_id = _resolve_linkedin_geo_id(schedule_args)
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    return schedule_args


def _build_company_career_pages_scheduler_args(
    args: argparse.Namespace,
) -> argparse.Namespace:
    schedule_args = _build_scheduler_linkedin_args(args)
    schedule_args.company_career_pages = True
    schedule_args.company_career_pages_now = False
    schedule_args.company_career_pages_table_only = False
    schedule_args.scheduler = True
    return schedule_args


def _build_company_career_pages_now_args(
    args: argparse.Namespace,
) -> argparse.Namespace:
    run_args = _build_scheduler_linkedin_args(args)
    run_args.company_career_pages = False
    run_args.company_career_pages_now = True
    run_args.company_career_pages_table_only = False
    run_args.scheduler = False
    run_args.num_of_min = FIRST_SCHEDULER_INTERVAL_MINUTES
    return run_args


def _build_company_career_pages_table_only_args(
    args: argparse.Namespace,
) -> argparse.Namespace:
    run_args = argparse.Namespace(**vars(args))
    run_args.populate_only = False
    run_args.save_db = True
    run_args.print_all = False
    run_args.suppress_preview = True
    run_args.search_term = None
    run_args.company_career_pages = False
    run_args.company_career_pages_now = False
    run_args.company_career_pages_table_only = True
    run_args.scheduler = True
    return run_args


def _get_next_linkedin_india_scheduler_run_at(from_time: datetime) -> datetime:
    first_run_at = from_time.replace(
        hour=LINKEDIN_INDIA_SCHEDULER_FIRST_RUN_HOUR,
        minute=LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )
    if from_time < first_run_at:
        return first_run_at

    last_run_at = from_time.replace(
        hour=LINKEDIN_INDIA_SCHEDULER_LAST_RUN_HOUR,
        minute=LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )
    next_run_at = from_time.replace(
        minute=LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )
    if from_time >= next_run_at:
        next_run_at += timedelta(hours=1)
    if next_run_at <= last_run_at:
        return next_run_at

    next_day = from_time + timedelta(days=1)
    return next_day.replace(
        hour=LINKEDIN_INDIA_SCHEDULER_FIRST_RUN_HOUR,
        minute=LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE,
        second=0,
        microsecond=0,
    )


def _build_linkedin_india_sharded_scheduler_args(
    args: argparse.Namespace,
) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    return schedule_args


def _build_scheduler_indeed_args(
    args: argparse.Namespace,
    *,
    hours_old: int,
) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.location = "Israel"
    schedule_args.country_indeed = "Israel"
    schedule_args.hours_old = hours_old
    return schedule_args


def _build_scheduler_glassdoor_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.location = "Israel"
    schedule_args.country_indeed = "Israel"
    schedule_args.hours_old = DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24
    return schedule_args


def _build_scheduler_amdocs_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.amdocs_base_url = (
        schedule_args.amdocs_base_url or DEFAULT_AMDOCS_BASE_URL
    )
    return schedule_args


def _build_scheduler_apple_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.apple_search_url = _build_apple_search_url(schedule_args)
    return schedule_args


def _build_scheduler_microsoft_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.microsoft_base_url = _build_microsoft_base_url(schedule_args)
    return schedule_args


def _build_scheduler_marvell_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.marvell_base_url = (
        schedule_args.marvell_base_url or DEFAULT_MARVELL_BASE_URL
    )
    return schedule_args


def _build_scheduler_redhat_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.redhat_base_url = (
        schedule_args.redhat_base_url or DEFAULT_REDHAT_BASE_URL
    )
    return schedule_args


def _build_scheduler_varonis_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.varonis_base_url = (
        schedule_args.varonis_base_url or DEFAULT_VARONIS_BASE_URL
    )
    return schedule_args


def _build_scheduler_comeet_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    return schedule_args


def _build_scheduler_greenhouse_args(args: argparse.Namespace) -> argparse.Namespace:
    schedule_args = argparse.Namespace(**vars(args))
    schedule_args.populate_only = False
    schedule_args.save_db = True
    schedule_args.print_all = False
    schedule_args.suppress_preview = True
    schedule_args.search_term = None
    schedule_args.location = "Israel"
    schedule_args.country_indeed = "Israel"
    if not (
        schedule_args.greenhouse_cookie_file
        or schedule_args.greenhouse_cookie
        or schedule_args.greenhouse_cookie_header
    ):
        schedule_args.greenhouse_cookie_file = str(DEFAULT_GREENHOUSE_COOKIE_FILE)
    return schedule_args


def _print_db_summary(label: str, db_summary: dict[str, Any] | None) -> None:
    if db_summary is None:
        return
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"{label} DB summary: "
        f"rows_in_file={db_summary.get('rows_in_file', 'n/a')} "
        f"inserted={db_summary.get('inserted', 'n/a')} "
        f"updated={db_summary.get('updated', 'n/a')} "
        f"invalid={db_summary.get('skipped_invalid', 'n/a')} "
        f"dup_input={db_summary.get('skipped_duplicate_input', 'n/a')} "
        f"failed={db_summary.get('failed', 'n/a')}"
    )
    _print_updated_change_summary(db_summary)


def _print_scheduler_site_summary(
    label: str,
    run_report: dict[str, object],
) -> None:
    db_summary = run_report.get("db_summary")
    if not isinstance(db_summary, dict):
        db_summary = {}

    jobs_retrieved = run_report.get("jobs_retrieved")
    print(
        f"[{datetime.now(SCHEDULER_TIMEZONE).isoformat(timespec='seconds')}] "
        f"{label} scheduler summary: "
        f"jobs_retrieved={jobs_retrieved if jobs_retrieved is not None else 'n/a'} "
        f"rows_in_file={db_summary.get('rows_in_file', 'n/a')} "
        f"inserted={db_summary.get('inserted', 'n/a')} "
        f"updated={db_summary.get('updated', 'n/a')} "
        f"invalid={db_summary.get('skipped_invalid', 'n/a')} "
        f"dup_input={db_summary.get('skipped_duplicate_input', 'n/a')} "
        f"failed={db_summary.get('failed', 'n/a')}"
    )
    _print_updated_change_summary(db_summary)


def _run_scheduled_scrape(
    *,
    label: str,
    schedule_args: argparse.Namespace,
    runner: Callable[..., Any],
    report_builder: Callable[..., dict[str, object]],
    output_site: str,
) -> dict[str, object]:
    print(f"Running scheduled {label} scrape")
    jobs, db_summary = _call_with_output_controls(
        runner,
        schedule_args,
        suppress_stdout=True,
        suppress_logging=True,
    )
    run_report = report_builder(
        schedule_args,
        output_path=_resolve_output_path(schedule_args.output, site=output_site),
        jobs=jobs,
        db_summary=db_summary,
    )
    _print_scheduler_site_summary(label, run_report)
    return run_report


def _run_scheduler_tick(
    args: argparse.Namespace,
    linkedin_schedule_args: argparse.Namespace,
    *,
    next_run_at: datetime,
    run_started_at: datetime,
    last_successful_run_date: date | None,
) -> tuple[bool, date | None]:
    scheduler_num_of_min = _get_scheduler_num_of_min(next_run_at)
    scheduler_hours_old = _get_scheduler_hours_old(scheduler_num_of_min)
    run_three_hour_scheduler_sites = _should_run_three_hour_scheduler_sites(
        next_run_at
    )
    print(
        f"[{run_started_at.isoformat(timespec='seconds')}] "
        "Scheduler tick started "
        f"(scheduled_for={next_run_at.isoformat(timespec='seconds')}, "
        f"linkedin_minutes_filter={scheduler_num_of_min}, "
        f"indeed_hours_old={scheduler_hours_old}, "
        f"three_hour_sites={'yes' if run_three_hour_scheduler_sites else 'no'})"
    )
    linkedin_schedule_args.num_of_min = scheduler_num_of_min
    indeed_schedule_args = _build_scheduler_indeed_args(
        args,
        hours_old=scheduler_hours_old,
    )
    glassdoor_schedule_args = _build_scheduler_glassdoor_args(args)
    amdocs_schedule_args = _build_scheduler_amdocs_args(args)
    apple_schedule_args = _build_scheduler_apple_args(args)
    microsoft_schedule_args = _build_scheduler_microsoft_args(args)
    marvell_schedule_args = _build_scheduler_marvell_args(args)
    redhat_schedule_args = _build_scheduler_redhat_args(args)
    varonis_schedule_args = _build_scheduler_varonis_args(args)
    _call_with_output_controls(
        _resolve_and_print_linkedin_auth_context,
        linkedin_schedule_args,
        context="scheduler-tick",
        suppress_stdout=True,
        suppress_logging=True,
    )
    tick_succeeded = True
    completed_runs: list[dict[str, object]] = []

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="LinkedIn",
                schedule_args=linkedin_schedule_args,
                runner=run_once,
                report_builder=_build_linkedin_scrape_run_report,
                output_site="linkedin",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled LinkedIn run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Indeed",
                schedule_args=indeed_schedule_args,
                runner=run_indeed_persist,
                report_builder=_build_indeed_scrape_run_report,
                output_site="indeed",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Indeed run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Glassdoor",
                schedule_args=glassdoor_schedule_args,
                runner=run_glassdoor_persist,
                report_builder=_build_glassdoor_scrape_run_report,
                output_site="glassdoor",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Glassdoor run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Amdocs",
                schedule_args=amdocs_schedule_args,
                runner=run_amdocs_persist,
                report_builder=_build_amdocs_scrape_run_report,
                output_site="amdocs",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Amdocs run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Apple",
                schedule_args=apple_schedule_args,
                runner=run_apple_persist,
                report_builder=_build_apple_scrape_run_report,
                output_site="apple",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Apple run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Microsoft",
                schedule_args=microsoft_schedule_args,
                runner=run_microsoft_persist,
                report_builder=_build_microsoft_scrape_run_report,
                output_site="microsoft",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Microsoft run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Marvell",
                schedule_args=marvell_schedule_args,
                runner=run_marvell_persist,
                report_builder=_build_marvell_scrape_run_report,
                output_site="marvell",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Marvell run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Red Hat",
                schedule_args=redhat_schedule_args,
                runner=run_redhat_persist,
                report_builder=_build_redhat_scrape_run_report,
                output_site="redhat",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Red Hat run failed: {exc}")

    try:
        completed_runs.append(
            _run_scheduled_scrape(
                label="Varonis",
                schedule_args=varonis_schedule_args,
                runner=run_varonis_persist,
                report_builder=_build_varonis_scrape_run_report,
                output_site="varonis",
            )
        )
    except Exception as exc:
        tick_succeeded = False
        print(f"Scheduled Varonis run failed: {exc}")

    if run_three_hour_scheduler_sites:
        comeet_schedule_args = _build_scheduler_comeet_args(args)
        greenhouse_schedule_args = _build_scheduler_greenhouse_args(args)

        try:
            completed_runs.append(
                _run_scheduled_scrape(
                    label="Comeet",
                    schedule_args=comeet_schedule_args,
                    runner=run_comeet_persist_all_israel,
                    report_builder=_build_comeet_scrape_run_report,
                    output_site="comeet",
                )
            )
        except Exception as exc:
            tick_succeeded = False
            print(f"Scheduled Comeet run failed: {exc}")

        try:
            completed_runs.append(
                _run_scheduled_scrape(
                    label="Greenhouse",
                    schedule_args=greenhouse_schedule_args,
                    runner=run_greenhouse_persist,
                    report_builder=_build_greenhouse_scrape_run_report,
                    output_site="greenhouse",
                )
            )
        except Exception as exc:
            tick_succeeded = False
            print(f"Scheduled Greenhouse run failed: {exc}")
    else:
        print("Skipping scheduled Comeet and Greenhouse runs until the next 3-hour tick")

    _publish_scrape_finished_event(args, runs=completed_runs, quiet=True)

    completed_at = datetime.now(SCHEDULER_TIMEZONE)
    if tick_succeeded:
        print(
            f"[{completed_at.isoformat(timespec='seconds')}] "
            "Scheduler tick completed successfully"
        )
        updated_last_successful_run_date = run_started_at.date()
        return True, updated_last_successful_run_date

    print(
        f"[{completed_at.isoformat(timespec='seconds')}] "
        "Scheduler tick completed with failures"
    )
    return False, last_successful_run_date


def run_scheduler(args: argparse.Namespace) -> None:
    linkedin_schedule_args = _build_scheduler_linkedin_args(args)
    last_successful_run_date: date | None = None

    while True:
        now = datetime.now(SCHEDULER_TIMEZONE)
        next_run_at = _get_next_scheduler_run_at(now)
        sleep_seconds = max(0, (next_run_at - now).total_seconds())
        time.sleep(sleep_seconds)

        run_started_at = datetime.now(SCHEDULER_TIMEZONE)
        _, last_successful_run_date = _run_scheduler_tick(
            args,
            linkedin_schedule_args,
            next_run_at=next_run_at,
            run_started_at=run_started_at,
            last_successful_run_date=last_successful_run_date,
        )


def _run_company_career_pages_scheduler_tick(
    args: argparse.Namespace,
    schedule_args: argparse.Namespace,
    *,
    next_run_at: datetime,
    run_started_at: datetime,
    last_successful_run_date: date | None,
) -> tuple[bool, date | None]:
    scheduler_num_of_min = _get_scheduler_num_of_min(next_run_at)
    schedule_args.num_of_min = scheduler_num_of_min

    print(
        f"[{run_started_at.isoformat(timespec='seconds')}] "
        "Company career-page scheduler tick started "
        f"(scheduled_for={next_run_at.isoformat(timespec='seconds')}, "
        f"board_minutes_filter={scheduler_num_of_min}, "
        "duplicate_marking=enabled)"
    )
    print("Running scheduled configured company career-page priority scrape")

    try:
        jobs, db_summary = run_company_career_pages_priority(schedule_args)
        run_report = _build_company_career_pages_scrape_run_report(
            schedule_args,
            output_path=_resolve_output_path(
                schedule_args.output,
                site="company_career_pages",
            ),
            jobs=jobs,
            db_summary=db_summary,
        )
        _print_scheduler_site_summary("Company Career Pages", run_report)
        _publish_scrape_finished_event(args, runs=[run_report], quiet=True)

        completed_at = datetime.now(SCHEDULER_TIMEZONE)
        print(
            f"[{completed_at.isoformat(timespec='seconds')}] "
            "Company career-page scheduler tick completed successfully"
        )
        return True, run_started_at.date()
    except Exception as exc:
        completed_at = datetime.now(SCHEDULER_TIMEZONE)
        print(f"Scheduled company career-page run failed: {exc}")
        print(
            f"[{completed_at.isoformat(timespec='seconds')}] "
            "Company career-page scheduler tick completed with failures"
        )
        return False, last_successful_run_date


def run_company_career_pages_scheduler(args: argparse.Namespace) -> None:
    from jobspy.jobs_table import ensure_company_career_pages_table

    schedule_args = _build_company_career_pages_scheduler_args(args)
    last_successful_run_date: date | None = None

    ensure_company_career_pages_table(seed_defaults=True)

    print("Starting configured company career-page scheduler mode")
    print(
        "Scheduler profile: "
        "site=company_career_pages, "
        f"timezone={SCHEDULER_TIMEZONE.key}, "
        f"window={SCHEDULER_FIRST_RUN_HOUR:02d}:"
        f"{SCHEDULER_RUN_MINUTE:02d}-"
        f"{SCHEDULER_LAST_RUN_HOUR:02d}:"
        f"{SCHEDULER_RUN_MINUTE:02d}, "
        "cadence=hourly, "
        f"job_boards={','.join(COMPANY_CAREER_PAGE_JOB_BOARD_SITES)}, "
        "persistence=combined, duplicate_marking=enabled"
    )

    while True:
        now = datetime.now(SCHEDULER_TIMEZONE)
        next_run_at = _get_next_scheduler_run_at(now)
        sleep_seconds = max(0, (next_run_at - now).total_seconds())
        print(
            f"[{now.isoformat(timespec='seconds')}] "
            "Next configured company career-page run at "
            f"{next_run_at.isoformat(timespec='seconds')} "
            f"(cadence=hourly, minute={SCHEDULER_RUN_MINUTE}, "
            f"window={SCHEDULER_FIRST_RUN_HOUR:02d}:"
            f"{SCHEDULER_RUN_MINUTE:02d}-"
            f"{SCHEDULER_LAST_RUN_HOUR:02d}:"
            f"{SCHEDULER_RUN_MINUTE:02d}, "
            f"sleep={sleep_seconds:.0f}s, anchor=Israel-wall-clock)"
        )
        time.sleep(sleep_seconds)

        run_started_at = datetime.now(SCHEDULER_TIMEZONE)
        _, last_successful_run_date = _run_company_career_pages_scheduler_tick(
            args,
            schedule_args,
            next_run_at=next_run_at,
            run_started_at=run_started_at,
            last_successful_run_date=last_successful_run_date,
        )


def _run_company_career_pages_table_only_scheduler_tick(
    schedule_args: argparse.Namespace,
    *,
    run_started_at: datetime,
) -> bool:
    print(
        f"[{run_started_at.isoformat(timespec='seconds')}] "
        "Company career-page table-only scheduler tick started "
        "(job_boards=disabled, duplicate_marking=disabled)"
    )

    try:
        jobs, db_summary = run_company_career_pages_table_only_once(schedule_args)
        run_report = _build_company_career_pages_scrape_run_report(
            schedule_args,
            output_path=_resolve_output_path(
                schedule_args.output,
                site="company_career_pages",
            ),
            jobs=jobs,
            db_summary=db_summary,
            mode="table-only",
            job_board_sites=(),
        )
        _print_scheduler_site_summary("Company Career Pages Table Only", run_report)
        _publish_scrape_finished_event(schedule_args, runs=[run_report], quiet=True)

        completed_at = datetime.now(SCHEDULER_TIMEZONE)
        print(
            f"[{completed_at.isoformat(timespec='seconds')}] "
            "Company career-page table-only scheduler tick completed successfully"
        )
        return True
    except Exception as exc:
        completed_at = datetime.now(SCHEDULER_TIMEZONE)
        print(f"Scheduled company career-page table-only run failed: {exc}")
        print(
            f"[{completed_at.isoformat(timespec='seconds')}] "
            "Company career-page table-only scheduler tick completed with failures"
        )
        return False


def run_company_career_pages_table_only_scheduler(args: argparse.Namespace) -> None:
    from jobspy.jobs_table import ensure_company_career_pages_table

    schedule_args = _build_company_career_pages_table_only_args(args)
    ensure_company_career_pages_table(seed_defaults=True)

    print("Starting configured company career-page table-only scheduler mode")
    print(
        "Scheduler profile: "
        "site=company_career_pages, "
        f"timezone={SCHEDULER_TIMEZONE.key}, "
        "cadence=2h, "
        "first_run=immediate, "
        "job_boards=disabled, "
        "persistence=jobs-table"
    )

    while True:
        run_started_at = datetime.now(SCHEDULER_TIMEZONE)
        _run_company_career_pages_table_only_scheduler_tick(
            schedule_args,
            run_started_at=run_started_at,
        )

        now = datetime.now(SCHEDULER_TIMEZONE)
        next_run_at = now + timedelta(
            hours=COMPANY_CAREER_PAGES_TABLE_ONLY_INTERVAL_HOURS
        )
        sleep_seconds = max(0, (next_run_at - now).total_seconds())
        print(
            f"[{now.isoformat(timespec='seconds')}] "
            "Next configured company career-page table-only run at "
            f"{next_run_at.isoformat(timespec='seconds')} "
            f"(cadence={COMPANY_CAREER_PAGES_TABLE_ONLY_INTERVAL_HOURS}h, "
            f"sleep={sleep_seconds:.0f}s)"
        )
        time.sleep(sleep_seconds)


def run_company_career_pages_now(
    args: argparse.Namespace,
) -> tuple[object | None, dict[str, Any] | None]:
    run_args = _build_company_career_pages_now_args(args)
    output_path = _resolve_output_path(run_args.output, site="company_career_pages")

    print("Starting configured company career-page one-shot mode")
    print(
        "One-shot profile: "
        "site=company_career_pages, "
        f"board_minutes_filter={run_args.num_of_min}, "
        f"job_boards={','.join(COMPANY_CAREER_PAGE_JOB_BOARD_SITES)}, "
        "order=direct-then-job-board, "
        "persistence=combined, duplicate_marking=enabled, exit=on-finish"
    )

    jobs, db_summary = run_company_career_pages_priority(run_args)
    run_report = _build_company_career_pages_scrape_run_report(
        run_args,
        output_path=output_path,
        jobs=jobs,
        db_summary=db_summary,
    )
    _publish_scrape_finished_event(args, runs=[run_report])

    print("Configured company career-page one-shot run completed")
    return jobs, db_summary


def run_linkedin_persist_india_sharded_scheduler(args: argparse.Namespace) -> None:
    schedule_args = _build_linkedin_india_sharded_scheduler_args(args)

    print("Starting LinkedIn India sharded scheduler mode")
    print(
        "Scheduler profile: "
        "site=linkedin-india-sharded, "
        f"timezone={LINKEDIN_INDIA_SCHEDULER_TIMEZONE.key}, "
        f"window={LINKEDIN_INDIA_SCHEDULER_FIRST_RUN_HOUR:02d}:"
        f"{LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE:02d}-"
        f"{LINKEDIN_INDIA_SCHEDULER_LAST_RUN_HOUR:02d}:"
        f"{LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE:02d}, "
        "cadence=hourly, "
        f"minutes_filter={LINKEDIN_INDIA_SCHEDULER_INTERVAL_MINUTES}, "
        "save_db=True, descriptions=True, shards=bengaluru,pune"
    )

    while True:
        now = datetime.now(LINKEDIN_INDIA_SCHEDULER_TIMEZONE)
        next_run_at = _get_next_linkedin_india_scheduler_run_at(now)
        sleep_seconds = max(0, (next_run_at - now).total_seconds())
        print(
            f"[{now.isoformat(timespec='seconds')}] "
            f"Next India sharded run at {next_run_at.isoformat(timespec='seconds')} "
            f"(cadence=hourly, minute={LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE}, "
            f"window={LINKEDIN_INDIA_SCHEDULER_FIRST_RUN_HOUR:02d}:"
            f"{LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE:02d}-"
            f"{LINKEDIN_INDIA_SCHEDULER_LAST_RUN_HOUR:02d}:"
            f"{LINKEDIN_INDIA_SCHEDULER_RUN_MINUTE:02d}, "
            f"sleep={sleep_seconds:.0f}s, anchor=India-wall-clock)"
        )
        time.sleep(sleep_seconds)

        run_started_at = datetime.now(LINKEDIN_INDIA_SCHEDULER_TIMEZONE)
        print(
            f"[{run_started_at.isoformat(timespec='seconds')}] "
            "India sharded scheduler tick started "
            f"(scheduled_for={next_run_at.isoformat(timespec='seconds')}, "
            f"minutes_filter={LINKEDIN_INDIA_SCHEDULER_INTERVAL_MINUTES}, "
            "shards=bengaluru,pune)"
        )
        _resolve_and_print_linkedin_auth_context(
            schedule_args,
            context="linkedin-india-sharded-scheduler-tick",
        )

        try:
            jobs, db_summary = run_linkedin_persist_india_sharded(schedule_args)
            _print_db_summary("LinkedIn India sharded", db_summary)
            _publish_scrape_finished_event(
                args,
                runs=[
                    _build_linkedin_india_sharded_scrape_run_report(
                        schedule_args,
                        output_path=_resolve_output_path(
                            schedule_args.output,
                            site="linkedin",
                        ),
                        jobs=jobs,
                        db_summary=db_summary,
                    )
                ],
            )
            print(
                f"[{datetime.now(LINKEDIN_INDIA_SCHEDULER_TIMEZONE).isoformat(timespec='seconds')}] "
                "India sharded scheduler tick completed successfully"
            )
        except Exception as exc:
            print(f"India sharded scheduler tick failed: {exc}")


def _validate_exclusive_cli_modes(args: argparse.Namespace) -> None:
    exclusive_modes = [
        ("--populate-only", bool(args.populate_only)),
        ("--company-career-pages", bool(args.company_career_pages)),
        ("--company-career-pages-now", bool(args.company_career_pages_now)),
        (
            "--company-career-pages-table-only",
            bool(args.company_career_pages_table_only),
        ),
        ("--company-career-page-probe", bool(args.company_career_page_probe)),
        ("--populate-comeet-base-urls", bool(args.populate_comeet_base_urls)),
        ("--comeet-test-scrape", bool(args.comeet_test_scrape)),
        ("--comeet-scrape-all-israel", bool(args.comeet_scrape_all_israel)),
        ("--comeet-persist-all-israel", bool(args.comeet_persist_all_israel)),
        ("--comeet-persist-all-india", bool(args.comeet_persist_all_india)),
        ("--linkedin-scrape-india", bool(args.linkedin_scrape_india)),
        ("--linkedin-scrape-india-sharded", bool(args.linkedin_scrape_india_sharded)),
        ("--linkedin-persist-india-sharded", bool(args.linkedin_persist_india_sharded)),
        (
            "--linkedin-persist-india-sharded-scheduler",
            bool(args.linkedin_persist_india_sharded_scheduler),
        ),
        ("--indeed-debug-search", bool(args.indeed_debug_search)),
        ("--indeed-persist", bool(args.indeed_persist)),
        ("--glassdoor-debug-search", bool(args.glassdoor_debug_search)),
        ("--glassdoor-persist", bool(args.glassdoor_persist)),
        ("--glassdoor-persist-one", bool(args.glassdoor_persist_one)),
        ("--greenhouse-debug-search", bool(args.greenhouse_debug_search)),
        ("--greenhouse-persist", bool(args.greenhouse_persist)),
        ("--amdocs-test-scrape", bool(args.amdocs_test_scrape)),
        ("--amdocs-persist", bool(args.amdocs_persist)),
        ("--apple-persist", bool(args.apple_persist)),
        ("--google-careers-persist", bool(args.google_careers_persist)),
        ("--microsoft-persist", bool(args.microsoft_persist)),
        ("--marvell-israel-test-scrape", bool(args.marvell_israel_test_scrape)),
        ("--marvell-persist", bool(args.marvell_persist)),
        ("--redhat-test-scrape", bool(args.redhat_test_scrape)),
        ("--redhat-persist", bool(args.redhat_persist)),
        ("--varonis-test-scrape", bool(args.varonis_test_scrape)),
        ("--varonis-persist", bool(args.varonis_persist)),
        (
            "--scheduler",
            bool(
                args.scheduler
                and not args.company_career_pages
                and not args.company_career_pages_now
                and not args.company_career_pages_table_only
            ),
        ),
    ]
    enabled_modes = [
        flag_name for flag_name, is_enabled in exclusive_modes if is_enabled
    ]
    if len(enabled_modes) > 1:
        raise ValueError(
            f"{enabled_modes[0]} cannot be combined with {enabled_modes[1]}"
        )
    if args.company_career_page_probe:
        if not args.company_name:
            raise ValueError("--company-name is required with --company-career-page-probe")
        if not args.career_page_url:
            raise ValueError(
                "--career-page-url is required with --company-career-page-probe"
            )
    elif args.activate_company_career_page:
        raise ValueError(
            "--activate-company-career-page requires --company-career-page-probe"
        )


def main() -> None:
    args = build_parser().parse_args()
    _validate_exclusive_cli_modes(args)

    if args.execution_mode == LinkedInScrapeMode.INSPECT_SINGLE_JOB.value:
        args.save_db = False
        args.populate_only = False
    if args.indeed_debug_search:
        args.save_db = False
        args.populate_only = False
    if args.glassdoor_debug_search:
        args.save_db = False
        args.populate_only = False
    if args.greenhouse_debug_search:
        args.save_db = False
        args.populate_only = False
    if args.amdocs_test_scrape:
        args.save_db = False
        args.populate_only = False
    if args.marvell_israel_test_scrape:
        args.save_db = False
        args.populate_only = False
    if args.redhat_test_scrape:
        args.save_db = False
        args.populate_only = False
    if args.varonis_test_scrape:
        args.save_db = False
        args.populate_only = False
    if args.populate_comeet_base_urls:
        args.populate_only = False
    if args.comeet_test_scrape:
        args.save_db = False
        args.populate_only = False
    if args.comeet_scrape_all_israel:
        args.save_db = False
        args.populate_only = False
    if args.comeet_persist_all_israel:
        args.save_db = False
        args.populate_only = False
    if args.comeet_persist_all_india:
        args.save_db = False
        args.populate_only = False
    if args.linkedin_scrape_india:
        args.save_db = False
        args.populate_only = False
    if args.linkedin_scrape_india_sharded:
        args.save_db = False
        args.populate_only = False
    if args.linkedin_persist_india_sharded_scheduler:
        args.populate_only = False
    if args.company_career_pages_table_only:
        args.populate_only = False

    if args.num_of_min is not None and args.num_of_min <= 0:
        raise ValueError("--num-of-min must be greater than 0")
    if args.company_career_page_sample_size <= 0:
        raise ValueError("--company-career-page-sample-size must be greater than 0")
    if (
        args.linkedin_page_delay_min is not None
        and args.linkedin_page_delay_min < 0
    ):
        raise ValueError("--linkedin-page-delay-min must be non-negative")
    if (
        args.linkedin_page_delay_max is not None
        and args.linkedin_page_delay_max < 0
    ):
        raise ValueError("--linkedin-page-delay-max must be non-negative")
    if (
        args.linkedin_page_delay_min is not None
        and args.linkedin_page_delay_max is not None
        and args.linkedin_page_delay_min > args.linkedin_page_delay_max
    ):
        raise ValueError(
            "--linkedin-page-delay-min cannot be greater than "
            "--linkedin-page-delay-max"
        )
    if (
        (
            args.company_career_pages
            or args.company_career_pages_now
            or args.company_career_pages_table_only
        )
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--company-career-pages, --company-career-pages-now, and "
            "--company-career-pages-table-only cannot be combined with "
            "--execution-mode"
        )
    if args.company_career_pages_now and args.scheduler:
        raise ValueError(
            "--company-career-pages-now cannot be combined with --scheduler"
        )
    if args.company_career_pages_table_only and args.scheduler:
        raise ValueError(
            "--company-career-pages-table-only cannot be combined with --scheduler"
        )
    if (
        args.amdocs_base_url
        and not args.amdocs_test_scrape
        and not args.amdocs_persist
        and not args.scheduler
    ):
        raise ValueError(
            "--amdocs-base-url can only be combined with --amdocs-test-scrape, "
            "--amdocs-persist, or --scheduler"
        )
    if args.apple_search_url and not (args.apple_persist or args.scheduler):
        raise ValueError(
            "--apple-search-url can only be combined with --apple-persist or --scheduler"
        )
    if args.google_careers_url and not args.google_careers_persist:
        raise ValueError(
            "--google-careers-url can only be combined with "
            "--google-careers-persist"
        )
    if args.microsoft_base_url and not (args.microsoft_persist or args.scheduler):
        raise ValueError(
            "--microsoft-base-url can only be combined with --microsoft-persist or --scheduler"
        )
    if (
        args.marvell_base_url
        and not args.marvell_israel_test_scrape
        and not args.marvell_persist
        and not args.scheduler
    ):
        raise ValueError(
            "--marvell-base-url can only be combined with "
            "--marvell-israel-test-scrape, --marvell-persist, or --scheduler"
        )
    if (
        args.varonis_base_url
        and not args.varonis_test_scrape
        and not args.varonis_persist
        and not args.scheduler
    ):
        raise ValueError(
            "--varonis-base-url can only be combined with --varonis-test-scrape, "
            "--varonis-persist, or --scheduler"
        )
    if (
        args.redhat_base_url
        and not args.redhat_test_scrape
        and not args.redhat_persist
        and not args.scheduler
    ):
        raise ValueError(
            "--redhat-base-url can only be combined with --redhat-test-scrape, "
            "--redhat-persist, or --scheduler"
        )
    if args.comeet_base_url and not args.comeet_test_scrape:
        raise ValueError(
            "--comeet-base-url can only be combined with --comeet-test-scrape"
        )
    if args.comeet_scrape_all_israel and args.comeet_base_url:
        raise ValueError(
            "--comeet-base-url cannot be combined with --comeet-scrape-all-israel"
        )
    if args.comeet_persist_all_israel and args.comeet_base_url:
        raise ValueError(
            "--comeet-base-url cannot be combined with --comeet-persist-all-israel"
        )
    if args.populate_only and args.populate_comeet_base_urls:
        raise ValueError(
            "--populate-only cannot be combined with --populate-comeet-base-urls"
        )
    if args.populate_only and args.comeet_test_scrape:
        raise ValueError(
            "--populate-only cannot be combined with --comeet-test-scrape"
        )
    if args.populate_only and args.comeet_scrape_all_israel:
        raise ValueError(
            "--populate-only cannot be combined with --comeet-scrape-all-israel"
        )
    if args.populate_only and args.comeet_persist_all_israel:
        raise ValueError(
            "--populate-only cannot be combined with --comeet-persist-all-israel"
        )
    if args.populate_only and args.greenhouse_debug_search:
        raise ValueError(
            "--populate-only cannot be combined with --greenhouse-debug-search"
        )
    if args.populate_only and args.amdocs_test_scrape:
        raise ValueError(
            "--populate-only cannot be combined with --amdocs-test-scrape"
        )
    if args.amdocs_test_scrape and args.amdocs_persist:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --amdocs-persist"
        )
    if args.marvell_israel_test_scrape and args.marvell_persist:
        raise ValueError(
            "--marvell-israel-test-scrape cannot be combined with --marvell-persist"
        )
    if args.greenhouse_debug_search and args.greenhouse_persist:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --greenhouse-persist"
        )
    if args.glassdoor_debug_search and args.glassdoor_persist:
        raise ValueError(
            "--glassdoor-debug-search cannot be combined with --glassdoor-persist"
        )
    if args.glassdoor_debug_search and args.glassdoor_persist_one:
        raise ValueError(
            "--glassdoor-debug-search cannot be combined with --glassdoor-persist-one"
        )
    if args.glassdoor_persist and args.glassdoor_persist_one:
        raise ValueError(
            "--glassdoor-persist cannot be combined with --glassdoor-persist-one"
        )
    if args.indeed_debug_search and args.indeed_persist:
        raise ValueError(
            "--indeed-debug-search cannot be combined with --indeed-persist"
        )
    if args.comeet_test_scrape and args.populate_comeet_base_urls:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --populate-comeet-base-urls"
        )
    if args.comeet_scrape_all_israel and args.populate_comeet_base_urls:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --populate-comeet-base-urls"
        )
    if args.comeet_persist_all_israel and args.populate_comeet_base_urls:
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --populate-comeet-base-urls"
        )
    if args.greenhouse_debug_search and args.populate_comeet_base_urls:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --populate-comeet-base-urls"
        )
    if args.greenhouse_persist and args.populate_comeet_base_urls:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --populate-comeet-base-urls"
        )
    if args.glassdoor_persist and args.populate_comeet_base_urls:
        raise ValueError(
            "--glassdoor-persist cannot be combined with --populate-comeet-base-urls"
        )
    if args.glassdoor_persist_one and args.populate_comeet_base_urls:
        raise ValueError(
            "--glassdoor-persist-one cannot be combined with --populate-comeet-base-urls"
        )
    if args.comeet_test_scrape and args.comeet_scrape_all_israel:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --comeet-scrape-all-israel"
        )
    if args.comeet_test_scrape and args.comeet_persist_all_israel:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --comeet-persist-all-israel"
        )
    if args.comeet_scrape_all_israel and args.comeet_persist_all_israel:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --comeet-persist-all-israel"
        )
    if args.populate_comeet_base_urls and args.indeed_debug_search:
        raise ValueError(
            "--populate-comeet-base-urls cannot be combined with --indeed-debug-search"
        )
    if args.comeet_test_scrape and args.indeed_debug_search:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --indeed-debug-search"
        )
    if args.comeet_scrape_all_israel and args.indeed_debug_search:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --indeed-debug-search"
        )
    if args.comeet_persist_all_israel and args.indeed_debug_search:
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --indeed-debug-search"
        )
    if args.glassdoor_persist and args.indeed_debug_search:
        raise ValueError(
            "--glassdoor-persist cannot be combined with --indeed-debug-search"
        )
    if args.glassdoor_persist_one and args.indeed_debug_search:
        raise ValueError(
            "--glassdoor-persist-one cannot be combined with --indeed-debug-search"
        )
    if args.greenhouse_debug_search and args.indeed_debug_search:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --indeed-debug-search"
        )
    if args.greenhouse_persist and args.indeed_debug_search:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --indeed-debug-search"
        )
    if args.populate_comeet_base_urls and args.indeed_persist:
        raise ValueError(
            "--populate-comeet-base-urls cannot be combined with --indeed-persist"
        )
    if args.comeet_test_scrape and args.indeed_persist:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --indeed-persist"
        )
    if args.comeet_scrape_all_israel and args.indeed_persist:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --indeed-persist"
        )
    if args.comeet_persist_all_israel and args.indeed_persist:
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --indeed-persist"
        )
    if args.greenhouse_debug_search and args.indeed_persist:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --indeed-persist"
        )
    if args.greenhouse_persist and args.indeed_persist:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --indeed-persist"
        )
    if args.glassdoor_persist and args.indeed_persist:
        raise ValueError(
            "--glassdoor-persist cannot be combined with --indeed-persist"
        )
    if args.glassdoor_persist_one and args.indeed_persist:
        raise ValueError(
            "--glassdoor-persist-one cannot be combined with --indeed-persist"
        )
    if args.indeed_debug_search and args.glassdoor_debug_search:
        raise ValueError(
            "--indeed-debug-search cannot be combined with --glassdoor-debug-search"
        )
    if args.comeet_test_scrape and args.glassdoor_debug_search:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --glassdoor-debug-search"
        )
    if args.comeet_scrape_all_israel and args.glassdoor_debug_search:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --glassdoor-debug-search"
        )
    if args.comeet_persist_all_israel and args.glassdoor_debug_search:
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --glassdoor-debug-search"
        )
    if args.populate_comeet_base_urls and args.glassdoor_debug_search:
        raise ValueError(
            "--populate-comeet-base-urls cannot be combined with --glassdoor-debug-search"
        )
    if args.indeed_persist and args.glassdoor_debug_search:
        raise ValueError(
            "--indeed-persist cannot be combined with --glassdoor-debug-search"
        )
    if args.greenhouse_debug_search and args.glassdoor_debug_search:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --glassdoor-debug-search"
        )
    if args.greenhouse_persist and args.glassdoor_debug_search:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --glassdoor-debug-search"
        )
    if args.comeet_test_scrape and args.glassdoor_persist:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --glassdoor-persist"
        )
    if args.comeet_test_scrape and args.glassdoor_persist_one:
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --glassdoor-persist-one"
        )
    if args.comeet_scrape_all_israel and args.glassdoor_persist:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --glassdoor-persist"
        )
    if args.comeet_scrape_all_israel and args.glassdoor_persist_one:
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --glassdoor-persist-one"
        )
    if args.comeet_persist_all_israel and args.glassdoor_persist:
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --glassdoor-persist"
        )
    if args.comeet_persist_all_israel and args.glassdoor_persist_one:
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --glassdoor-persist-one"
        )
    if args.greenhouse_debug_search and args.glassdoor_persist:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --glassdoor-persist"
        )
    if args.greenhouse_debug_search and args.glassdoor_persist_one:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --glassdoor-persist-one"
        )
    if args.greenhouse_persist and args.glassdoor_persist:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --glassdoor-persist"
        )
    if args.greenhouse_persist and args.glassdoor_persist_one:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --glassdoor-persist-one"
        )
    if args.amdocs_test_scrape and args.populate_comeet_base_urls:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --populate-comeet-base-urls"
        )
    if args.amdocs_test_scrape and args.comeet_test_scrape:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --comeet-test-scrape"
        )
    if args.amdocs_test_scrape and args.comeet_scrape_all_israel:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --comeet-scrape-all-israel"
        )
    if args.amdocs_test_scrape and args.comeet_persist_all_israel:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --comeet-persist-all-israel"
        )
    if args.amdocs_test_scrape and args.indeed_debug_search:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --indeed-debug-search"
        )
    if args.amdocs_test_scrape and args.indeed_persist:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --indeed-persist"
        )
    if args.amdocs_test_scrape and args.glassdoor_debug_search:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --glassdoor-debug-search"
        )
    if args.amdocs_test_scrape and args.glassdoor_persist:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --glassdoor-persist"
        )
    if args.amdocs_test_scrape and args.glassdoor_persist_one:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --glassdoor-persist-one"
        )
    if args.amdocs_test_scrape and args.greenhouse_debug_search:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --greenhouse-debug-search"
        )
    if args.amdocs_test_scrape and args.greenhouse_persist:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --greenhouse-persist"
        )
    if args.amdocs_persist and args.populate_comeet_base_urls:
        raise ValueError(
            "--amdocs-persist cannot be combined with --populate-comeet-base-urls"
        )
    if args.amdocs_persist and args.comeet_test_scrape:
        raise ValueError(
            "--amdocs-persist cannot be combined with --comeet-test-scrape"
        )
    if args.amdocs_persist and args.comeet_scrape_all_israel:
        raise ValueError(
            "--amdocs-persist cannot be combined with --comeet-scrape-all-israel"
        )
    if args.amdocs_persist and args.comeet_persist_all_israel:
        raise ValueError(
            "--amdocs-persist cannot be combined with --comeet-persist-all-israel"
        )
    if args.amdocs_persist and args.indeed_debug_search:
        raise ValueError(
            "--amdocs-persist cannot be combined with --indeed-debug-search"
        )
    if args.amdocs_persist and args.indeed_persist:
        raise ValueError(
            "--amdocs-persist cannot be combined with --indeed-persist"
        )
    if args.amdocs_persist and args.glassdoor_debug_search:
        raise ValueError(
            "--amdocs-persist cannot be combined with --glassdoor-debug-search"
        )
    if args.amdocs_persist and args.glassdoor_persist:
        raise ValueError(
            "--amdocs-persist cannot be combined with --glassdoor-persist"
        )
    if args.amdocs_persist and args.glassdoor_persist_one:
        raise ValueError(
            "--amdocs-persist cannot be combined with --glassdoor-persist-one"
        )
    if args.amdocs_persist and args.greenhouse_debug_search:
        raise ValueError(
            "--amdocs-persist cannot be combined with --greenhouse-debug-search"
        )
    if args.amdocs_persist and args.greenhouse_persist:
        raise ValueError(
            "--amdocs-persist cannot be combined with --greenhouse-persist"
        )
    if args.marvell_persist and args.populate_comeet_base_urls:
        raise ValueError(
            "--marvell-persist cannot be combined with --populate-comeet-base-urls"
        )
    if args.marvell_persist and args.comeet_test_scrape:
        raise ValueError(
            "--marvell-persist cannot be combined with --comeet-test-scrape"
        )
    if args.marvell_persist and args.comeet_scrape_all_israel:
        raise ValueError(
            "--marvell-persist cannot be combined with --comeet-scrape-all-israel"
        )
    if args.marvell_persist and args.comeet_persist_all_israel:
        raise ValueError(
            "--marvell-persist cannot be combined with --comeet-persist-all-israel"
        )
    if args.marvell_persist and args.indeed_debug_search:
        raise ValueError(
            "--marvell-persist cannot be combined with --indeed-debug-search"
        )
    if args.marvell_persist and args.indeed_persist:
        raise ValueError(
            "--marvell-persist cannot be combined with --indeed-persist"
        )
    if args.marvell_persist and args.glassdoor_debug_search:
        raise ValueError(
            "--marvell-persist cannot be combined with --glassdoor-debug-search"
        )
    if args.marvell_persist and args.glassdoor_persist:
        raise ValueError(
            "--marvell-persist cannot be combined with --glassdoor-persist"
        )
    if args.marvell_persist and args.glassdoor_persist_one:
        raise ValueError(
            "--marvell-persist cannot be combined with --glassdoor-persist-one"
        )
    if args.marvell_persist and args.greenhouse_debug_search:
        raise ValueError(
            "--marvell-persist cannot be combined with --greenhouse-debug-search"
        )
    if args.marvell_persist and args.greenhouse_persist:
        raise ValueError(
            "--marvell-persist cannot be combined with --greenhouse-persist"
        )
    if args.marvell_persist and args.amdocs_test_scrape:
        raise ValueError(
            "--marvell-persist cannot be combined with --amdocs-test-scrape"
        )
    if args.marvell_persist and args.amdocs_persist:
        raise ValueError(
            "--marvell-persist cannot be combined with --amdocs-persist"
        )
    if args.marvell_persist and args.marvell_israel_test_scrape:
        raise ValueError(
            "--marvell-persist cannot be combined with --marvell-israel-test-scrape"
        )
    if args.scheduler and args.populate_only:
        raise ValueError("--scheduler cannot be combined with --populate-only")
    if args.scheduler and args.populate_comeet_base_urls:
        raise ValueError(
            "--scheduler cannot be combined with --populate-comeet-base-urls"
        )
    if args.scheduler and args.comeet_test_scrape:
        raise ValueError("--scheduler cannot be combined with --comeet-test-scrape")
    if args.scheduler and args.comeet_scrape_all_israel:
        raise ValueError(
            "--scheduler cannot be combined with --comeet-scrape-all-israel"
        )
    if args.scheduler and args.comeet_persist_all_israel:
        raise ValueError(
            "--scheduler cannot be combined with --comeet-persist-all-israel"
        )
    if args.scheduler and args.greenhouse_debug_search:
        raise ValueError("--greenhouse-debug-search cannot be combined with --scheduler")
    if args.scheduler and args.greenhouse_persist:
        raise ValueError("--greenhouse-persist cannot be combined with --scheduler")
    if args.indeed_debug_search and args.scheduler:
        raise ValueError("--indeed-debug-search cannot be combined with --scheduler")
    if args.indeed_persist and args.scheduler:
        raise ValueError("--indeed-persist cannot be combined with --scheduler")
    if args.glassdoor_debug_search and args.scheduler:
        raise ValueError(
            "--glassdoor-debug-search cannot be combined with --scheduler"
        )
    if args.glassdoor_persist and args.scheduler:
        raise ValueError(
            "--glassdoor-persist cannot be combined with --scheduler"
        )
    if args.glassdoor_persist_one and args.scheduler:
        raise ValueError(
            "--glassdoor-persist-one cannot be combined with --scheduler"
        )
    if args.amdocs_test_scrape and args.scheduler:
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --scheduler"
        )
    if args.amdocs_persist and args.scheduler:
        raise ValueError(
            "--amdocs-persist cannot be combined with --scheduler"
        )
    if args.apple_persist and args.scheduler:
        raise ValueError("--apple-persist cannot be combined with --scheduler")
    if args.google_careers_persist and args.scheduler:
        raise ValueError(
            "--google-careers-persist cannot be combined with --scheduler"
        )
    if args.microsoft_persist and args.scheduler:
        raise ValueError("--microsoft-persist cannot be combined with --scheduler")
    if args.marvell_persist and args.scheduler:
        raise ValueError(
            "--marvell-persist cannot be combined with --scheduler"
        )
    if args.redhat_persist and args.scheduler:
        raise ValueError("--redhat-persist cannot be combined with --scheduler")
    if (
        args.indeed_debug_search
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--indeed-debug-search cannot be combined with --execution-mode"
        )
    if (
        args.indeed_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError("--indeed-persist cannot be combined with --execution-mode")
    if (
        args.glassdoor_debug_search
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--glassdoor-debug-search cannot be combined with --execution-mode"
        )
    if (
        args.glassdoor_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--glassdoor-persist cannot be combined with --execution-mode"
        )
    if (
        args.glassdoor_persist_one
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--glassdoor-persist-one cannot be combined with --execution-mode"
        )
    if (
        args.greenhouse_debug_search
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --execution-mode"
        )
    if (
        args.greenhouse_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--greenhouse-persist cannot be combined with --execution-mode"
        )
    if (
        args.populate_comeet_base_urls
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--populate-comeet-base-urls cannot be combined with --execution-mode"
        )
    if (
        args.comeet_test_scrape
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--comeet-test-scrape cannot be combined with --execution-mode"
        )
    if (
        args.comeet_scrape_all_israel
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--comeet-scrape-all-israel cannot be combined with --execution-mode"
        )
    if (
        args.comeet_persist_all_israel
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--comeet-persist-all-israel cannot be combined with --execution-mode"
        )
    if (
        args.comeet_persist_all_india
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--comeet-persist-all-india cannot be combined with --execution-mode"
        )
    if (
        args.linkedin_scrape_india
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--linkedin-scrape-india cannot be combined with --execution-mode"
        )
    if (
        args.linkedin_scrape_india_sharded
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--linkedin-scrape-india-sharded cannot be combined with --execution-mode"
        )
    if (
        args.linkedin_persist_india_sharded
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--linkedin-persist-india-sharded cannot be combined with --execution-mode"
        )
    if (
        args.amdocs_test_scrape
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--amdocs-test-scrape cannot be combined with --execution-mode"
        )
    if (
        args.amdocs_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--amdocs-persist cannot be combined with --execution-mode"
        )
    if (
        args.apple_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--apple-persist cannot be combined with --execution-mode"
        )
    if (
        args.google_careers_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--google-careers-persist cannot be combined with --execution-mode"
        )
    if (
        args.microsoft_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--microsoft-persist cannot be combined with --execution-mode"
        )
    if (
        args.marvell_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--marvell-persist cannot be combined with --execution-mode"
        )
    if (
        args.redhat_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--redhat-persist cannot be combined with --execution-mode"
        )
    if args.marvell_israel_test_scrape and args.populate_only:
        raise ValueError(
            "--marvell-israel-test-scrape cannot be combined with --populate-only"
        )
    if args.redhat_test_scrape and args.populate_only:
        raise ValueError("--redhat-test-scrape cannot be combined with --populate-only")
    if args.redhat_test_scrape and args.redhat_persist:
        raise ValueError("--redhat-test-scrape cannot be combined with --redhat-persist")
    if args.varonis_test_scrape and args.populate_only:
        raise ValueError(
            "--varonis-test-scrape cannot be combined with --populate-only"
        )
    if args.varonis_test_scrape and args.varonis_persist:
        raise ValueError(
            "--varonis-test-scrape cannot be combined with --varonis-persist"
        )
    if args.marvell_israel_test_scrape and args.populate_comeet_base_urls:
        raise ValueError(
            "--marvell-israel-test-scrape cannot be combined with "
            "--populate-comeet-base-urls"
        )
    if args.marvell_israel_test_scrape and args.scheduler:
        raise ValueError(
            "--marvell-israel-test-scrape cannot be combined with --scheduler"
        )
    if args.redhat_test_scrape and args.populate_comeet_base_urls:
        raise ValueError(
            "--redhat-test-scrape cannot be combined with "
            "--populate-comeet-base-urls"
        )
    if args.redhat_test_scrape and args.scheduler:
        raise ValueError("--redhat-test-scrape cannot be combined with --scheduler")
    if args.varonis_test_scrape and args.scheduler:
        raise ValueError(
            "--varonis-test-scrape cannot be combined with --scheduler"
        )
    if args.varonis_persist and args.scheduler:
        raise ValueError("--varonis-persist cannot be combined with --scheduler")
    if (
        args.marvell_israel_test_scrape
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--marvell-israel-test-scrape cannot be combined with --execution-mode"
        )
    if (
        args.redhat_test_scrape
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--redhat-test-scrape cannot be combined with --execution-mode"
        )
    if (
        args.varonis_test_scrape
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--varonis-test-scrape cannot be combined with --execution-mode"
        )
    if (
        args.varonis_persist
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError("--varonis-persist cannot be combined with --execution-mode")
    if args.greenhouse_debug_search and args.comeet_test_scrape:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --comeet-test-scrape"
        )
    if args.greenhouse_persist and args.comeet_test_scrape:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --comeet-test-scrape"
        )
    if args.greenhouse_debug_search and args.comeet_scrape_all_israel:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --comeet-scrape-all-israel"
        )
    if args.greenhouse_persist and args.comeet_scrape_all_israel:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --comeet-scrape-all-israel"
        )
    if args.greenhouse_debug_search and args.comeet_persist_all_israel:
        raise ValueError(
            "--greenhouse-debug-search cannot be combined with --comeet-persist-all-israel"
        )
    if args.greenhouse_persist and args.comeet_persist_all_israel:
        raise ValueError(
            "--greenhouse-persist cannot be combined with --comeet-persist-all-israel"
        )
    if (
        args.execution_mode
        in {
            LinkedInScrapeMode.INSPECT_SINGLE_JOB.value,
            LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value,
        }
        and args.populate_only
    ):
        raise ValueError(
            "--populate-only cannot be combined with LinkedIn inspect execution modes"
        )
    if (
        args.execution_mode
        in {
            LinkedInScrapeMode.INSPECT_SINGLE_JOB.value,
            LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value,
        }
        and args.num_of_min is not None
    ):
        raise ValueError(
            "--num-of-min cannot be combined with LinkedIn inspect execution modes"
        )
    if (
        args.execution_mode == LinkedInScrapeMode.UNTIL_LAST_PAGE.value
        and args.num_of_min is None
    ):
        raise ValueError(
            "--num-of-min is required with --execution-mode until-last-page"
        )
    if (
        args.execution_mode != LinkedInScrapeMode.UNTIL_LAST_PAGE.value
        and args.num_of_min is not None
    ):
        raise ValueError(
            "--num-of-min can only be used with --execution-mode until-last-page"
        )
    if args.scheduler and args.execution_mode != LinkedInScrapeMode.DEFAULT.value:
        raise ValueError("--scheduler cannot be combined with --execution-mode")
    if (
        args.linkedin_persist_india_sharded_scheduler
        and args.execution_mode != LinkedInScrapeMode.DEFAULT.value
    ):
        raise ValueError(
            "--linkedin-persist-india-sharded-scheduler cannot be combined "
            "with --execution-mode"
        )
    if args.execution_mode == LinkedInScrapeMode.INSPECT_SINGLE_JOB.value:
        _build_single_job_url(args)
    if args.execution_mode == LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value:
        _build_single_profile_url(args)

    if _should_print_linkedin_auth_at_startup(args):
        _resolve_and_print_linkedin_auth_context(
            args,
            context="process-startup",
        )

    if args.linkedin_persist_india_sharded_scheduler:
        run_linkedin_persist_india_sharded_scheduler(args)
        return

    if args.company_career_page_probe:
        run_company_career_page_probe(args)
        return

    if args.company_career_pages_table_only:
        run_company_career_pages_table_only_scheduler(args)
        return

    if args.company_career_pages_now:
        run_company_career_pages_now(args)
        return

    if args.company_career_pages:
        run_company_career_pages_scheduler(args)
        return

    if args.scheduler:
        run_scheduler(args)
        return

    if args.redhat_test_scrape:
        run_redhat_test_scrape(args)
        return

    if args.redhat_persist:
        jobs, db_summary = run_redhat_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_redhat_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="redhat"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.varonis_test_scrape:
        run_varonis_test_scrape(args)
        return

    if args.varonis_persist:
        jobs, db_summary = run_varonis_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_varonis_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="varonis"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.marvell_israel_test_scrape:
        run_marvell_israel_test_scrape(args)
        return

    if args.marvell_persist:
        jobs, db_summary = run_marvell_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_marvell_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="marvell"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.amdocs_test_scrape:
        run_amdocs_test_scrape(args)
        return

    if args.amdocs_persist:
        jobs, db_summary = run_amdocs_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_amdocs_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="amdocs"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.apple_persist:
        jobs, db_summary = run_apple_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_apple_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="apple"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.google_careers_persist:
        jobs, db_summary = run_google_careers_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_google_careers_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(
                        args.output, site="google_careers"
                    ),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.microsoft_persist:
        jobs, db_summary = run_microsoft_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_microsoft_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="microsoft"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.indeed_debug_search:
        run_indeed_debug_search(args)
        return

    if args.glassdoor_debug_search:
        run_glassdoor_debug_search(args)
        return

    if args.glassdoor_persist:
        jobs, db_summary = run_glassdoor_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_glassdoor_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="glassdoor"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.glassdoor_persist_one:
        jobs, db_summary = run_glassdoor_persist(args, results_wanted=1)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_glassdoor_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="glassdoor"),
                    jobs=jobs,
                    db_summary=db_summary,
                    results_requested=1,
                )
            ],
        )
        return

    if args.greenhouse_debug_search:
        run_greenhouse_debug_search(args)
        return

    if args.greenhouse_persist:
        jobs, db_summary = run_greenhouse_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_greenhouse_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="greenhouse"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.indeed_persist:
        jobs, db_summary = run_indeed_persist(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_indeed_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="indeed"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.populate_comeet_base_urls:
        run_populate_comeet_base_urls(args)
        return

    if args.comeet_test_scrape:
        run_comeet_test_scrape(args)
        return

    if args.comeet_scrape_all_israel:
        run_comeet_scrape_all_israel(args)
        return

    if args.comeet_persist_all_israel:
        jobs, db_summary = run_comeet_persist_all_israel(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_comeet_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="comeet"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    if args.comeet_persist_all_india:
        run_comeet_persist_all_india(args)
        return

    if args.linkedin_scrape_india:
        run_linkedin_scrape_india(args)
        return

    if args.linkedin_scrape_india_sharded:
        run_linkedin_scrape_india_sharded(args)
        return

    if args.linkedin_persist_india_sharded:
        jobs, db_summary = run_linkedin_persist_india_sharded(args)
        _publish_scrape_finished_event(
            args,
            runs=[
                _build_linkedin_india_sharded_scrape_run_report(
                    args,
                    output_path=_resolve_output_path(args.output, site="linkedin"),
                    jobs=jobs,
                    db_summary=db_summary,
                )
            ],
        )
        return

    jobs, db_summary = run_once(args)
    _publish_scrape_finished_event(
        args,
        runs=[
            _build_linkedin_scrape_run_report(
                args,
                output_path=_resolve_output_path(args.output, site="linkedin"),
                jobs=jobs,
                db_summary=db_summary,
            ),
            _build_redhat_scrape_run_report(
                args,
                output_path=_resolve_output_path(args.output, site="linkedin"),
                jobs=jobs,
                db_summary=db_summary,
            ),
        ],
    )


if __name__ == "__main__":
    main()
