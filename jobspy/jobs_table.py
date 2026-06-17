from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jobspy.model import JobType
from jobspy.util import get_enum_from_job_type


LINKEDIN_SOURCE = "linkedin"
INDEED_SOURCE = "indeed"
COMEET_SOURCE = "comeet"
GREENHOUSE_SOURCE = "greenhouse"
GLASSDOOR_SOURCE = "glassdoor"
EIGHTFOLD_SOURCE = "eightfold"
WORKDAY_SOURCE = "workday"
REDHAT_SOURCE = "redhat"
VARONIS_SOURCE = "varonis"
APPLE_SOURCE = "apple"
MICROSOFT_SOURCE = "microsoft"
META_SOURCE = "meta"
JSON_FEED_SOURCE = "json_feed"
GOOGLE_SOURCE = "google"
ZIP_RECRUITER_SOURCE = "zip_recruiter"
BAYT_SOURCE = "bayt"
NAUKRI_SOURCE = "naukri"
BDJOBS_SOURCE = "bdjobs"
COMEET_JOBS_URL_PREFIX = "https://www.comeet.com/jobs"
JOBS_TABLE_NAME = "jobs"
JOBS_IS_DUPLICATE_COLUMN_NAME = "is_duplicate"
JOBS_REPOSTED_AT_COLUMN_NAME = "reposted_at"
JOBS_JOB_URL_UNIQUE_INDEX_NAME = "idx_jobs_job_url"
JOBS_DEDUP_MAPPING_TABLE_NAME = "tmp_jobs_job_url_dedup_map"
JOBS_PARSED_TABLE_NAME = "jobs_parsed"
JOBS_PARSED_RAW_JOB_ID_COLUMN_NAME = "raw_job_id"
JOBS_PARSED_STATUS_COLUMN_NAME = "status"
JOBS_PARSED_ACTIVE_STATUS_VALUE = "active"
COMPANY_COMEET_JOB_URLS_TABLE_NAME = "company_comeet_job_urls"
COMPANY_CAREER_PAGES_TABLE_NAME = "company_career_pages"
NICE_GREENHOUSE_JOBS_URL = (
    "https://boards-api.greenhouse.io/v1/boards/nice/jobs?content=true"
)
NICE_COMPANY_URL = "https://www.nice.com/careers"
HIBOB_JOBS_API_URL = "https://hibob-fa0ad69d0cb34a.careers.hibob.com/api/job-ad"
NICE_JSON_FEED_CONFIG = {
    "company_name": "NICE",
    "company_url": NICE_COMPANY_URL,
    "field_paths": {
        "id": "id",
        "title": "title",
        "job_url": "absolute_url",
        "apply_url": "absolute_url",
        "job_url_direct": "absolute_url",
        "city": "location.name",
        "description": "content",
        "listing_type": "metadata.Job Type.value",
        "job_function": "metadata.Category.value",
    },
    "constants": {"country": "Israel"},
    "location_filter_paths": ["location.name"],
}


def _greenhouse_public_json_feed_config(
    company_name: str,
    company_url: str,
) -> dict[str, Any]:
    return {
        "company_name": company_name,
        "company_url": company_url,
        "field_paths": {
            "id": "id",
            "title": "title",
            "job_url": "absolute_url",
            "apply_url": "absolute_url",
            "job_url_direct": "absolute_url",
            "city": "location.name",
            "description": "content",
            "listing_type": "metadata.Job Type.value",
            "job_function": "metadata.Category.value",
        },
        "constants": {"country": "Israel"},
        "location_filter_paths": ["location.name"],
    }


MONDAY_JSON_FEED_CONFIG = {
    "html_json_script_id": "__NEXT_DATA__",
    "rows_path": (
        "props.pageProps.dynamicData."
        "fd303451-80d2-4029-8e00-685006289b60.positions"
    ),
    "company_name": "monday.com",
    "company_url": "https://monday.com/careers/",
    "field_paths": {
        "id": "uid",
        "title": "name",
        "city": "location.name",
        "listing_type": "employment_type",
        "job_function": "department",
    },
    "templates": {
        "job_url": "https://monday.com/careers/{uid}",
        "apply_url": "https://monday.com/careers/{uid}",
        "job_url_direct": "https://monday.com/careers/{uid}",
    },
    "detail_fetch": {
        "html_json_script_id": "__NEXT_DATA__",
        "payload_path": "props.pageProps.positionData",
        "description_sections": [
            {"title": "Description", "path": "positionDescription"},
            {"title": "Responsibilities", "path": "positionResponsibilities"},
            {"title": "Requirements", "path": "positionRequirements"},
            {"title": "Team", "path": "teamDescription"},
        ],
    },
    "constants": {"country": "Israel"},
    "location_filter_paths": ["location.name", "location.city"],
}
MATRIX_HTML_FEED_CONFIG = {
    "html_row_selector": ".hot-jobs-row .col-md-3",
    "html_fields": {
        "title": {"selector": "a h3"},
        "job_url": {
            "selector": "a[href*='/jobs/']",
            "attr": "href",
            "urljoin": True,
        },
        "description": {"selector": ".excerpt"},
    },
    "company_name": "Matrix",
    "company_url": "https://www.matrix.co.il/jobs/",
    "field_paths": {
        "title": "title",
        "job_url": "job_url",
        "apply_url": "job_url",
        "job_url_direct": "job_url",
        "description": "description",
    },
    "constants": {"country": "Israel"},
}
HIBOB_JSON_FEED_CONFIG = {
    "headers": {"companyIdentifier": "hibob-fa0ad69d0cb34a"},
    "rows_path": "jobAdDetails",
    "company_name": "HiBob",
    "company_url": "https://www.hibob.com/careers/",
    "field_paths": {
        "id": "id",
        "title": "title",
        "city": "site",
        "country": "country",
        "description": "description",
        "listing_type": "employmentType",
        "job_function": "department",
    },
    "templates": {
        "job_url": (
            "https://hibob-fa0ad69d0cb34a.careers.hibob.com/jobs/{id}"
        ),
        "apply_url": (
            "https://hibob-fa0ad69d0cb34a.careers.hibob.com/jobs/{id}"
        ),
        "job_url_direct": (
            "https://hibob-fa0ad69d0cb34a.careers.hibob.com/jobs/{id}"
        ),
    },
    "constants": {"country": "Israel"},
    "location_filter_paths": ["country", "site"],
}
GTECH_HTML_FEED_CONFIG = {
    "html_row_selector": ".elementor-post",
    "html_fields": {
        "title": {"selector": ".elementor-post__title a"},
        "job_url": {
            "selector": ".elementor-post__title a",
            "attr": "href",
            "urljoin": True,
        },
        "description": {"selector": ".elementor-post__excerpt"},
    },
    "company_name": "Gtech",
    "company_url": "https://gtech.co.il/%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/",
    "field_paths": {
        "title": "title",
        "job_url": "job_url",
        "apply_url": "job_url",
        "job_url_direct": "job_url",
        "description": "description",
    },
    "constants": {"country": "Israel"},
}
LINKEDIN_JOB_URL_PATTERN = re.compile(r"/jobs/view/(?:[^/?#]+-)?(?P<job_id>\d+)")
LINKEDIN_COMPANY_URL_PATTERN = re.compile(r"/company/(?P<company_id>[^/?#]+)")
INDEED_COMPANY_URL_PATTERN = re.compile(r"/cmp/(?P<company_id>[^/?#]+)")
GLASSDOOR_COMPANY_URL_PATTERN = re.compile(r"/W-EI_IE(?P<company_id>\d+)\.htm")
GREENHOUSE_JOB_URL_PATH_ID_PATTERN = re.compile(r"/(?P<job_id>\d+)(?:/)?$")
WORKDAY_JOB_URL_EXTERNAL_ID_PATTERN = re.compile(r"_(?P<job_id>[^/?#]+)$")
VARONIS_JOB_URL_EXTERNAL_ID_PATTERN = re.compile(r"/job/(?P<job_id>[^/?#]+)")
APPLE_JOB_URL_PATTERN = re.compile(r"/details/(?P<job_id>[^/?#]+)")
META_JOB_URL_PATTERN = re.compile(r"/jobs/(?P<job_id>\d+)")
PG_ENV_KEYS = ("PG_HOST", "PG_PORT", "PG_DB", "PG_USER", "PG_PASSWORD")
AIRTABLE_EXPORT_TABLE_KEYS = ("data", "table")
AIRTABLE_ROW_CELL_VALUES_KEY = "cellValuesByColumnId"
COMEET_AIRTABLE_CAREER_LINK_COLUMN_ID = "fldHm56Wa148CQZ8h"
COMEET_AIRTABLE_COMPANY_NAME_COLUMN_ID = "fldLT11B0cpV6p9Uz"
PROTECTED_RAW_JSON_DATE_POSTED_KEY = "date_posted"
JOB_UPSERT_IGNORED_CHANGE_FIELDS = {
    "title",
    "location",
    "company_name",
    "company_url",
    "company_id",
    "description",
    "applications_count",
    "contract_type",
    "experience_level",
    "work_type",
    "sector",
    "salary",
    "poster_full_name",
    "poster_profile_url",
    "apply_url",
    "apply_type",
    "benefits",
    "source",
    "external_id",
}
JOB_UPSERT_SUMMARY_COLUMNS = [
    "title",
    "location",
    "company_name",
    "company_url",
    "company_id",
    "description",
    "applications_count",
    "contract_type",
    "experience_level",
    "work_type",
    "sector",
    "salary",
    "poster_full_name",
    "poster_profile_url",
    "apply_url",
    "apply_type",
    "benefits",
    "source",
    "external_id",
]


def _get_job_upsert_comparable_columns(
    *,
    include_duplicate_flag: bool = False,
) -> list[str]:
    comparable_columns = [
        column
        for column in JOB_UPSERT_SUMMARY_COLUMNS
        if column not in JOB_UPSERT_IGNORED_CHANGE_FIELDS
    ]
    if include_duplicate_flag:
        comparable_columns.append(JOBS_IS_DUPLICATE_COLUMN_NAME)
    return comparable_columns
DIRECT_COMPANY_CAREER_PAGE_MARKER_KEYS = (
    "direct_company_career_page_id",
    "direct_company_career_page_key",
)
JOB_BOARD_DUPLICATE_SOURCES = {
    LINKEDIN_SOURCE,
    INDEED_SOURCE,
    GLASSDOOR_SOURCE,
    GREENHOUSE_SOURCE,
    COMEET_SOURCE,
    GOOGLE_SOURCE,
    ZIP_RECRUITER_SOURCE,
    BAYT_SOURCE,
    NAUKRI_SOURCE,
    BDJOBS_SOURCE,
}
DEFAULT_COMPANY_CAREER_PAGE_ROWS = (
    {
        "company_key": "amdocs",
        "company_name": "Amdocs",
        "company_aliases": [],
        "scraper_site": "eightfold",
        "career_page_url": (
            "https://jobs.amdocs.com/careers"
            "?start=0&location=Israel&pid=563431010318975"
            "&sort_by=match&filter_include_remote=1"
        ),
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "nvidia",
        "company_name": "NVIDIA",
        "company_aliases": ["Nvidia"],
        "scraper_site": "eightfold",
        "career_page_url": (
            "https://jobs.nvidia.com/careers"
            "?start=0&location=Israel&pid=893395263607"
            "&sort_by=distance&filter_include_remote=0"
        ),
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "redhat",
        "company_name": "Red Hat",
        "company_aliases": ["Careers at Red Hat"],
        "scraper_site": "redhat",
        "career_page_url": (
            "https://redhat.wd5.myworkdayjobs.com/jobs/"
            "?a=084562884af243748dad7c84c304d89a"
        ),
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "varonis",
        "company_name": "Varonis",
        "company_aliases": [],
        "scraper_site": "varonis",
        "career_page_url": "https://careers.varonis.com/",
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "elbit",
        "company_name": "Elbit Systems Israel",
        "company_aliases": ["Elbit Systems"],
        "scraper_site": "json_feed",
        "career_page_url": "https://elbitsystemscareer.com/cron/jobs.json",
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {
            "json_feed_config": {
                "company_name": "Elbit Systems Israel",
                "company_url": "https://elbitsystemscareer.com/",
                "field_paths": {
                    "id": "jobId",
                    "title": "jobTitle",
                    "date_posted": "openDate",
                    "job_function": "employerName",
                    "listing_type": "employmentType",
                },
                "templates": {
                    "job_url": "https://elbitsystemscareer.com/job/?jid={jobId}",
                    "apply_url": "https://elbitsystemscareer.com/job/?jid={jobId}",
                    "job_url_direct": "https://elbitsystemscareer.com/job/?jid={jobId}",
                },
                "description_sections": [
                    {"title": "Description", "path": "description"},
                    {"title": "Requirements", "path": "requirements"},
                    {"title": "Skills", "path": "skills"},
                ],
                "constants": {"country": "Israel"},
                "filters": [{"path": "status", "equals": 1}],
            },
        },
    },
    {
        "company_key": "nice",
        "company_name": "NICE",
        "company_aliases": ["NiCE"],
        "scraper_site": "nice",
        "career_page_url": NICE_COMPANY_URL,
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {"json_feed_config": NICE_JSON_FEED_CONFIG},
    },
    {
        "company_key": "apple",
        "company_name": "Apple",
        "company_aliases": [],
        "scraper_site": "apple",
        "career_page_url": "https://jobs.apple.com/en-il/search?location=israel-ISR",
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "google",
        "company_name": "Google",
        "company_aliases": [],
        "scraper_site": "google_careers",
        "career_page_url": (
            "https://www.google.com/about/careers/applications/jobs/results/"
            "?q=&location=Israel&hl=en"
        ),
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "microsoft",
        "company_name": "Microsoft",
        "company_aliases": [],
        "scraper_site": "microsoft",
        "career_page_url": (
            "https://jobs.careers.microsoft.com/global/en/search?lc=Israel"
        ),
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "marvell",
        "company_name": "Marvell",
        "company_aliases": [],
        "scraper_site": "workday",
        "career_page_url": (
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
            "?Country=084562884af243748dad7c84c304d89a"
        ),
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
    },
    {
        "company_key": "finastra",
        "company_name": "Finastra",
        "company_aliases": [],
        "scraper_site": "workday",
        "career_page_url": (
            "https://finastra.wd3.myworkdayjobs.com/FINC"
            "?locations=9ab6e37cf0b510c42416df84b57e102f"
        ),
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
        "detected_platform": "workday",
    },
    {
        "company_key": "matrix",
        "company_name": "Matrix",
        "company_aliases": [],
        "scraper_site": "json_feed",
        "career_page_url": "https://www.matrix.co.il/jobs/",
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {"json_feed_config": MATRIX_HTML_FEED_CONFIG},
        "detected_platform": "html_list",
    },
    {
        "company_key": "nova",
        "company_name": "Nova",
        "company_aliases": ["Nova Ltd.", "Nova Measuring Instruments"],
        "scraper_site": "comeet",
        "career_page_url": "https://www.novami.com/results/?freetext=&location=israel",
        "resolved_fetch_url": "https://www.comeet.com/jobs/nova/A5.007",
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
        "detected_platform": "comeet",
    },
    {
        "company_key": "gong",
        "company_name": "Gong",
        "company_aliases": ["Gong.io"],
        "scraper_site": "json_feed",
        "career_page_url": (
            "https://www.gong.io/careers"
            "?location=Tel+Aviv#careers-listing-section"
        ),
        "resolved_fetch_url": (
            "https://boards-api.greenhouse.io/v1/boards/gongio/jobs?content=true"
        ),
        "search_term": None,
        "location": "Tel Aviv",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {
            "json_feed_config": _greenhouse_public_json_feed_config(
                "Gong",
                "https://www.gong.io/careers",
            ),
        },
        "detected_platform": "greenhouse_public_board",
    },
    {
        "company_key": "monday",
        "company_name": "monday.com",
        "company_aliases": ["Monday", "Monday.com"],
        "scraper_site": "json_feed",
        "career_page_url": "https://monday.com/careers/?location=telaviv",
        "search_term": None,
        "location": "Tel Aviv",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {"json_feed_config": MONDAY_JSON_FEED_CONFIG},
        "detected_platform": "next_data",
    },
    {
        "company_key": "towersemi",
        "company_name": "Tower Semiconductor",
        "company_aliases": ["TowerSemi", "Tower Semiconductor Ltd."],
        "scraper_site": "json_feed",
        "career_page_url": "https://careers.towersemi.com/our-loactions/israel/",
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "enabled": False,
        "status": "unsupported",
        "extra_params": {},
        "detected_platform": "custom_wordpress_salesforce",
    },
    {
        "company_key": "fiverr",
        "company_name": "Fiverr",
        "company_aliases": [],
        "scraper_site": "comeet",
        "career_page_url": "https://www.fiverr.com/jobs/teams?location=tlv",
        "resolved_fetch_url": "https://www.comeet.com/jobs/fiverr/60.002",
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {},
        "detected_platform": "comeet",
    },
    {
        "company_key": "similarweb",
        "company_name": "Similarweb",
        "company_aliases": ["SimilarWeb"],
        "scraper_site": "json_feed",
        "career_page_url": "https://www.similarweb.com/corp/careers/#opportunities",
        "resolved_fetch_url": (
            "https://boards-api.greenhouse.io/v1/boards/similarweb/jobs?content=true"
        ),
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {
            "json_feed_config": _greenhouse_public_json_feed_config(
                "Similarweb",
                "https://www.similarweb.com/corp/careers/",
            ),
        },
        "detected_platform": "greenhouse_public_board",
    },
    {
        "company_key": "hibob",
        "company_name": "HiBob",
        "company_aliases": ["Hibob", "Bob"],
        "scraper_site": "json_feed",
        "career_page_url": "https://www.hibob.com/careers/",
        "resolved_fetch_url": HIBOB_JOBS_API_URL,
        "search_term": None,
        "location": "Israel",
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {"json_feed_config": HIBOB_JSON_FEED_CONFIG},
        "detected_platform": "json_feed",
    },
    {
        "company_key": "gtech",
        "company_name": "Gtech",
        "company_aliases": [],
        "scraper_site": "json_feed",
        "career_page_url": "https://gtech.co.il/%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/",
        "search_term": None,
        "location": None,
        "country_indeed": "Israel",
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": 60,
        "extra_params": {"json_feed_config": GTECH_HTML_FEED_CONFIG},
        "detected_platform": "html_list",
    },
)
CREATE_COMPANY_COMEET_JOB_URLS_TABLE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {COMPANY_COMEET_JOB_URLS_TABLE_NAME} (
        comeet_base_url TEXT PRIMARY KEY,
        company_name TEXT,
        comeet_company_slug TEXT NOT NULL,
        comeet_company_code TEXT NOT NULL,
        source_job_url TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""
CREATE_COMPANY_CAREER_PAGES_TABLE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {COMPANY_CAREER_PAGES_TABLE_NAME} (
        id BIGSERIAL PRIMARY KEY,
        company_key TEXT NOT NULL UNIQUE,
        company_name TEXT NOT NULL,
        company_aliases TEXT[] NOT NULL DEFAULT '{{}}'::text[],
        scraper_site TEXT NOT NULL,
        career_page_url TEXT NOT NULL,
        search_term TEXT,
        location TEXT,
        country_indeed TEXT NOT NULL DEFAULT 'Israel',
        results_wanted INTEGER NOT NULL DEFAULT 0,
        description_format TEXT NOT NULL DEFAULT 'markdown',
        description_limit INTEGER,
        request_timeout INTEGER NOT NULL DEFAULT 60,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        extra_params JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        status TEXT NOT NULL DEFAULT 'active',
        detected_platform TEXT,
        resolved_fetch_url TEXT,
        validation_report JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        sample_jobs JSONB NOT NULL DEFAULT '[]'::jsonb,
        last_validated_at TIMESTAMPTZ,
        activated_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""
ALTER_COMPANY_CAREER_PAGES_TABLE_SQL = f"""
    ALTER TABLE {COMPANY_CAREER_PAGES_TABLE_NAME}
        ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active',
        ADD COLUMN IF NOT EXISTS detected_platform TEXT,
        ADD COLUMN IF NOT EXISTS resolved_fetch_url TEXT,
        ADD COLUMN IF NOT EXISTS validation_report JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        ADD COLUMN IF NOT EXISTS sample_jobs JSONB NOT NULL DEFAULT '[]'::jsonb,
        ADD COLUMN IF NOT EXISTS last_validated_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ
"""


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = _safe_str(value)
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value

    return values


def _load_pg_config() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    sibling_env = Path(__file__).resolve().parents[2] / "career-agents" / ".env"
    env_paths = [repo_root / ".env", sibling_env]

    config = {key: _safe_str(os.getenv(key)) for key in PG_ENV_KEYS}
    for env_path in env_paths:
        if all(config.values()):
            break
        env_values = _load_env_file(env_path)
        for key in PG_ENV_KEYS:
            if not config.get(key) and env_values.get(key):
                config[key] = env_values[key]
                os.environ.setdefault(key, env_values[key])

    missing = [key for key, value in config.items() if not value]
    if missing:
        searched = ", ".join(str(path) for path in env_paths)
        raise RuntimeError(
            f"Missing PostgreSQL env vars: {', '.join(missing)}. "
            f"Checked current environment and env files: {searched}"
        )

    return {
        "host": config["PG_HOST"],
        "port": int(config["PG_PORT"] or "5432"),
        "dbname": config["PG_DB"],
        "user": config["PG_USER"],
        "password": config["PG_PASSWORD"],
    }


def _format_population_summary(summary: dict[str, Any]) -> str:
    lines = ["{"]
    items = list(summary.items())
    for index, (key, value) in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        lines.append(f'  "{key}": {json.dumps(value, ensure_ascii=False)}{suffix}')
    lines.append("}")
    return "\n".join(lines)


def _get_db_connection():
    import psycopg2

    return psycopg2.connect(**_load_pg_config())


def _normalize_company_match_key(value: Any) -> str | None:
    text = _safe_str(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", text).casefold()


def _coerce_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]

    resolved: list[str] = []
    for item in items:
        normalized = _safe_str(item)
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return resolved


def _ensure_company_career_pages_table(
    cursor,
    *,
    seed_defaults: bool = False,
) -> None:
    from psycopg2.extras import Json

    cursor.execute(CREATE_COMPANY_CAREER_PAGES_TABLE_SQL)
    cursor.execute(ALTER_COMPANY_CAREER_PAGES_TABLE_SQL)
    cursor.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_company_career_pages_company_name
        ON {COMPANY_CAREER_PAGES_TABLE_NAME} (LOWER(BTRIM(company_name)))
        """
    )
    if not seed_defaults:
        return

    insert_sql = f"""
        INSERT INTO {COMPANY_CAREER_PAGES_TABLE_NAME} (
            company_key,
            company_name,
            company_aliases,
            scraper_site,
            career_page_url,
            search_term,
            location,
            country_indeed,
            results_wanted,
            description_format,
            description_limit,
            request_timeout,
            enabled,
            extra_params,
            status,
            detected_platform,
            resolved_fetch_url,
            created_at,
            updated_at,
            activated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, NOW(), NOW(), CASE WHEN %s THEN NOW() ELSE NULL END
        )
        ON CONFLICT (company_key) DO UPDATE SET
            company_name = EXCLUDED.company_name,
            company_aliases = EXCLUDED.company_aliases,
            scraper_site = EXCLUDED.scraper_site,
            career_page_url = EXCLUDED.career_page_url,
            search_term = EXCLUDED.search_term,
            location = EXCLUDED.location,
            country_indeed = EXCLUDED.country_indeed,
            results_wanted = EXCLUDED.results_wanted,
            description_format = EXCLUDED.description_format,
            description_limit = EXCLUDED.description_limit,
            request_timeout = EXCLUDED.request_timeout,
            extra_params = EXCLUDED.extra_params,
            detected_platform = EXCLUDED.detected_platform,
            resolved_fetch_url = EXCLUDED.resolved_fetch_url,
            updated_at = NOW()
        WHERE
            {COMPANY_CAREER_PAGES_TABLE_NAME}.company_name
                IS DISTINCT FROM EXCLUDED.company_name
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.company_aliases
                IS DISTINCT FROM EXCLUDED.company_aliases
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.scraper_site
                IS DISTINCT FROM EXCLUDED.scraper_site
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.career_page_url
                IS DISTINCT FROM EXCLUDED.career_page_url
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.search_term
                IS DISTINCT FROM EXCLUDED.search_term
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.location
                IS DISTINCT FROM EXCLUDED.location
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.country_indeed
                IS DISTINCT FROM EXCLUDED.country_indeed
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.results_wanted
                IS DISTINCT FROM EXCLUDED.results_wanted
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.description_format
                IS DISTINCT FROM EXCLUDED.description_format
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.description_limit
                IS DISTINCT FROM EXCLUDED.description_limit
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.request_timeout
                IS DISTINCT FROM EXCLUDED.request_timeout
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.extra_params
                IS DISTINCT FROM EXCLUDED.extra_params
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.detected_platform
                IS DISTINCT FROM EXCLUDED.detected_platform
            OR {COMPANY_CAREER_PAGES_TABLE_NAME}.resolved_fetch_url
                IS DISTINCT FROM EXCLUDED.resolved_fetch_url
    """
    for row in DEFAULT_COMPANY_CAREER_PAGE_ROWS:
        enabled = bool(row.get("enabled", True))
        status = _safe_str(row.get("status")) or ("active" if enabled else "disabled")
        cursor.execute(
            insert_sql,
            (
                row["company_key"],
                row["company_name"],
                row["company_aliases"],
                row["scraper_site"],
                row["career_page_url"],
                row["search_term"],
                row["location"],
                row["country_indeed"],
                row["results_wanted"],
                row["description_format"],
                row["description_limit"],
                row["request_timeout"],
                enabled,
                Json(row["extra_params"]),
                status,
                _safe_str(row.get("detected_platform")) or row["scraper_site"],
                _safe_str(row.get("resolved_fetch_url")),
                enabled,
            ),
        )


def ensure_company_career_pages_table(*, seed_defaults: bool = False) -> None:
    conn = _get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                _ensure_company_career_pages_table(
                    cursor,
                    seed_defaults=seed_defaults,
                )
    finally:
        conn.close()


def _company_career_page_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "company_key": row[1],
        "company_name": row[2],
        "company_aliases": _coerce_text_list(row[3]),
        "scraper_site": row[4],
        "career_page_url": row[5],
        "search_term": row[6],
        "location": row[7],
        "country_indeed": row[8],
        "results_wanted": row[9],
        "description_format": row[10],
        "description_limit": row[11],
        "request_timeout": row[12],
        "enabled": row[13],
        "extra_params": _coerce_json_object(row[14]),
        "status": row[17] if len(row) > 17 else ("active" if row[13] else "disabled"),
        "detected_platform": row[18] if len(row) > 18 else None,
        "resolved_fetch_url": row[19] if len(row) > 19 else None,
        "validation_report": (
            _coerce_json_object(row[20]) if len(row) > 20 else {}
        ),
        "sample_jobs": row[21] if len(row) > 21 and isinstance(row[21], list) else [],
        "last_validated_at": row[22] if len(row) > 22 else None,
        "activated_at": row[23] if len(row) > 23 else None,
        "created_at": row[15],
        "updated_at": row[16],
    }


def list_company_career_pages(
    *,
    enabled_only: bool = True,
    seed_defaults: bool = False,
) -> list[dict[str, Any]]:
    where_sql = "WHERE enabled IS TRUE" if enabled_only else ""
    query = f"""
        SELECT
            id,
            company_key,
            company_name,
            company_aliases,
            scraper_site,
            career_page_url,
            search_term,
            location,
            country_indeed,
            results_wanted,
            description_format,
            description_limit,
            request_timeout,
            enabled,
            extra_params,
            created_at,
            updated_at,
            status,
            detected_platform,
            resolved_fetch_url,
            validation_report,
            sample_jobs,
            last_validated_at,
            activated_at
        FROM {COMPANY_CAREER_PAGES_TABLE_NAME}
        {where_sql}
        ORDER BY company_name, company_key
    """

    conn = _get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            _ensure_company_career_pages_table(
                cursor,
                seed_defaults=seed_defaults,
            )
            cursor.execute(query)
            rows = cursor.fetchall()
    finally:
        conn.close()

    return [_company_career_page_row_to_dict(row) for row in rows]


def upsert_company_career_page_from_validation(
    validation_result: dict[str, Any],
    *,
    activate: bool = False,
) -> dict[str, Any]:
    from psycopg2.extras import Json

    if activate and not validation_result.get("valid"):
        raise ValueError("Cannot activate an invalid company career-page validation")

    row_config = validation_result.get("row") or {}
    if not isinstance(row_config, dict):
        row_config = {}

    company_key = _safe_str(validation_result.get("company_key")) or _safe_str(
        row_config.get("company_key")
    )
    company_name = _safe_str(validation_result.get("company_name")) or _safe_str(
        row_config.get("company_name")
    )
    scraper_site = _safe_str(row_config.get("scraper_site"))
    career_page_url = _safe_str(row_config.get("career_page_url"))
    resolved_fetch_url = _safe_str(row_config.get("resolved_fetch_url"))
    if not company_key:
        raise ValueError("Validation result is missing company_key")
    if not company_name:
        raise ValueError("Validation result is missing company_name")
    if not scraper_site:
        raise ValueError("Validation result is missing scraper_site")
    if not career_page_url:
        raise ValueError("Validation result is missing career_page_url")

    is_valid = bool(validation_result.get("valid"))
    enabled = bool(activate and is_valid)
    status = "active" if enabled else "valid" if is_valid else "failed"
    sample_jobs = validation_result.get("sample_jobs")
    if not isinstance(sample_jobs, list):
        sample_jobs = []

    upsert_sql = f"""
        INSERT INTO {COMPANY_CAREER_PAGES_TABLE_NAME} (
            company_key,
            company_name,
            company_aliases,
            scraper_site,
            career_page_url,
            search_term,
            location,
            country_indeed,
            results_wanted,
            description_format,
            description_limit,
            request_timeout,
            enabled,
            extra_params,
            status,
            detected_platform,
            resolved_fetch_url,
            validation_report,
            sample_jobs,
            last_validated_at,
            activated_at,
            created_at,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, NOW(), CASE WHEN %s THEN NOW() ELSE NULL END,
            NOW(), NOW()
        )
        ON CONFLICT (company_key) DO UPDATE SET
            company_name = EXCLUDED.company_name,
            company_aliases = EXCLUDED.company_aliases,
            scraper_site = EXCLUDED.scraper_site,
            career_page_url = EXCLUDED.career_page_url,
            search_term = EXCLUDED.search_term,
            location = EXCLUDED.location,
            country_indeed = EXCLUDED.country_indeed,
            results_wanted = EXCLUDED.results_wanted,
            description_format = EXCLUDED.description_format,
            description_limit = EXCLUDED.description_limit,
            request_timeout = EXCLUDED.request_timeout,
            enabled = EXCLUDED.enabled,
            extra_params = EXCLUDED.extra_params,
            status = EXCLUDED.status,
            detected_platform = EXCLUDED.detected_platform,
            resolved_fetch_url = EXCLUDED.resolved_fetch_url,
            validation_report = EXCLUDED.validation_report,
            sample_jobs = EXCLUDED.sample_jobs,
            last_validated_at = EXCLUDED.last_validated_at,
            activated_at = CASE
                WHEN EXCLUDED.enabled THEN COALESCE(
                    {COMPANY_CAREER_PAGES_TABLE_NAME}.activated_at,
                    EXCLUDED.activated_at
                )
                ELSE {COMPANY_CAREER_PAGES_TABLE_NAME}.activated_at
            END,
            updated_at = NOW()
        RETURNING id, enabled, status
    """
    params = (
        company_key,
        company_name,
        _coerce_text_list(row_config.get("company_aliases")),
        scraper_site,
        career_page_url,
        _safe_str(row_config.get("search_term")),
        _safe_str(row_config.get("location")),
        _safe_str(row_config.get("country_indeed")) or "Israel",
        _safe_int(row_config.get("results_wanted")) or 0,
        _safe_str(row_config.get("description_format")) or "markdown",
        _safe_int(row_config.get("description_limit")),
        _safe_int(row_config.get("request_timeout")) or 60,
        enabled,
        Json(row_config.get("extra_params") or {}),
        status,
        _safe_str(validation_result.get("detected_platform")),
        resolved_fetch_url,
        Json(validation_result),
        Json(sample_jobs),
        enabled,
    )

    conn = _get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            _ensure_company_career_pages_table(cursor, seed_defaults=False)
            cursor.execute(upsert_sql, params)
            row = cursor.fetchone()
    finally:
        conn.close()

    return {
        "id": row[0] if row else None,
        "company_key": company_key,
        "enabled": bool(row[1]) if row else enabled,
        "status": row[2] if row else status,
    }


def get_company_career_page_company_match_keys(
    *,
    seed_defaults: bool = False,
) -> set[str]:
    query = f"""
        SELECT company_name, company_aliases
        FROM {COMPANY_CAREER_PAGES_TABLE_NAME}
        WHERE enabled IS TRUE
    """

    conn = _get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            _ensure_company_career_pages_table(
                cursor,
                seed_defaults=seed_defaults,
            )
            cursor.execute(query)
            rows = cursor.fetchall()
    finally:
        conn.close()

    match_keys: set[str] = set()
    for company_name, aliases in rows:
        if company_key := _normalize_company_match_key(company_name):
            match_keys.add(company_key)
        for alias in _coerce_text_list(aliases):
            if alias_key := _normalize_company_match_key(alias):
                match_keys.add(alias_key)
    return match_keys


def _parse_json_file(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        rows = payload["jobs"]
    else:
        raise ValueError(
            f"Expected either a JSON array or an object with a 'jobs' array in {json_path}"
        )

    dict_rows = [row for row in rows if isinstance(row, dict)]
    if len(dict_rows) != len(rows):
        raise ValueError(f"Expected every item in {json_path} to be a JSON object")
    return dict_rows


def _parse_company_comeet_job_urls_file(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        rows = payload["jobs"]
    elif isinstance(payload, dict):
        table = None
        nested_data = payload.get(AIRTABLE_EXPORT_TABLE_KEYS[0])
        if isinstance(nested_data, dict):
            table = nested_data.get(AIRTABLE_EXPORT_TABLE_KEYS[1])
        if table is None:
            table = payload.get("table")

        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            raise ValueError(
                "Expected either a JSON array, an object with a 'jobs' array, "
                "or an Airtable-style export with rows at payload['data']['table']['rows']"
            )
        rows = table["rows"]
    else:
        raise ValueError(
            f"Expected a supported company Comeet URL payload in {json_path}"
        )

    dict_rows = [row for row in rows if isinstance(row, dict)]
    if len(dict_rows) != len(rows):
        raise ValueError(f"Expected every item in {json_path} to be a JSON object")
    return dict_rows


def _parse_date(value: Any) -> date | None:
    text = _safe_str(value)
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_job_type_list(value: Any) -> list[JobType] | None:
    if value is None:
        return None

    items = value if isinstance(value, list) else str(value).split(",")
    parsed_items: list[JobType] = []

    for item in items:
        if isinstance(item, JobType):
            enum_value = item
        else:
            normalized = _safe_str(item)
            if not normalized:
                continue
            normalized = normalized.lower().replace(" ", "").replace("-", "")
            enum_value = get_enum_from_job_type(normalized)

        if enum_value and enum_value not in parsed_items:
            parsed_items.append(enum_value)

    return parsed_items or None


def _validate_linkedin_job_url(job_url: Any) -> tuple[str | None, str | None]:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None, None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"}:
        return None, None
    if "linkedin.com" not in parsed.netloc.lower():
        return None, None

    match = LINKEDIN_JOB_URL_PATTERN.search(parsed.path)
    if not match:
        return None, None

    external_id = match.group("job_id")
    canonical_url = f"https://www.linkedin.com/jobs/view/{external_id}"
    return canonical_url, external_id


def _normalize_company(company_url: Any) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url)
    if not company_url_text:
        return None, None

    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"}:
        return company_url_text, None

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    match = LINKEDIN_COMPANY_URL_PATTERN.search(parsed.path)
    company_id = match.group("company_id") if match else None
    return canonical_url, company_id


def _normalize_indeed_company(company_url: Any) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url)
    if not company_url_text:
        return None, None

    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"}:
        return company_url_text, None

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    match = INDEED_COMPANY_URL_PATTERN.search(parsed.path)
    company_id = match.group("company_id") if match else None
    return canonical_url, company_id


def _normalize_glassdoor_company(company_url: Any) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url)
    if not company_url_text:
        return None, None

    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"}:
        return company_url_text, None

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    match = GLASSDOOR_COMPANY_URL_PATTERN.search(parsed.path)
    company_id = match.group("company_id") if match else None
    return canonical_url, company_id


def _build_salary(row: dict[str, Any]) -> str | None:
    min_amount = row.get("min_amount")
    max_amount = row.get("max_amount")
    interval = _safe_str(row.get("interval"))
    currency = _safe_str(row.get("currency"))

    if min_amount is None and max_amount is None and not interval and not currency:
        return None

    parts = []
    if currency:
        parts.append(currency)

    if min_amount is not None and max_amount is not None:
        parts.append(f"{min_amount} - {max_amount}")
    elif min_amount is not None:
        parts.append(str(min_amount))
    elif max_amount is not None:
        parts.append(str(max_amount))

    if interval:
        parts.append(interval)
    return " ".join(parts) or None


def _build_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"
    return None


def _validate_indeed_job_url(job_url: Any) -> tuple[str | None, str | None]:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None, None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"}:
        return None, None
    if "indeed." not in parsed.netloc.lower():
        return None, None

    query = parse_qs(parsed.query)
    external_id = _safe_str((query.get("jk") or [None])[0])
    if not external_id:
        return None, None

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?jk={external_id}"
    return canonical_url, external_id


def _validate_glassdoor_job_url(job_url: Any) -> tuple[str | None, str | None]:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None, None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"}:
        return None, None
    if "glassdoor." not in parsed.netloc.lower():
        return None, None

    query = parse_qs(parsed.query)
    external_id = _safe_str((query.get("jl") or [None])[0])
    if not external_id:
        return None, None

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?jl={external_id}"
    return canonical_url, external_id


def _detect_source(row: dict[str, Any]) -> str:
    source = _safe_str(row.get("site")) or _safe_str(row.get("source"))
    return (source or LINKEDIN_SOURCE).strip().lower()


def _direct_company_career_page_source(row: dict[str, Any]) -> str | None:
    if not any(
        _safe_str(row.get(key)) for key in DIRECT_COMPANY_CAREER_PAGE_MARKER_KEYS
    ):
        return None
    return (
        _safe_str(row.get("direct_company_career_page_company"))
        or _safe_str(row.get("company"))
        or _safe_str(row.get("company_name"))
        or _safe_str(row.get("direct_company_career_page_key"))
    )


def _apply_direct_company_career_page_source(
    row: dict[str, Any],
    record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if record is None:
        return None
    company_source = _direct_company_career_page_source(row)
    if company_source:
        record["source"] = company_source
    return record


def _build_linkedin_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url, external_id = _validate_linkedin_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not external_id or not title:
        return None

    company_url, company_id = _normalize_company(row.get("company_url"))
    published_at = _parse_date(row.get("date_posted"))
    posted_time = _safe_str(row.get("date_posted"))
    applications_count = _safe_int(row.get("applications_count"))
    job_url_direct = _safe_str(row.get("job_url_direct"))
    linkedin_apply_url = _safe_str(row.get("apply_url"))
    apply_url = job_url_direct or linkedin_apply_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": posted_time,
        "published_at": published_at,
        "job_url": job_url,
        "company_name": _safe_str(row.get("company")),
        "company_url": company_url,
        "company_id": company_id,
        "description": _safe_str(row.get("description")),
        "applications_count": applications_count,
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": (
            "external"
            if job_url_direct and job_url_direct == apply_url
            else LINKEDIN_SOURCE if linkedin_apply_url else None
        ),
        "benefits": None,
        "source": LINKEDIN_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _build_indeed_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url, external_id = _validate_indeed_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not external_id or not title:
        return None

    company_url, company_id = _normalize_indeed_company(row.get("company_url"))
    published_at = _parse_date(row.get("date_posted"))
    posted_time = _safe_str(row.get("date_posted"))
    external_apply_url = _safe_str(row.get("job_url_direct"))
    indeed_apply_url = _safe_str(row.get("apply_url"))
    apply_url = external_apply_url or indeed_apply_url or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": posted_time,
        "published_at": published_at,
        "job_url": job_url,
        "company_name": _safe_str(row.get("company")),
        "company_url": company_url,
        "company_id": company_id,
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external" if external_apply_url else "indeed",
        "benefits": None,
        "source": INDEED_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _build_glassdoor_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url, external_id = _validate_glassdoor_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not external_id or not title:
        return None

    company_url, company_id = _normalize_glassdoor_company(row.get("company_url"))
    published_at = _parse_date(row.get("date_posted"))
    posted_time = _safe_str(row.get("date_posted"))
    external_apply_url = _safe_str(row.get("job_url_direct"))
    glassdoor_apply_url = _safe_str(row.get("apply_url"))
    apply_url = external_apply_url or glassdoor_apply_url or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": posted_time,
        "published_at": published_at,
        "job_url": job_url,
        "company_name": _safe_str(row.get("company")),
        "company_url": company_url,
        "company_id": company_id,
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external" if external_apply_url else GLASSDOOR_SOURCE,
        "benefits": None,
        "source": GLASSDOOR_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _validate_eightfold_job_url(job_url: Any) -> str | None:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _normalize_eightfold_company(company_url: Any) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url)
    if not company_url_text:
        return None, None

    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return company_url_text, company_url_text

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return canonical_url or f"{parsed.scheme}://{parsed.netloc}", parsed.netloc.lower()


def _build_eightfold_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace("_", "-").replace(" ", "-")
    return None


def _build_eightfold_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url = _validate_eightfold_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not title:
        return None

    company_url, company_id = _normalize_eightfold_company(row.get("company_url"))
    external_id = (
        _safe_str(row.get("id"))
        or _safe_str(row.get("external_id"))
        or job_url
    )
    apply_url = _safe_str(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or _safe_str(row.get("company")),
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_eightfold_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": EIGHTFOLD_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _validate_workday_job_url(job_url: Any) -> str | None:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _normalize_workday_company(company_url: Any) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url)
    if not company_url_text:
        return None, None

    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return company_url_text, company_url_text

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return canonical_url or f"{parsed.scheme}://{parsed.netloc}", canonical_url


def _extract_workday_external_id(row: dict[str, Any], job_url: str) -> str | None:
    external_id = _safe_str(row.get("id")) or _safe_str(row.get("external_id"))
    if external_id:
        return external_id

    parsed = urlparse(job_url)
    match = WORKDAY_JOB_URL_EXTERNAL_ID_PATTERN.search(parsed.path.rstrip("/"))
    if not match:
        return None
    return _safe_str(match.group("job_id"))


def _build_workday_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace("_", "-").replace(" ", "-")
    return None


def _build_workday_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url = _validate_workday_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not title:
        return None

    company_url, company_id = _normalize_workday_company(row.get("company_url"))
    external_id = _extract_workday_external_id(row, job_url)
    apply_url = _validate_workday_job_url(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or _safe_str(row.get("company")),
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_workday_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": WORKDAY_SOURCE,
        "external_id": external_id or job_url,
        "raw_json": row,
    }


def _validate_varonis_job_url(job_url: Any) -> str | None:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _extract_varonis_external_id(row: dict[str, Any], job_url: str) -> str | None:
    external_id = _safe_str(row.get("id")) or _safe_str(row.get("external_id"))
    if external_id:
        return external_id

    parsed = urlparse(job_url)
    match = VARONIS_JOB_URL_EXTERNAL_ID_PATTERN.search(parsed.path.rstrip("/"))
    if not match:
        return None
    return _safe_str(match.group("job_id"))


def _build_varonis_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace("_", "-").replace(" ", "-")
    return None


def _build_varonis_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url = _validate_varonis_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not title:
        return None

    company_url, company_id = _normalize_eightfold_company(row.get("company_url"))
    external_id = _extract_varonis_external_id(row, job_url)
    apply_url = _safe_str(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or _safe_str(row.get("company")) or "varonis",
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_varonis_work_type(row),
        "sector": _safe_str(row.get("job_function"))
        or _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": VARONIS_SOURCE,
        "external_id": external_id or job_url,
        "raw_json": row,
    }


def _validate_json_feed_job_url(job_url: Any) -> str | None:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    canonical_url = f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
    if parsed.query:
        canonical_url = f"{canonical_url}?{parsed.query}"
    return canonical_url


def _build_json_feed_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace("_", "-").replace(" ", "-")
    return None


def _build_json_feed_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url = _validate_json_feed_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not title:
        return None

    company_url, company_id = _normalize_eightfold_company(row.get("company_url"))
    external_id = (
        _safe_str(row.get("id"))
        or _safe_str(row.get("external_id"))
        or job_url
    )
    apply_url = _validate_json_feed_job_url(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or _safe_str(row.get("company")) or JSON_FEED_SOURCE,
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_json_feed_work_type(row),
        "sector": _safe_str(row.get("job_function"))
        or _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": JSON_FEED_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _validate_apple_job_url(job_url: Any) -> str | None:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"} or "jobs.apple.com" not in parsed.netloc.lower():
        return None

    match = APPLE_JOB_URL_PATTERN.search(parsed.path)
    if not match:
        return None

    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _normalize_apple_company(company_url: Any) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url) or "https://jobs.apple.com"
    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return company_url_text, company_url_text

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return canonical_url or f"{parsed.scheme}://{parsed.netloc}", parsed.netloc.lower()


def _extract_apple_external_id(row: dict[str, Any], job_url: str) -> str | None:
    external_id = _safe_str(row.get("id")) or _safe_str(row.get("external_id"))
    if external_id:
        return external_id

    parsed = urlparse(job_url)
    match = APPLE_JOB_URL_PATTERN.search(parsed.path)
    if not match:
        return None
    return _safe_str(match.group("job_id"))


def _build_apple_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace("_", "-").replace(" ", "-")
    return None


def _build_apple_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url = _validate_apple_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not title:
        return None

    company_url, company_id = _normalize_apple_company(row.get("company_url"))
    external_id = _extract_apple_external_id(row, job_url)
    apply_url = _validate_apple_job_url(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or "jobs.apple.com",
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_apple_work_type(row),
        "sector": _safe_str(row.get("job_function"))
        or _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": APPLE_SOURCE,
        "external_id": external_id or job_url,
        "raw_json": row,
    }


def _build_microsoft_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    record = _build_eightfold_job_record(row)
    if record is None:
        return None
    record["source"] = MICROSOFT_SOURCE
    record["company_id"] = record.get("company_id") or "microsoft"
    return record


def _validate_meta_job_url(job_url: Any) -> tuple[str | None, str | None]:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None, None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"}:
        return None, None
    if parsed.netloc.lower() != "www.metacareers.com":
        return None, None

    match = META_JOB_URL_PATTERN.search(parsed.path)
    if not match:
        return None, None

    external_id = match.group("job_id")
    canonical_url = f"https://www.metacareers.com/jobs/{external_id}/"
    return canonical_url, external_id


def _build_meta_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url, external_id = _validate_meta_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not external_id or not title:
        return None

    company_url, company_id = _normalize_greenhouse_company(
        row.get("company_url"),
        job_url,
    )
    apply_url = _safe_str(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or "www.metacareers.com",
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _safe_str(row.get("listing_type")),
        "sector": _safe_str(row.get("job_function")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": META_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _build_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    source = _detect_source(row)
    record: dict[str, Any] | None = None
    if source == INDEED_SOURCE:
        record = _build_indeed_job_record(row)
    elif source == LINKEDIN_SOURCE:
        record = _build_linkedin_job_record(row)
    elif source == GLASSDOOR_SOURCE:
        record = _build_glassdoor_job_record(row)
    elif source == GREENHOUSE_SOURCE:
        record = _build_greenhouse_job_record(row)
    elif source == COMEET_SOURCE:
        record = _build_comeet_job_record(row)
    elif source == EIGHTFOLD_SOURCE:
        record = _build_eightfold_job_record(row)
    elif source in {WORKDAY_SOURCE, REDHAT_SOURCE}:
        record = _build_workday_job_record(row)
    elif source == VARONIS_SOURCE:
        record = _build_varonis_job_record(row)
    elif source == APPLE_SOURCE:
        record = _build_apple_job_record(row)
    elif source == MICROSOFT_SOURCE:
        record = _build_microsoft_job_record(row)
    elif source == META_SOURCE:
        record = _build_meta_job_record(row)
    elif source == JSON_FEED_SOURCE:
        record = _build_json_feed_job_record(row)
    return _apply_direct_company_career_page_source(row, record)


def _validate_greenhouse_job_url(job_url: Any) -> tuple[str | None, str | None]:
    job_url_text = _safe_str(job_url)
    if not job_url_text:
        return None, None

    parsed = urlparse(job_url_text)
    if parsed.scheme not in {"http", "https"}:
        return None, None

    query = parse_qs(parsed.query)
    external_id = _safe_str((query.get("gh_jid") or [None])[0])
    if not external_id:
        match = GREENHOUSE_JOB_URL_PATH_ID_PATTERN.search(parsed.path.rstrip("/"))
        external_id = match.group("job_id") if match else None
    if not external_id:
        return None, None

    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    if re.search(rf"/{re.escape(external_id)}(?:/|$)", normalized_path):
        canonical_query = ""
    else:
        canonical_query = f"gh_jid={external_id}"

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
    if canonical_query:
        canonical_url = f"{canonical_url}?{canonical_query}"
    return canonical_url, external_id


def _normalize_greenhouse_company(
    company_url: Any,
    fallback_job_url: Any,
) -> tuple[str | None, str | None]:
    company_url_text = _safe_str(company_url)
    if not company_url_text:
        parsed_job_url = urlparse(_safe_str(fallback_job_url) or "")
        if parsed_job_url.scheme in {"http", "https"} and parsed_job_url.netloc:
            company_url_text = f"{parsed_job_url.scheme}://{parsed_job_url.netloc}"

    if not company_url_text:
        return None, None

    parsed = urlparse(company_url_text)
    if parsed.scheme not in {"http", "https"}:
        return company_url_text, company_url_text

    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    company_id = parsed.netloc.lower()
    return canonical_url or f"{parsed.scheme}://{parsed.netloc}", company_id


def _build_greenhouse_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace("_", "-").replace(" ", "-")
    return None


def _build_greenhouse_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url, external_id = _validate_greenhouse_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not external_id or not title:
        return None

    company_url, company_id = _normalize_greenhouse_company(
        row.get("company_url"),
        job_url,
    )
    apply_url = _safe_str(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": company_url,
        "company_id": company_id or _safe_str(row.get("company")),
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_int(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_greenhouse_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external",
        "benefits": None,
        "source": GREENHOUSE_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _validate_comeet_job_url(job_url: Any) -> str | None:
    job_url_text = _safe_str(job_url)
    if not job_url_text or not job_url_text.startswith(COMEET_JOBS_URL_PREFIX):
        return None

    parsed = urlparse(job_url_text)
    if parsed.scheme != "https" or parsed.netloc != "www.comeet.com":
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 5 or path_parts[0] != "jobs":
        return None

    return f"{parsed.scheme}://{parsed.netloc}/{'/'.join(path_parts[:5])}"


def _build_comeet_work_type(row: dict[str, Any]) -> str | None:
    if row.get("is_remote") is True:
        return "remote"

    listing_type = _safe_str(row.get("listing_type"))
    if listing_type:
        return listing_type.lower().replace(" ", "-")
    return None


def _build_comeet_job_record(row: dict[str, Any]) -> dict[str, Any] | None:
    job_url = _validate_comeet_job_url(row.get("job_url"))
    title = _safe_str(row.get("title"))
    if not job_url or not title:
        return None

    comeet_base_url, _, _ = _extract_comeet_company_fields(job_url)
    external_id = job_url
    job_url_direct = _safe_str(row.get("job_url_direct"))
    apply_url = _safe_str(row.get("apply_url")) or job_url

    return {
        "title": title,
        "location": _safe_str(row.get("location")),
        "posted_time": _safe_str(row.get("date_posted")),
        "published_at": _parse_date(row.get("date_posted")),
        "job_url": job_url,
        "company_name": _safe_str(row.get("company"))
        or _safe_str(row.get("company_name")),
        "company_url": _safe_str(row.get("company_url")),
        "company_id": comeet_base_url,
        "description": _safe_str(row.get("description")),
        "applications_count": _safe_str(row.get("applications_count")),
        "contract_type": _safe_str(row.get("job_type")),
        "experience_level": _safe_str(row.get("job_level")),
        "work_type": _build_comeet_work_type(row),
        "sector": _safe_str(row.get("company_industry")),
        "salary": _build_salary(row),
        "poster_full_name": None,
        "poster_profile_url": None,
        "apply_url": apply_url,
        "apply_type": "external" if job_url_direct and job_url_direct != apply_url else COMEET_SOURCE,
        "benefits": None,
        "source": COMEET_SOURCE,
        "external_id": external_id,
        "raw_json": row,
    }


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _merge_job_records(
    existing_record: dict[str, Any],
    candidate_record: dict[str, Any],
) -> dict[str, Any]:
    merged_record = dict(existing_record)
    for key, candidate_value in candidate_record.items():
        if key == "raw_json":
            existing_raw_json = _coerce_json_object(merged_record.get("raw_json"))
            candidate_raw_json = _coerce_json_object(candidate_value)
            merged_record["raw_json"] = {
                **existing_raw_json,
                **candidate_raw_json,
            }
            continue

        if _has_meaningful_value(candidate_value):
            merged_record[key] = candidate_value

    return merged_record


def _build_job_upsert_change_predicate(
    *,
    current_record_ref: str,
    candidate_record_ref: str,
    include_duplicate_flag: bool = False,
) -> str:
    comparable_columns = _get_job_upsert_comparable_columns(
        include_duplicate_flag=include_duplicate_flag
    )

    conditions: list[str] = []
    for column in comparable_columns:
        current_value_ref = f"{current_record_ref}.{column}"
        candidate_value_ref = f"{candidate_record_ref}.{column}"
        if column == "description":
            conditions.append(
                f"{current_value_ref} IS DISTINCT FROM "
                f"{_build_non_blank_text_merge_sql(current_value_ref=current_value_ref, candidate_value_ref=candidate_value_ref)}"
            )
            continue
        conditions.append(
            f"{current_value_ref} IS DISTINCT FROM {candidate_value_ref}"
        )

    effective_raw_json = _build_job_raw_json_merge_sql(
        current_raw_json_ref=f"{current_record_ref}.raw_json",
        candidate_raw_json_ref=f"{candidate_record_ref}.raw_json",
    )
    current_effective_raw_json = _build_job_raw_json_change_comparison_sql(
        f"COALESCE({current_record_ref}.raw_json, '{{}}'::jsonb)"
    )
    candidate_effective_raw_json = _build_job_raw_json_change_comparison_sql(
        effective_raw_json
    )
    conditions.append(
        f"{current_effective_raw_json} IS DISTINCT FROM "
        f"{candidate_effective_raw_json}"
    )
    reposted_at_sql = _build_linkedin_reposted_at_merge_sql(
        current_record_ref=current_record_ref,
        candidate_record_ref=candidate_record_ref,
    )
    conditions.append(
        f"{current_record_ref}.{JOBS_REPOSTED_AT_COLUMN_NAME} IS DISTINCT FROM "
        f"{reposted_at_sql}"
    )
    return "\n            OR ".join(conditions)


def _build_non_blank_text_merge_sql(
    *,
    current_value_ref: str,
    candidate_value_ref: str,
) -> str:
    return (
        f"COALESCE(NULLIF(BTRIM({candidate_value_ref}), ''), {current_value_ref})"
    )


def _build_linkedin_reposted_at_merge_sql(
    *,
    current_record_ref: str,
    candidate_record_ref: str,
) -> str:
    current_published_at_ref = f"{current_record_ref}.published_at"
    current_reposted_at_ref = f"{current_record_ref}.{JOBS_REPOSTED_AT_COLUMN_NAME}"
    candidate_published_at_ref = f"{candidate_record_ref}.published_at"
    candidate_source_ref = f"{candidate_record_ref}.source"
    latest_stored_linkedin_date = (
        "COALESCE("
        f"GREATEST({current_published_at_ref}, {current_reposted_at_ref}), "
        f"{current_published_at_ref}, "
        f"{current_reposted_at_ref}"
        ")"
    )
    return (
        "CASE\n"
        f"                WHEN {candidate_source_ref} = '{LINKEDIN_SOURCE}'\n"
        f"                 AND {candidate_published_at_ref} IS NOT NULL\n"
        f"                 AND {current_published_at_ref} IS NOT NULL\n"
        f"                 AND {candidate_published_at_ref} > {latest_stored_linkedin_date} THEN\n"
        f"                    {candidate_published_at_ref}\n"
        "                ELSE\n"
        f"                    {current_reposted_at_ref}\n"
        "            END"
    )


def _build_job_candidate_raw_json_sql(
    *,
    candidate_raw_json_ref: str,
) -> str:
    candidate_json = f"COALESCE({candidate_raw_json_ref}, '{{}}'::jsonb)"
    return (
        "CASE\n"
        f"                WHEN NULLIF(BTRIM(COALESCE({candidate_json}->>'description', '')), '') IS NULL THEN\n"
        f"                    {candidate_json} - 'description'\n"
        "                ELSE\n"
        f"                    {candidate_json}\n"
        "            END"
    )


def _build_job_raw_json_change_comparison_sql(raw_json_ref: str) -> str:
    comparison_sql = f"({raw_json_ref} - '{PROTECTED_RAW_JSON_DATE_POSTED_KEY}')"
    for field_name in sorted(JOB_UPSERT_IGNORED_CHANGE_FIELDS):
        comparison_sql = f"({comparison_sql} - '{field_name}')"
    return comparison_sql


def _build_job_raw_json_merge_sql(
    *,
    current_raw_json_ref: str,
    candidate_raw_json_ref: str,
) -> str:
    current_json = f"COALESCE({current_raw_json_ref}, '{{}}'::jsonb)"
    candidate_json = _build_job_candidate_raw_json_sql(
        candidate_raw_json_ref=candidate_raw_json_ref
    )
    return (
        "CASE\n"
        f"                WHEN {current_json} ? "
        f"'{PROTECTED_RAW_JSON_DATE_POSTED_KEY}' THEN\n"
        f"                    {current_json} || "
        f"({candidate_json} - '{PROTECTED_RAW_JSON_DATE_POSTED_KEY}')\n"
        "                ELSE\n"
        f"                    {current_json} || {candidate_json}\n"
        "            END"
    )


def _merge_non_blank_text_value(current_value: Any, candidate_value: Any) -> Any:
    if isinstance(candidate_value, str) and candidate_value.strip():
        return candidate_value
    return current_value


def _merge_job_candidate_raw_json_value(candidate_raw_json: Any) -> dict[str, Any]:
    candidate_json = _coerce_json_object(candidate_raw_json)
    if not _safe_str(candidate_json.get("description")):
        candidate_json = {
            key: value for key, value in candidate_json.items() if key != "description"
        }
    return candidate_json


def _merge_job_raw_json_value(
    current_raw_json: Any,
    candidate_raw_json: Any,
) -> dict[str, Any]:
    current_json = _coerce_json_object(current_raw_json)
    candidate_json = _merge_job_candidate_raw_json_value(candidate_raw_json)
    if PROTECTED_RAW_JSON_DATE_POSTED_KEY in current_json:
        candidate_json = {
            key: value
            for key, value in candidate_json.items()
            if key != PROTECTED_RAW_JSON_DATE_POSTED_KEY
        }
    return current_json | candidate_json


def _build_job_raw_json_effective_value(raw_json: Any) -> dict[str, Any]:
    effective_json = _coerce_json_object(raw_json)
    ignored_keys = {PROTECTED_RAW_JSON_DATE_POSTED_KEY, *JOB_UPSERT_IGNORED_CHANGE_FIELDS}
    return {
        key: value
        for key, value in effective_json.items()
        if key not in ignored_keys
    }


def _normalize_updated_change_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: value[key] for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_updated_change_value(item) for item in value]
    return value


def _build_updated_change_summary_query(*, include_duplicate_flag: bool = False) -> str:
    comparable_columns = _get_job_upsert_comparable_columns(
        include_duplicate_flag=include_duplicate_flag
    )

    selected_columns = [
        "s.job_url",
        "COALESCE(NULLIF(BTRIM(s.external_id), ''), NULLIF(BTRIM(j.external_id), ''), s.job_url) AS job_id",
    ]
    for column in comparable_columns:
        selected_columns.append(f"j.{column} AS current_{column}")
        selected_columns.append(f"s.{column} AS candidate_{column}")
    selected_columns.extend(
        [
            "j.raw_json AS current_raw_json",
            "s.raw_json AS candidate_raw_json",
            f"j.{JOBS_REPOSTED_AT_COLUMN_NAME} AS current_{JOBS_REPOSTED_AT_COLUMN_NAME}",
            "j.published_at AS current_published_at",
            "s.published_at AS candidate_published_at",
        ]
    )

    staging_change_predicate = _build_job_upsert_change_predicate(
        current_record_ref="j",
        candidate_record_ref="s",
        include_duplicate_flag=include_duplicate_flag,
    )
    return f"""
        SELECT
            {", ".join(selected_columns)}
        FROM tmp_jobs_import s
        JOIN {JOBS_TABLE_NAME} j
          ON j.job_url = s.job_url
        WHERE {staging_change_predicate}
        ORDER BY s.job_url
    """


def _summarize_updated_change_rows(
    rows: list[tuple[Any, ...]],
    *,
    include_duplicate_flag: bool = False,
) -> list[dict[str, Any]]:
    comparable_columns = _get_job_upsert_comparable_columns(
        include_duplicate_flag=include_duplicate_flag
    )

    summaries: list[dict[str, Any]] = []
    for row in rows:
        position = 0
        job_url = _safe_str(row[position])
        position += 1
        job_id = _safe_str(row[position]) or job_url
        position += 1

        current_values: dict[str, Any] = {}
        candidate_values: dict[str, Any] = {}
        for column in comparable_columns:
            current_values[column] = row[position]
            position += 1
            candidate_values[column] = row[position]
            position += 1

        current_raw_json = row[position]
        position += 1
        candidate_raw_json = row[position]
        position += 1
        current_reposted_at = row[position]
        position += 1
        current_published_at = row[position]
        position += 1
        candidate_published_at = row[position]

        for column in comparable_columns:
            current_value = current_values[column]
            candidate_value = candidate_values[column]
            if column == "description":
                candidate_value = _merge_non_blank_text_value(
                    current_value,
                    candidate_value,
                )
            if _normalize_updated_change_value(current_value) == _normalize_updated_change_value(
                candidate_value
            ):
                continue
            summaries.append(
                {
                    "job_id": job_id,
                    "job_url": job_url,
                    "field": column,
                    "before": _normalize_updated_change_value(current_value),
                    "after": _normalize_updated_change_value(candidate_value),
                }
            )

        current_effective_raw_json = _build_job_raw_json_effective_value(current_raw_json)
        merged_effective_raw_json = _build_job_raw_json_effective_value(
            _merge_job_raw_json_value(
                current_raw_json,
                candidate_raw_json,
            )
        )
        if _normalize_updated_change_value(current_effective_raw_json) != _normalize_updated_change_value(
            merged_effective_raw_json
        ):
            summaries.append(
                {
                    "job_id": job_id,
                    "job_url": job_url,
                    "field": "raw_json",
                    "before": _normalize_updated_change_value(current_effective_raw_json),
                    "after": _normalize_updated_change_value(merged_effective_raw_json),
                }
            )

        if (
            _safe_str(candidate_values.get("source")) == LINKEDIN_SOURCE
            and candidate_published_at is not None
            and current_published_at is not None
        ):
            latest_stored_linkedin_date = max(
                value
                for value in (current_published_at, current_reposted_at)
                if value is not None
            )
            merged_reposted_at = (
                candidate_published_at
                if candidate_published_at > latest_stored_linkedin_date
                else current_reposted_at
            )
        else:
            merged_reposted_at = current_reposted_at
        if current_reposted_at != merged_reposted_at:
            summaries.append(
                {
                    "job_id": job_id,
                    "job_url": job_url,
                    "field": JOBS_REPOSTED_AT_COLUMN_NAME,
                    "before": current_reposted_at,
                    "after": merged_reposted_at,
                }
            )

    return summaries


def _prepare_job_records(
    rows: list[dict[str, Any]],
    *,
    record_builder,
) -> tuple[list[dict[str, Any]], int, int]:
    staged_records_by_job_url: dict[str, dict[str, Any]] = {}
    skipped_invalid = 0
    skipped_duplicate_input = 0

    for row in rows:
        job_record = record_builder(row)
        if not job_record:
            skipped_invalid += 1
            continue

        job_url = job_record["job_url"]
        existing_record = staged_records_by_job_url.get(job_url)
        if existing_record:
            skipped_duplicate_input += 1
            staged_records_by_job_url[job_url] = _merge_job_records(
                existing_record,
                job_record,
            )
            continue

        staged_records_by_job_url[job_url] = job_record

    return (
        list(staged_records_by_job_url.values()),
        skipped_invalid,
        skipped_duplicate_input,
    )


def _is_direct_company_career_page_record(record: dict[str, Any]) -> bool:
    raw_json = _coerce_json_object(record.get("raw_json"))
    return any(
        _safe_str(raw_json.get(key))
        for key in DIRECT_COMPANY_CAREER_PAGE_MARKER_KEYS
    )


def _apply_configured_company_duplicate_flags(
    job_records: list[dict[str, Any]],
    configured_company_match_keys: set[str],
) -> int:
    marked_duplicates = 0
    for record in job_records:
        record["is_duplicate"] = False
        if _is_direct_company_career_page_record(record):
            continue
        if _safe_str(record.get("source")) not in JOB_BOARD_DUPLICATE_SOURCES:
            continue

        company_match_key = _normalize_company_match_key(record.get("company_name"))
        if company_match_key and company_match_key in configured_company_match_keys:
            record["is_duplicate"] = True
            marked_duplicates += 1
    return marked_duplicates


def _job_record_to_staging_value(
    record: dict[str, Any],
    json_adapter,
    *,
    include_duplicate_flag: bool = False,
) -> tuple[Any, ...]:
    duplicate_values: tuple[Any, ...] = ()
    if include_duplicate_flag:
        duplicate_values = (bool(record.get("is_duplicate", False)),)

    return (
        record["title"],
        record["location"],
        record["posted_time"],
        record["published_at"],
        record["job_url"],
        record["company_name"],
        record["company_url"],
        record["company_id"],
        record["description"],
        record["applications_count"],
        record["contract_type"],
        record["experience_level"],
        record["work_type"],
        record["sector"],
        record["salary"],
        record["poster_full_name"],
        record["poster_profile_url"],
        record["apply_url"],
        record["apply_type"],
        record["benefits"],
        record["source"],
        record["external_id"],
        *duplicate_values,
        json_adapter(record["raw_json"]),
    )


def _jobs_job_url_unique_index_exists(cursor) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND tablename = %s
          AND indexname = %s
        LIMIT 1
        """,
        (JOBS_TABLE_NAME, JOBS_JOB_URL_UNIQUE_INDEX_NAME),
    )
    return cursor.fetchone() is not None


def _get_current_schema_table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        """,
        (table_name,),
    )
    return {str(row[0]) for row in cursor.fetchall()}


def _ensure_jobs_reposted_at_column(cursor) -> None:
    cursor.execute(
        f"""
        ALTER TABLE {JOBS_TABLE_NAME}
        ADD COLUMN IF NOT EXISTS {JOBS_REPOSTED_AT_COLUMN_NAME} DATE
        """
    )


def _bulk_activate_reposted_linkedin_jobs_parsed(
    cursor,
    staging_table: str,
) -> int:
    jobs_parsed_columns = _get_current_schema_table_columns(
        cursor,
        JOBS_PARSED_TABLE_NAME,
    )
    required_columns = {
        JOBS_PARSED_RAW_JOB_ID_COLUMN_NAME,
        JOBS_PARSED_STATUS_COLUMN_NAME,
    }
    if not required_columns.issubset(jobs_parsed_columns):
        return 0

    cursor.execute(
        f"""
        WITH reposted_linkedin_jobs AS (
            SELECT DISTINCT j.id
            FROM {JOBS_TABLE_NAME} j
            JOIN {staging_table} s
              ON s.job_url = j.job_url
            WHERE s.source = %s
              AND j.{JOBS_REPOSTED_AT_COLUMN_NAME} IS NOT NULL
        )
        UPDATE {JOBS_PARSED_TABLE_NAME} AS jp
        SET {JOBS_PARSED_STATUS_COLUMN_NAME} = %s
        FROM reposted_linkedin_jobs rlj
        WHERE jp.{JOBS_PARSED_RAW_JOB_ID_COLUMN_NAME} = rlj.id
          AND jp.{JOBS_PARSED_STATUS_COLUMN_NAME} IS DISTINCT FROM %s
        RETURNING 1
        """,
        (
            LINKEDIN_SOURCE,
            JOBS_PARSED_ACTIVE_STATUS_VALUE,
            JOBS_PARSED_ACTIVE_STATUS_VALUE,
        ),
    )
    return len(cursor.fetchall())


def _reset_jobs_dedup_mapping_table(cursor) -> None:
    cursor.execute(f"DROP TABLE IF EXISTS {JOBS_DEDUP_MAPPING_TABLE_NAME}")
    cursor.execute(
        f"""
        CREATE TEMP TABLE {JOBS_DEDUP_MAPPING_TABLE_NAME} (
            loser_id BIGINT PRIMARY KEY,
            winner_id BIGINT NOT NULL,
            job_url TEXT NOT NULL
        ) ON COMMIT DROP
        """
    )


def _count_jobs_dedup_mapping_rows(cursor) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {JOBS_DEDUP_MAPPING_TABLE_NAME}")
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _create_jobs_dedup_mapping_table(cursor) -> int:
    _reset_jobs_dedup_mapping_table(cursor)
    cursor.execute(
        f"""
        INSERT INTO {JOBS_DEDUP_MAPPING_TABLE_NAME} (loser_id, winner_id, job_url)
        WITH duplicate_job_urls AS (
            SELECT job_url
            FROM {JOBS_TABLE_NAME}
            WHERE job_url IS NOT NULL
            GROUP BY job_url
            HAVING COUNT(*) > 1
        ),
        job_reference_counts AS (
            SELECT
                j.id,
                j.job_url,
                j.updated_at,
                j.fetched_at,
                EXISTS (
                    SELECT 1
                    FROM user_job_kanban_cards k
                    WHERE k.job_id = j.id
                ) AS has_kanban_refs,
                (
                    COALESCE(
                        (SELECT COUNT(*) FROM user_job_kanban_cards k WHERE k.job_id = j.id),
                        0
                    ) +
                    COALESCE(
                        (SELECT COUNT(*) FROM user_job_first_match f WHERE f.job_id = j.id),
                        0
                    ) +
                    COALESCE(
                        (SELECT COUNT(*) FROM job_match_email_deliveries e WHERE e.job_id = j.id),
                        0
                    )
                ) AS total_ref_count
            FROM {JOBS_TABLE_NAME} j
            WHERE j.job_url IN (SELECT job_url FROM duplicate_job_urls)
        ),
        ranked_jobs AS (
            SELECT
                id,
                job_url,
                FIRST_VALUE(id) OVER (
                    PARTITION BY job_url
                    ORDER BY
                        has_kanban_refs DESC,
                        total_ref_count DESC,
                        updated_at DESC NULLS LAST,
                        fetched_at DESC NULLS LAST,
                        id DESC
                ) AS winner_id,
                ROW_NUMBER() OVER (
                    PARTITION BY job_url
                    ORDER BY
                        has_kanban_refs DESC,
                        total_ref_count DESC,
                        updated_at DESC NULLS LAST,
                        fetched_at DESC NULLS LAST,
                        id DESC
                ) AS row_num
            FROM job_reference_counts
        )
        SELECT
            id AS loser_id,
            winner_id,
            job_url
        FROM ranked_jobs
        WHERE row_num > 1
        """
    )
    return _count_jobs_dedup_mapping_rows(cursor)


def _merge_duplicate_job_rows(cursor) -> None:
    cursor.execute(
        f"""
        UPDATE {JOBS_TABLE_NAME} AS winner
        SET
            title = COALESCE(NULLIF(BTRIM(loser.title), ''), winner.title),
            location = COALESCE(NULLIF(BTRIM(loser.location), ''), winner.location),
            posted_time = COALESCE(NULLIF(BTRIM(loser.posted_time), ''), winner.posted_time),
            published_at = COALESCE(loser.published_at, winner.published_at),
            {JOBS_REPOSTED_AT_COLUMN_NAME} = COALESCE(
                GREATEST(winner.{JOBS_REPOSTED_AT_COLUMN_NAME}, loser.{JOBS_REPOSTED_AT_COLUMN_NAME}),
                winner.{JOBS_REPOSTED_AT_COLUMN_NAME},
                loser.{JOBS_REPOSTED_AT_COLUMN_NAME}
            ),
            company_name = COALESCE(NULLIF(BTRIM(loser.company_name), ''), winner.company_name),
            company_url = COALESCE(NULLIF(BTRIM(loser.company_url), ''), winner.company_url),
            company_id = COALESCE(NULLIF(BTRIM(loser.company_id), ''), winner.company_id),
            description = COALESCE(NULLIF(BTRIM(loser.description), ''), winner.description),
            applications_count = COALESCE(NULLIF(BTRIM(loser.applications_count), ''), winner.applications_count),
            contract_type = COALESCE(NULLIF(BTRIM(loser.contract_type), ''), winner.contract_type),
            experience_level = COALESCE(NULLIF(BTRIM(loser.experience_level), ''), winner.experience_level),
            work_type = COALESCE(NULLIF(BTRIM(loser.work_type), ''), winner.work_type),
            sector = COALESCE(NULLIF(BTRIM(loser.sector), ''), winner.sector),
            salary = COALESCE(NULLIF(BTRIM(loser.salary), ''), winner.salary),
            poster_full_name = COALESCE(NULLIF(BTRIM(loser.poster_full_name), ''), winner.poster_full_name),
            poster_profile_url = COALESCE(NULLIF(BTRIM(loser.poster_profile_url), ''), winner.poster_profile_url),
            apply_url = COALESCE(NULLIF(BTRIM(loser.apply_url), ''), winner.apply_url),
            apply_type = COALESCE(NULLIF(BTRIM(loser.apply_type), ''), winner.apply_type),
            benefits = COALESCE(NULLIF(BTRIM(loser.benefits), ''), winner.benefits),
            source = COALESCE(NULLIF(BTRIM(winner.source), ''), loser.source),
            external_id = COALESCE(NULLIF(BTRIM(winner.external_id), ''), loser.external_id),
            raw_json = COALESCE(winner.raw_json, '{{}}'::jsonb) || COALESCE(loser.raw_json, '{{}}'::jsonb),
            fetched_at = COALESCE(
                GREATEST(winner.fetched_at, loser.fetched_at),
                winner.fetched_at,
                loser.fetched_at
            ),
            updated_at = COALESCE(
                GREATEST(winner.updated_at, loser.updated_at),
                winner.updated_at,
                loser.updated_at
            )
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        JOIN {JOBS_TABLE_NAME} AS loser
          ON loser.id = mapping.loser_id
        WHERE winner.id = mapping.winner_id
        """
    )


def _merge_user_job_first_match_duplicates(cursor) -> None:
    cursor.execute(
        f"""
        UPDATE user_job_first_match AS winner
        SET
            fit_first_analysis = COALESCE(winner.fit_first_analysis, FALSE)
                OR COALESCE(loser.fit_first_analysis, FALSE),
            created_at = COALESCE(
                LEAST(winner.created_at, loser.created_at),
                winner.created_at,
                loser.created_at
            ),
            fit_score = CASE
                WHEN winner.fit_score IS NULL THEN loser.fit_score
                WHEN loser.fit_score IS NULL THEN winner.fit_score
                ELSE GREATEST(winner.fit_score, loser.fit_score)
            END,
            job_fit_output = CASE
                WHEN winner.job_fit_output IS NULL OR winner.job_fit_output = '{{}}'::jsonb
                    THEN loser.job_fit_output
                ELSE winner.job_fit_output
            END,
            star = COALESCE(winner.star, FALSE) OR COALESCE(loser.star, FALSE),
            hide = COALESCE(winner.hide, FALSE) OR COALESCE(loser.hide, FALSE),
            seen = COALESCE(winner.seen, FALSE) OR COALESCE(loser.seen, FALSE),
            seen_at = COALESCE(
                GREATEST(winner.seen_at, loser.seen_at),
                winner.seen_at,
                loser.seen_at
            ),
            last_view_at = COALESCE(
                GREATEST(winner.last_view_at, loser.last_view_at),
                winner.last_view_at,
                loser.last_view_at
            ),
            link_clicked_at = COALESCE(
                GREATEST(winner.link_clicked_at, loser.link_clicked_at),
                winner.link_clicked_at,
                loser.link_clicked_at
            ),
            attached_resume_normalized = COALESCE(
                winner.attached_resume_normalized,
                loser.attached_resume_normalized
            ),
            attached_resume_template_name = COALESCE(
                NULLIF(BTRIM(winner.attached_resume_template_name), ''),
                loser.attached_resume_template_name
            ),
            attached_resume_updated_at = COALESCE(
                GREATEST(
                    winner.attached_resume_updated_at,
                    loser.attached_resume_updated_at
                ),
                winner.attached_resume_updated_at,
                loser.attached_resume_updated_at
            ),
            added_by_user = COALESCE(winner.added_by_user, FALSE)
                OR COALESCE(loser.added_by_user, FALSE),
            distance_km = CASE
                WHEN winner.distance_km IS NULL THEN loser.distance_km
                WHEN loser.distance_km IS NULL THEN winner.distance_km
                ELSE LEAST(winner.distance_km, loser.distance_km)
            END,
            applied = COALESCE(winner.applied, FALSE) OR COALESCE(loser.applied, FALSE)
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        JOIN user_job_first_match AS loser
          ON loser.job_id = mapping.loser_id
        WHERE winner.job_id = mapping.winner_id
          AND loser.user_id = winner.user_id
        """
    )
    cursor.execute(
        f"""
        DELETE FROM user_job_first_match AS loser
        USING {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping, user_job_first_match AS winner
        WHERE loser.job_id = mapping.loser_id
          AND winner.job_id = mapping.winner_id
          AND winner.user_id = loser.user_id
        """
    )
    cursor.execute(
        f"""
        UPDATE user_job_first_match AS row_to_move
        SET job_id = mapping.winner_id
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        WHERE row_to_move.job_id = mapping.loser_id
        """
    )


def _merge_user_job_kanban_card_duplicates(cursor) -> None:
    cursor.execute(
        f"""
        UPDATE user_job_kanban_cards AS winner
        SET
            stage = COALESCE(NULLIF(BTRIM(winner.stage), ''), loser.stage),
            common_data = COALESCE(winner.common_data, '{{}}'::jsonb)
                || COALESCE(loser.common_data, '{{}}'::jsonb),
            stage_data = COALESCE(winner.stage_data, '{{}}'::jsonb)
                || COALESCE(loser.stage_data, '{{}}'::jsonb),
            metadata = COALESCE(winner.metadata, '{{}}'::jsonb)
                || COALESCE(loser.metadata, '{{}}'::jsonb),
            source = COALESCE(NULLIF(BTRIM(winner.source), ''), loser.source),
            last_event = COALESCE(NULLIF(BTRIM(loser.last_event), ''), winner.last_event),
            moved_at = COALESCE(
                GREATEST(winner.moved_at, loser.moved_at),
                winner.moved_at,
                loser.moved_at
            ),
            created_at = COALESCE(
                LEAST(winner.created_at, loser.created_at),
                winner.created_at,
                loser.created_at
            ),
            updated_at = COALESCE(
                GREATEST(winner.updated_at, loser.updated_at),
                winner.updated_at,
                loser.updated_at
            ),
            deleted_at = CASE
                WHEN winner.deleted_at IS NULL OR loser.deleted_at IS NULL THEN NULL
                ELSE GREATEST(winner.deleted_at, loser.deleted_at)
            END
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        JOIN user_job_kanban_cards AS loser
          ON loser.job_id = mapping.loser_id
        WHERE winner.job_id = mapping.winner_id
          AND loser.user_id = winner.user_id
        """
    )
    cursor.execute(
        f"""
        DELETE FROM user_job_kanban_cards AS loser
        USING {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping, user_job_kanban_cards AS winner
        WHERE loser.job_id = mapping.loser_id
          AND winner.job_id = mapping.winner_id
          AND winner.user_id = loser.user_id
        """
    )
    cursor.execute(
        f"""
        UPDATE user_job_kanban_cards AS row_to_move
        SET job_id = mapping.winner_id
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        WHERE row_to_move.job_id = mapping.loser_id
        """
    )


def _merge_job_match_email_delivery_duplicates(cursor) -> None:
    cursor.execute(
        f"""
        UPDATE job_match_email_deliveries AS winner
        SET
            delivery_status = COALESCE(
                NULLIF(BTRIM(loser.delivery_status), ''),
                winner.delivery_status
            ),
            email = COALESCE(NULLIF(BTRIM(winner.email), ''), loser.email),
            run_started_at = COALESCE(
                GREATEST(winner.run_started_at, loser.run_started_at),
                winner.run_started_at,
                loser.run_started_at
            ),
            delivered_at = COALESCE(
                GREATEST(winner.delivered_at, loser.delivered_at),
                winner.delivered_at,
                loser.delivered_at
            )
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        JOIN job_match_email_deliveries AS loser
          ON loser.job_id = mapping.loser_id
        WHERE winner.job_id = mapping.winner_id
          AND loser.user_id = winner.user_id
          AND loser.service_name = winner.service_name
        """
    )
    cursor.execute(
        f"""
        DELETE FROM job_match_email_deliveries AS loser
        USING {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping, job_match_email_deliveries AS winner
        WHERE loser.job_id = mapping.loser_id
          AND winner.job_id = mapping.winner_id
          AND winner.user_id = loser.user_id
          AND winner.service_name = loser.service_name
        """
    )
    cursor.execute(
        f"""
        UPDATE job_match_email_deliveries AS row_to_move
        SET job_id = mapping.winner_id
        FROM {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
        WHERE row_to_move.job_id = mapping.loser_id
        """
    )


def _delete_jobs_in_dedup_mapping(cursor) -> int:
    _merge_duplicate_job_rows(cursor)
    _merge_user_job_first_match_duplicates(cursor)
    _merge_user_job_kanban_card_duplicates(cursor)
    _merge_job_match_email_delivery_duplicates(cursor)
    cursor.execute(
        f"""
        WITH deleted_rows AS (
            DELETE FROM {JOBS_TABLE_NAME} AS duplicate_jobs
            USING {JOBS_DEDUP_MAPPING_TABLE_NAME} mapping
            WHERE duplicate_jobs.id = mapping.loser_id
            RETURNING duplicate_jobs.id
        )
        SELECT COUNT(*)
        FROM deleted_rows
        """
    )
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _delete_duplicate_job_url_rows(cursor) -> int:
    duplicate_row_count = _create_jobs_dedup_mapping_table(cursor)
    if duplicate_row_count == 0:
        return 0

    return _delete_jobs_in_dedup_mapping(cursor)


def _merge_source_external_job_url_collisions(cursor, staging_table: str) -> int:
    _reset_jobs_dedup_mapping_table(cursor)
    cursor.execute(
        f"""
        INSERT INTO {JOBS_DEDUP_MAPPING_TABLE_NAME} (loser_id, winner_id, job_url)
        SELECT DISTINCT
            source_external_job.id AS loser_id,
            job_url_job.id AS winner_id,
            job_url_job.job_url
        FROM {staging_table} AS staged_job
        JOIN {JOBS_TABLE_NAME} AS source_external_job
          ON source_external_job.source = staged_job.source
         AND source_external_job.external_id = staged_job.external_id
        JOIN {JOBS_TABLE_NAME} AS job_url_job
          ON job_url_job.job_url = staged_job.job_url
        WHERE staged_job.external_id IS NOT NULL
          AND BTRIM(staged_job.external_id) <> ''
          AND source_external_job.id <> job_url_job.id
        """
    )
    collision_row_count = _count_jobs_dedup_mapping_rows(cursor)
    if collision_row_count == 0:
        return 0

    return _delete_jobs_in_dedup_mapping(cursor)


def _ensure_jobs_job_url_uniqueness(cursor) -> int:
    if _jobs_job_url_unique_index_exists(cursor):
        return 0

    deleted_duplicate_rows = _delete_duplicate_job_url_rows(cursor)
    cursor.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {JOBS_JOB_URL_UNIQUE_INDEX_NAME}
        ON {JOBS_TABLE_NAME} (job_url)
        """
    )
    return deleted_duplicate_rows


def _realign_existing_job_urls_by_source_external_id(cursor, staging_table: str) -> None:
    cursor.execute(
        f"""
        UPDATE {JOBS_TABLE_NAME} AS existing_job
        SET
            job_url = staged_job.job_url
        FROM {staging_table} AS staged_job
        WHERE existing_job.source = staged_job.source
          AND existing_job.external_id = staged_job.external_id
          AND existing_job.job_url IS DISTINCT FROM staged_job.job_url
          AND NOT EXISTS (
              SELECT 1
              FROM {JOBS_TABLE_NAME} AS conflicting_job_url
              WHERE conflicting_job_url.job_url = staged_job.job_url
                AND conflicting_job_url.id <> existing_job.id
          )
        """
    )


def _bulk_upsert_jobs(
    job_records: list[dict[str, Any]],
    *,
    include_duplicate_flag: bool = False,
) -> dict[str, Any]:
    from psycopg2.extras import Json, execute_values

    if not job_records:
        return {
            "inserted": 0,
            "inserted_job_urls": [],
            "updated": 0,
            "updated_job_urls": [],
            "updated_external_ids": [],
            "updated_changes": [],
            "updated_fields": [],
            "parsed_jobs_activated": 0,
            "deleted_duplicate_rows": 0,
            "failed": 0,
        }

    staging_table = "tmp_jobs_import"
    meaningful_change_predicate = _build_job_upsert_change_predicate(
        current_record_ref=JOBS_TABLE_NAME,
        candidate_record_ref="EXCLUDED",
        include_duplicate_flag=include_duplicate_flag,
    )
    staging_change_predicate = _build_job_upsert_change_predicate(
        current_record_ref="j",
        candidate_record_ref="s",
        include_duplicate_flag=include_duplicate_flag,
    )
    raw_json_merge_sql = _build_job_raw_json_merge_sql(
        current_raw_json_ref=f"{JOBS_TABLE_NAME}.raw_json",
        candidate_raw_json_ref="EXCLUDED.raw_json",
    )
    reposted_at_merge_sql = _build_linkedin_reposted_at_merge_sql(
        current_record_ref=JOBS_TABLE_NAME,
        candidate_record_ref="EXCLUDED",
    )
    staging_duplicate_column_sql = (
        f",\n            {JOBS_IS_DUPLICATE_COLUMN_NAME} BOOLEAN"
        if include_duplicate_flag
        else ""
    )
    staging_duplicate_insert_column_sql = (
        f", {JOBS_IS_DUPLICATE_COLUMN_NAME}" if include_duplicate_flag else ""
    )
    staging_duplicate_select_column_sql = (
        f", s.{JOBS_IS_DUPLICATE_COLUMN_NAME}" if include_duplicate_flag else ""
    )
    jobs_duplicate_insert_column_sql = (
        f",\n            {JOBS_IS_DUPLICATE_COLUMN_NAME}"
        if include_duplicate_flag
        else ""
    )
    jobs_duplicate_update_sql = (
        f",\n            {JOBS_IS_DUPLICATE_COLUMN_NAME} = "
        f"EXCLUDED.{JOBS_IS_DUPLICATE_COLUMN_NAME}"
        if include_duplicate_flag
        else ""
    )
    create_staging_sql = f"""
        CREATE TEMP TABLE {staging_table} (
            title TEXT,
            location TEXT,
            posted_time TEXT,
            published_at DATE,
            job_url TEXT,
            company_name TEXT,
            company_url TEXT,
            company_id TEXT,
            description TEXT,
            applications_count TEXT,
            contract_type TEXT,
            experience_level TEXT,
            work_type TEXT,
            sector TEXT,
            salary TEXT,
            poster_full_name TEXT,
            poster_profile_url TEXT,
            apply_url TEXT,
            apply_type TEXT,
            benefits TEXT,
            source TEXT,
            external_id TEXT,
            {staging_duplicate_column_sql.lstrip(',').strip() + ',' if include_duplicate_flag else ''}
            raw_json JSONB
        ) ON COMMIT DROP
    """
    insert_staging_sql = f"""
        INSERT INTO {staging_table} (
            title, location, posted_time, published_at, job_url,
            company_name, company_url, company_id,
            description, applications_count, contract_type,
            experience_level, work_type, sector, salary,
            poster_full_name, poster_profile_url,
            apply_url, apply_type, benefits,
            source, external_id{staging_duplicate_insert_column_sql}, raw_json
        )
        VALUES %s
    """
    normalize_staging_dates_sql = f"""
        UPDATE {staging_table}
        SET
            posted_time = COALESCE(NULLIF(BTRIM(posted_time), ''), NOW()::text),
            published_at = COALESCE(published_at, NOW()::date)
    """
    select_existing_sql = f"""
        SELECT DISTINCT s.job_url, s.external_id
        FROM {staging_table} s
        JOIN {JOBS_TABLE_NAME} j
          ON j.job_url = s.job_url
    """
    select_changed_existing_sql = f"""
        SELECT DISTINCT s.job_url, s.external_id
        FROM {staging_table} s
        JOIN {JOBS_TABLE_NAME} j
          ON j.job_url = s.job_url
        WHERE {staging_change_predicate}
    """
    upsert_sql = f"""
        INSERT INTO {JOBS_TABLE_NAME} (
            title, location, posted_time, published_at, job_url,
            company_name, company_url, company_id,
            description, applications_count, contract_type,
            experience_level, work_type, sector, salary,
            poster_full_name, poster_profile_url,
            apply_url, apply_type, benefits,
            source, external_id{jobs_duplicate_insert_column_sql}, raw_json, fetched_at
        )
        SELECT
            s.title, s.location, s.posted_time, s.published_at, s.job_url,
            s.company_name, s.company_url, s.company_id,
            s.description, s.applications_count, s.contract_type,
            s.experience_level, s.work_type, s.sector, s.salary,
            s.poster_full_name, s.poster_profile_url,
            s.apply_url, s.apply_type, s.benefits,
            s.source, s.external_id{staging_duplicate_select_column_sql}, s.raw_json, NOW()
        FROM {staging_table} s
        ON CONFLICT (job_url) DO UPDATE
        SET
            title = EXCLUDED.title,
            location = EXCLUDED.location,
            posted_time = COALESCE({JOBS_TABLE_NAME}.posted_time, EXCLUDED.posted_time),
            published_at = COALESCE({JOBS_TABLE_NAME}.published_at, EXCLUDED.published_at),
            {JOBS_REPOSTED_AT_COLUMN_NAME} = {reposted_at_merge_sql},
            company_name = EXCLUDED.company_name,
            company_url = EXCLUDED.company_url,
            company_id = EXCLUDED.company_id,
            description = { _build_non_blank_text_merge_sql(
                current_value_ref=f"{JOBS_TABLE_NAME}.description",
                candidate_value_ref="EXCLUDED.description",
            ) },
            applications_count = EXCLUDED.applications_count,
            contract_type = EXCLUDED.contract_type,
            experience_level = EXCLUDED.experience_level,
            work_type = EXCLUDED.work_type,
            sector = EXCLUDED.sector,
            salary = EXCLUDED.salary,
            poster_full_name = EXCLUDED.poster_full_name,
            poster_profile_url = EXCLUDED.poster_profile_url,
            apply_url = EXCLUDED.apply_url,
            apply_type = EXCLUDED.apply_type,
            benefits = EXCLUDED.benefits,
            source = EXCLUDED.source,
            external_id = EXCLUDED.external_id,
            {jobs_duplicate_update_sql.lstrip(',').strip() + ',' if include_duplicate_flag else ''}
            raw_json = {raw_json_merge_sql},
            updated_at = NOW()
        WHERE {meaningful_change_predicate}
    """

    staging_values = [
        _job_record_to_staging_value(
            record,
            Json,
            include_duplicate_flag=include_duplicate_flag,
        )
        for record in job_records
    ]

    inserted = 0
    inserted_job_urls: list[str] = []
    updated_job_urls: list[str] = []
    updated_external_ids: list[str] = []
    updated_changes: list[dict[str, Any]] = []
    parsed_jobs_activated = 0
    deleted_duplicate_rows = 0
    failed = 0
    has_linkedin_records = any(
        _safe_str(record.get("source")) == LINKEDIN_SOURCE for record in job_records
    )

    conn = _get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                _ensure_jobs_reposted_at_column(cursor)
                deleted_duplicate_rows = _ensure_jobs_job_url_uniqueness(cursor)
                cursor.execute(create_staging_sql)
                execute_values(
                    cursor,
                    insert_staging_sql,
                    staging_values,
                    page_size=500,
                )
                cursor.execute(normalize_staging_dates_sql)
                _merge_source_external_job_url_collisions(cursor, staging_table)
                _realign_existing_job_urls_by_source_external_id(cursor, staging_table)
                cursor.execute(select_existing_sql)
                existing_rows = cursor.fetchall()
                existing_job_urls = {row[0] for row in existing_rows}
                cursor.execute(select_changed_existing_sql)
                changed_existing_rows = cursor.fetchall()
                updated_job_urls = [row[0] for row in changed_existing_rows]
                updated_external_ids = [row[1] for row in changed_existing_rows]
                if changed_existing_rows:
                    cursor.execute(
                        _build_updated_change_summary_query(
                            include_duplicate_flag=include_duplicate_flag
                        )
                    )
                    updated_changes = _summarize_updated_change_rows(
                        cursor.fetchall(),
                        include_duplicate_flag=include_duplicate_flag,
                    )
                cursor.execute(upsert_sql)
                inserted = len(job_records) - len(existing_rows)
                inserted_job_urls = [
                    record["job_url"]
                    for record in job_records
                    if record.get("job_url") not in existing_job_urls
                ]
                if has_linkedin_records:
                    parsed_jobs_activated = (
                        _bulk_activate_reposted_linkedin_jobs_parsed(
                            cursor,
                            staging_table,
                        )
                    )
    except Exception:
        failed = len(job_records)
        raise
    finally:
        conn.close()

    return {
        "inserted": inserted,
        "inserted_job_urls": inserted_job_urls,
        "updated": len(updated_job_urls),
        "updated_job_urls": updated_job_urls,
        "updated_external_ids": updated_external_ids,
        "updated_changes": updated_changes,
        "updated_fields": sorted(
            {
                _safe_str(change.get("field"))
                for change in updated_changes
                if isinstance(change, dict) and _safe_str(change.get("field"))
            }
        ),
        "parsed_jobs_activated": parsed_jobs_activated,
        "deleted_duplicate_rows": deleted_duplicate_rows,
        "failed": failed,
    }


def _coerce_jobs_to_rows(jobs: Any) -> list[dict[str, Any]]:
    if jobs is None:
        return []
    if isinstance(jobs, list):
        rows = jobs
    else:
        to_json = getattr(jobs, "to_json", None)
        if not callable(to_json):
            raise ValueError("Expected a dataframe-like object or a list of job rows")
        rows = json.loads(
            jobs.to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
            )
        )

    if not isinstance(rows, list):
        raise ValueError("Expected jobs to serialize into a JSON array")
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if len(dict_rows) != len(rows):
        raise ValueError("Expected every serialized job row to be a JSON object")
    return dict_rows


def _extract_comeet_company_fields(
    job_url: Any,
) -> tuple[str | None, str | None, str | None]:
    job_url_text = _safe_str(job_url)
    if not job_url_text or not job_url_text.startswith(COMEET_JOBS_URL_PREFIX):
        return None, None, None

    parsed = urlparse(job_url_text)
    if parsed.scheme != "https" or parsed.netloc != "www.comeet.com":
        return None, None, None

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 3 or path_parts[0] != "jobs":
        return None, None, None

    comeet_base_url = f"{parsed.scheme}://{parsed.netloc}/{'/'.join(path_parts[:3])}"
    return comeet_base_url, path_parts[1], path_parts[2]


def _extract_company_name(row: dict[str, Any]) -> str | None:
    company_name = _safe_str(row.get("company_name"))
    if company_name:
        return company_name

    raw_company = row.get("company")
    company = _coerce_json_object(raw_company)
    company_name = _safe_str(company.get("name"))
    if company_name:
        return company_name

    if not isinstance(raw_company, dict):
        company_name = _safe_str(raw_company)
        if company_name:
            return company_name

    cell_values = row.get(AIRTABLE_ROW_CELL_VALUES_KEY)
    if isinstance(cell_values, dict):
        return _safe_str(cell_values.get(COMEET_AIRTABLE_COMPANY_NAME_COLUMN_ID))

    return None


def _extract_comeet_source_job_url(row: dict[str, Any]) -> str | None:
    job_url = _safe_str(row.get("job_url"))
    if job_url:
        return job_url

    cell_values = row.get(AIRTABLE_ROW_CELL_VALUES_KEY)
    if not isinstance(cell_values, dict):
        return None

    return _safe_str(cell_values.get(COMEET_AIRTABLE_CAREER_LINK_COLUMN_ID))


def _pick_preferred_company_name(
    existing_name: str | None, candidate_name: str | None
) -> str | None:
    existing_name = _safe_str(existing_name)
    candidate_name = _safe_str(candidate_name)

    if not existing_name:
        return candidate_name
    if not candidate_name:
        return existing_name

    if len(candidate_name) > len(existing_name):
        return candidate_name
    return existing_name


def _build_comeet_company_url_record(row: dict[str, Any]) -> dict[str, Any] | None:
    source_job_url = _extract_comeet_source_job_url(row)
    comeet_base_url, comeet_company_slug, comeet_company_code = (
        _extract_comeet_company_fields(source_job_url)
    )
    if not comeet_base_url or not comeet_company_slug or not comeet_company_code:
        return None

    return {
        "comeet_base_url": comeet_base_url,
        "company_name": _extract_company_name(row),
        "comeet_company_slug": comeet_company_slug,
        "comeet_company_code": comeet_company_code,
        "source_job_url": source_job_url,
    }


def _merge_comeet_company_url_records(
    existing_record: dict[str, Any], candidate_record: dict[str, Any]
) -> dict[str, Any]:
    preferred_company_name = _pick_preferred_company_name(
        existing_record.get("company_name"),
        candidate_record.get("company_name"),
    )
    source_job_url = existing_record["source_job_url"]
    if preferred_company_name == candidate_record.get("company_name"):
        source_job_url = candidate_record["source_job_url"]

    return {
        **existing_record,
        "company_name": preferred_company_name,
        "source_job_url": source_job_url,
    }


class LinkedInJobsTableLookup:
    def __init__(self) -> None:
        self._conn = None
        self._cache: dict[str, dict[str, Any] | None] = {}

    def _ensure_connection(self):
        if self._conn is None or getattr(self._conn, "closed", 1):
            self._conn = _get_db_connection()
            self._conn.autocommit = True
        return self._conn

    def get_job_details(self, job_url: str) -> dict[str, Any] | None:
        canonical_job_url, _ = _validate_linkedin_job_url(job_url)
        if not canonical_job_url:
            return None

        if canonical_job_url in self._cache:
            return self._cache[canonical_job_url]

        query = """
            SELECT
                description,
                applications_count,
                contract_type,
                experience_level,
                sector,
                apply_url,
                raw_json
            FROM jobs
            WHERE source = %s
              AND job_url = %s
            ORDER BY updated_at DESC NULLS LAST, fetched_at DESC NULLS LAST, id DESC
            LIMIT 1
        """

        conn = self._ensure_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, (LINKEDIN_SOURCE, canonical_job_url))
            row = cursor.fetchone()

        if not row:
            self._cache[canonical_job_url] = None
            return None

        raw_json = _coerce_json_object(row[6])

        details = {
            "description": _safe_str(raw_json.get("description")) or _safe_str(row[0]),
            "applications_count": _safe_int(raw_json.get("applications_count"))
            if raw_json.get("applications_count") is not None
            else _safe_int(row[1]),
            "job_type": _parse_job_type_list(
                raw_json.get("job_type") or row[2]
            ),
            "job_level": _safe_str(raw_json.get("job_level")) or _safe_str(row[3]),
            "company_industry": _safe_str(raw_json.get("company_industry"))
            or _safe_str(row[4]),
            "apply_url": _safe_str(raw_json.get("apply_url")) or _safe_str(row[5]),
            "job_url_direct": _safe_str(raw_json.get("job_url_direct")),
            "job_function": _safe_str(raw_json.get("job_function")),
        }
        self._cache[canonical_job_url] = details
        return details

    def close(self) -> None:
        if self._conn is not None and not getattr(self._conn, "closed", 1):
            self._conn.close()
        self._conn = None


def populate_jobs_table_from_file(
    json_path: Path,
    *,
    mark_configured_company_job_board_duplicates: bool = False,
) -> dict[str, Any]:
    rows = _parse_json_file(json_path)

    prepared_records, skipped_invalid, skipped_duplicate_input = _prepare_job_records(
        rows,
        record_builder=_build_job_record,
    )
    marked_duplicate_jobs = 0
    if mark_configured_company_job_board_duplicates:
        marked_duplicate_jobs = _apply_configured_company_duplicate_flags(
            prepared_records,
            get_company_career_page_company_match_keys(),
        )

    if mark_configured_company_job_board_duplicates:
        upsert_summary = _bulk_upsert_jobs(
            prepared_records,
            include_duplicate_flag=True,
        )
    else:
        upsert_summary = _bulk_upsert_jobs(prepared_records)

    summary = {
        "rows_in_file": len(rows),
        "prepared_records": len(prepared_records),
        "inserted": upsert_summary["inserted"],
        "inserted_job_urls": upsert_summary.get("inserted_job_urls", []),
        "updated": upsert_summary["updated"],
        "updated_external_ids": upsert_summary["updated_external_ids"],
        "updated_job_urls": upsert_summary["updated_job_urls"],
        "updated_changes": upsert_summary.get("updated_changes", []),
        "updated_fields": upsert_summary.get("updated_fields", []),
        "parsed_jobs_activated": upsert_summary.get("parsed_jobs_activated", 0),
        "skipped_invalid": skipped_invalid,
        "skipped_duplicate_input": skipped_duplicate_input,
        "deleted_duplicate_rows": upsert_summary["deleted_duplicate_rows"],
        "failed": upsert_summary["failed"],
    }
    if mark_configured_company_job_board_duplicates:
        summary["marked_duplicate_jobs"] = marked_duplicate_jobs
    return summary


def populate_company_comeet_job_urls_from_file(json_path: Path) -> dict[str, Any]:
    rows = _parse_company_comeet_job_urls_file(json_path)
    print(f"Loaded {len(rows)} row(s) from {json_path}")
    print(
        "Connecting to PostgreSQL and populating "
        f"{COMPANY_COMEET_JOB_URLS_TABLE_NAME} table"
    )

    select_sql = f"""
        SELECT comeet_base_url
        FROM {COMPANY_COMEET_JOB_URLS_TABLE_NAME}
        WHERE comeet_base_url = %s
        LIMIT 1
    """
    insert_sql = f"""
        INSERT INTO {COMPANY_COMEET_JOB_URLS_TABLE_NAME} (
            comeet_base_url,
            company_name,
            comeet_company_slug,
            comeet_company_code,
            source_job_url,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
    """
    inserted = 0
    skipped_existing = 0
    skipped_invalid = 0
    skipped_duplicate_input = 0
    failed = 0
    matching_comeet_rows = 0
    deduped_records: dict[str, dict[str, Any]] = {}

    for row in rows:
        record = _build_comeet_company_url_record(row)
        if not record:
            skipped_invalid += 1
            continue

        matching_comeet_rows += 1
        existing_record = deduped_records.get(record["comeet_base_url"])
        if existing_record:
            skipped_duplicate_input += 1
            deduped_records[record["comeet_base_url"]] = (
                _merge_comeet_company_url_records(existing_record, record)
            )
            continue

        deduped_records[record["comeet_base_url"]] = record

    conn = _get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(CREATE_COMPANY_COMEET_JOB_URLS_TABLE_SQL)
            total = len(deduped_records)
            for index, record in enumerate(deduped_records.values(), start=1):
                if total and (index == 1 or index % 25 == 0 or index == total):
                    print(
                        f"DB progress {index}/{total} | "
                        f"inserted={inserted} existing={skipped_existing} "
                        f"invalid={skipped_invalid} dup_input={skipped_duplicate_input} failed={failed}"
                    )

                values = (
                    record["comeet_base_url"],
                    record["company_name"],
                    record["comeet_company_slug"],
                    record["comeet_company_code"],
                    record["source_job_url"],
                )

                try:
                    cursor.execute(select_sql, (record["comeet_base_url"],))
                    exists = cursor.fetchone() is not None

                    if exists:
                        skipped_existing += 1
                    else:
                        cursor.execute(insert_sql, values)
                        inserted += 1
                except Exception as exc:
                    failed += 1
                    print(
                        "DB row failed for "
                        f"{record['comeet_base_url']}: {exc}"
                    )

    finally:
        conn.close()

    summary = {
        "rows_in_file": len(rows),
        "matching_comeet_rows": matching_comeet_rows,
        "unique_base_urls": len(deduped_records),
        "inserted": inserted,
        "updated": 0,
        "updated_base_urls": [],
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
        "skipped_duplicate_input": skipped_duplicate_input,
        "failed": failed,
    }
    print(f"{COMPANY_COMEET_JOB_URLS_TABLE_NAME} population finished")
    print(_format_population_summary(summary))
    return summary


def get_company_comeet_job_url(
    comeet_base_url: str | None = None,
) -> dict[str, Any] | None:
    normalized_base_url = _safe_str(comeet_base_url)
    if normalized_base_url:
        query = f"""
            SELECT
                comeet_base_url,
                company_name,
                comeet_company_slug,
                comeet_company_code,
                source_job_url,
                created_at,
                updated_at
            FROM {COMPANY_COMEET_JOB_URLS_TABLE_NAME}
            WHERE comeet_base_url = %s
            LIMIT 1
        """
        params = (normalized_base_url,)
    else:
        query = f"""
            SELECT
                comeet_base_url,
                company_name,
                comeet_company_slug,
                comeet_company_code,
                source_job_url,
                created_at,
                updated_at
            FROM {COMPANY_COMEET_JOB_URLS_TABLE_NAME}
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, comeet_base_url
            LIMIT 1
        """
        params = ()

    conn = _get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return {
        "comeet_base_url": row[0],
        "company_name": row[1],
        "comeet_company_slug": row[2],
        "comeet_company_code": row[3],
        "source_job_url": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


def list_company_comeet_job_urls() -> list[dict[str, Any]]:
    query = f"""
        SELECT
            comeet_base_url,
            company_name,
            comeet_company_slug,
            comeet_company_code,
            source_job_url,
            created_at,
            updated_at
        FROM {COMPANY_COMEET_JOB_URLS_TABLE_NAME}
        ORDER BY company_name NULLS LAST, comeet_base_url
    """

    conn = _get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {
            "comeet_base_url": row[0],
            "company_name": row[1],
            "comeet_company_slug": row[2],
            "comeet_company_code": row[3],
            "source_job_url": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }
        for row in rows
    ]


def populate_comeet_jobs_table(jobs: Any) -> dict[str, Any]:
    rows = _coerce_jobs_to_rows(jobs)

    staging_records, skipped_invalid, skipped_duplicate_input = _prepare_job_records(
        rows,
        record_builder=_build_comeet_job_record,
    )

    if not staging_records:
        summary = {
            "rows_in_batch": len(rows),
            "prepared_records": 0,
            "inserted": 0,
            "updated": 0,
            "skipped_invalid": skipped_invalid,
            "skipped_duplicate_input": skipped_duplicate_input,
            "failed": 0,
        }
        return summary
    upsert_summary = _bulk_upsert_jobs(staging_records)

    summary = {
        "rows_in_batch": len(rows),
        "prepared_records": len(staging_records),
        "inserted": upsert_summary["inserted"],
        "updated": upsert_summary["updated"],
        "updated_external_ids_sample": upsert_summary["updated_external_ids"][:20],
        "updated_job_urls_sample": upsert_summary["updated_job_urls"][:20],
        "skipped_invalid": skipped_invalid,
        "skipped_duplicate_input": skipped_duplicate_input,
        "deleted_duplicate_rows": upsert_summary["deleted_duplicate_rows"],
        "failed": upsert_summary["failed"],
    }
    return summary
