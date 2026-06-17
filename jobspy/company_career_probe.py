from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from jobspy import scrape_jobs
from jobspy import jobs_table


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
GREENHOUSE_API_TEMPLATE = (
    "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
)
URL_KWARG_BY_SITE = {
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
GREENHOUSE_BOARD_TOKEN_PATTERNS = (
    re.compile(r"boards-api\.greenhouse\.io/v1/boards/(?P<token>[^/?#\"']+)/jobs", re.I),
    re.compile(r"job-boards\.greenhouse\.io/(?P<token>[^/?#\"']+)", re.I),
    re.compile(r"boards(?:\.eu)?\.greenhouse\.io/(?P<token>[^/?#\"']+)", re.I),
)


@dataclass(frozen=True)
class DetectedCareerPage:
    detected_platform: str
    scraper_site: str
    input_url: str
    resolved_fetch_url: str
    extra_params: dict[str, Any]
    confidence: str = "high"
    notes: tuple[str, ...] = ()


def probe_company_career_page(
    *,
    company_name: str,
    career_page_url: str,
    company_key: str | None = None,
    location: str | None = "Israel",
    country_indeed: str = "Israel",
    sample_size: int = 5,
    request_timeout: int = 60,
    user_agent: str | None = None,
) -> dict[str, Any]:
    company_name = _required_text(company_name, "company_name")
    career_page_url = _normalize_url(_required_text(career_page_url, "career_page_url"))
    company_key = _safe_text(company_key) or _slugify(company_name)
    errors: list[str] = []
    warnings: list[str] = []

    try:
        detected = detect_company_career_page(
            company_name=company_name,
            career_page_url=career_page_url,
            country_indeed=country_indeed,
            request_timeout=request_timeout,
            user_agent=user_agent,
        )
    except Exception as exc:
        row = _build_base_row(
            company_key=company_key,
            company_name=company_name,
            career_page_url=career_page_url,
            location=location,
            country_indeed=country_indeed,
            request_timeout=request_timeout,
            scraper_site="unknown",
            resolved_fetch_url=None,
            extra_params={},
        )
        return _json_safe(
            {
                "valid": False,
                "status": "failed",
                "company_key": company_key,
                "company_name": company_name,
                "input_url": career_page_url,
                "detected_platform": None,
                "scraper_site": None,
                "resolved_fetch_url": None,
                "row": row,
                "sample_jobs": [],
                "jobs_found": 0,
                "errors": [str(exc)],
                "warnings": warnings,
            }
        )

    row = _build_base_row(
        company_key=company_key,
        company_name=company_name,
        career_page_url=career_page_url,
        location=location,
        country_indeed=country_indeed,
        request_timeout=request_timeout,
        scraper_site=detected.scraper_site,
        resolved_fetch_url=detected.resolved_fetch_url,
        extra_params=detected.extra_params,
    )
    warnings.extend(detected.notes)
    validation = validate_company_career_page_row(
        row,
        sample_size=sample_size,
        user_agent=user_agent,
    )
    errors.extend(validation["errors"])
    warnings.extend(validation["warnings"])
    valid = not errors and validation["jobs_found"] > 0

    return _json_safe(
        {
            "valid": valid,
            "status": "valid" if valid else "failed",
            "company_key": company_key,
            "company_name": company_name,
            "input_url": career_page_url,
            "detected_platform": detected.detected_platform,
            "scraper_site": detected.scraper_site,
            "resolved_fetch_url": detected.resolved_fetch_url,
            "confidence": detected.confidence,
            "row": row,
            "sample_jobs": validation["sample_jobs"],
            "jobs_found": validation["jobs_found"],
            "normalized_records": validation["normalized_records"],
            "errors": errors,
            "warnings": warnings,
        }
    )


def detect_company_career_page(
    *,
    company_name: str,
    career_page_url: str,
    country_indeed: str = "Israel",
    request_timeout: int = 60,
    user_agent: str | None = None,
) -> DetectedCareerPage:
    career_page_url = _normalize_url(career_page_url)
    parsed = urlparse(career_page_url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if "myworkdayjobs.com" in host:
        return DetectedCareerPage(
            detected_platform="workday",
            scraper_site="workday",
            input_url=career_page_url,
            resolved_fetch_url=career_page_url,
            extra_params={},
        )
    if host == "www.comeet.com" and path.startswith("/jobs/"):
        return DetectedCareerPage(
            detected_platform="comeet",
            scraper_site="comeet",
            input_url=career_page_url,
            resolved_fetch_url=career_page_url,
            extra_params={},
        )
    if host == "jobs.lever.co" or "api.lever.co" in host:
        company_slug = _extract_lever_slug(career_page_url)
        if company_slug:
            return _build_lever_detection(
                company_name=company_name,
                input_url=career_page_url,
                company_slug=company_slug,
                country_indeed=country_indeed,
            )

    board_token = _extract_greenhouse_board_token(career_page_url)
    if board_token:
        return _build_greenhouse_public_detection(
            company_name=company_name,
            input_url=career_page_url,
            board_token=board_token,
            country_indeed=country_indeed,
        )

    session = _build_session(user_agent)
    page_text = _fetch_text(session, career_page_url, request_timeout)
    board_token = _find_greenhouse_board_token_in_page(
        session,
        career_page_url,
        page_text,
        request_timeout,
    )
    if board_token:
        return _build_greenhouse_public_detection(
            company_name=company_name,
            input_url=career_page_url,
            board_token=board_token,
            country_indeed=country_indeed,
            notes=("Detected Greenhouse public board from page assets.",),
        )

    lever_slug = _find_lever_slug_in_text(page_text)
    if lever_slug:
        return _build_lever_detection(
            company_name=company_name,
            input_url=career_page_url,
            company_slug=lever_slug,
            country_indeed=country_indeed,
            notes=("Detected Lever postings from page HTML.",),
        )

    payload = _try_fetch_json(session, career_page_url, request_timeout)
    if payload is not None:
        config = _infer_json_feed_config(payload, company_name, career_page_url, country_indeed)
        if config:
            return DetectedCareerPage(
                detected_platform="json_feed",
                scraper_site="json_feed",
                input_url=career_page_url,
                resolved_fetch_url=career_page_url,
                extra_params={"json_feed_config": config},
                confidence="medium",
                notes=("Inferred a generic JSON feed mapping from response fields.",),
            )

    raise ValueError(
        "Could not detect a supported career-page platform. Supported detection "
        "currently covers public Greenhouse boards, Lever, Workday, Comeet, "
        "and generic JSON feeds with recognizable job fields."
    )


def validate_company_career_page_row(
    company_record: dict[str, Any],
    *,
    sample_size: int = 5,
    user_agent: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    kwargs = build_scrape_kwargs(company_record, sample_size=sample_size)
    if user_agent:
        kwargs["user_agent"] = user_agent

    try:
        jobs = scrape_jobs(**kwargs)
    except Exception as exc:
        return {
            "sample_jobs": [],
            "jobs_found": 0,
            "normalized_records": [],
            "errors": [f"Scrape failed: {exc}"],
            "warnings": warnings,
        }

    sample_jobs = _dataframe_sample(jobs, sample_size)
    if not sample_jobs:
        errors.append("Scrape returned no jobs.")

    normalized_records = []
    for index, row in enumerate(sample_jobs, start=1):
        title = _safe_text(row.get("title"))
        job_url = _safe_text(row.get("job_url"))
        if not title:
            errors.append(f"Sample job {index} is missing title.")
        if not job_url:
            errors.append(f"Sample job {index} is missing job_url.")
        record = jobs_table._build_job_record(row)
        if record is None:
            errors.append(f"Sample job {index} could not be normalized for DB import.")
        else:
            normalized_records.append(record)

    return _json_safe(
        {
            "sample_jobs": sample_jobs,
            "jobs_found": 0 if jobs is None else len(jobs),
            "normalized_records": normalized_records,
            "errors": errors,
            "warnings": warnings,
        }
    )


def build_scrape_kwargs(
    company_record: dict[str, Any],
    *,
    sample_size: int | None = None,
) -> dict[str, Any]:
    scraper_site = _required_text(company_record.get("scraper_site"), "scraper_site")
    fetch_url = (
        _safe_text(company_record.get("resolved_fetch_url"))
        or _required_text(company_record.get("career_page_url"), "career_page_url")
    )
    url_kwarg = URL_KWARG_BY_SITE.get(scraper_site)
    if not url_kwarg:
        raise ValueError(f"Unsupported scraper_site={scraper_site!r}")

    extra_params = company_record.get("extra_params") or {}
    if not isinstance(extra_params, dict):
        extra_params = {}

    kwargs: dict[str, Any] = {
        "site_name": scraper_site,
        "search_term": _safe_text(company_record.get("search_term")),
        "location": _safe_text(company_record.get("location")),
        "results_wanted": sample_size if sample_size is not None else (
            _safe_int(company_record.get("results_wanted")) or 0
        ),
        "country_indeed": _safe_text(company_record.get("country_indeed")) or "Israel",
        "description_format": _safe_text(company_record.get("description_format"))
        or "markdown",
        "description_limit": company_record.get("description_limit"),
        "request_timeout": _safe_int(company_record.get("request_timeout")) or 60,
        "verbose": 0,
        url_kwarg: fetch_url,
    }
    kwargs.update(extra_params)
    return kwargs


def _build_greenhouse_public_detection(
    *,
    company_name: str,
    input_url: str,
    board_token: str,
    country_indeed: str,
    notes: tuple[str, ...] = (),
) -> DetectedCareerPage:
    fetch_url = GREENHOUSE_API_TEMPLATE.format(board_token=board_token)
    config = {
        "company_name": company_name,
        "company_url": input_url,
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
        "constants": {"country": country_indeed},
        "location_filter_paths": ["location.name"],
    }
    return DetectedCareerPage(
        detected_platform="greenhouse_public_board",
        scraper_site="json_feed",
        input_url=input_url,
        resolved_fetch_url=fetch_url,
        extra_params={"json_feed_config": config},
        notes=notes,
    )


def _build_lever_detection(
    *,
    company_name: str,
    input_url: str,
    company_slug: str,
    country_indeed: str,
    notes: tuple[str, ...] = (),
) -> DetectedCareerPage:
    fetch_url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    config = {
        "company_name": company_name,
        "company_url": input_url,
        "field_paths": {
            "id": "id",
            "title": "text",
            "job_url": "hostedUrl",
            "apply_url": "applyUrl",
            "job_url_direct": "hostedUrl",
            "city": "categories.location",
            "description": ["description", "descriptionPlain"],
            "listing_type": "categories.commitment",
            "job_function": "categories.team",
        },
        "constants": {"country": country_indeed},
        "location_filter_paths": ["categories.location"],
    }
    return DetectedCareerPage(
        detected_platform="lever",
        scraper_site="json_feed",
        input_url=input_url,
        resolved_fetch_url=fetch_url,
        extra_params={"json_feed_config": config},
        notes=notes,
    )


def _build_base_row(
    *,
    company_key: str,
    company_name: str,
    career_page_url: str,
    location: str | None,
    country_indeed: str,
    request_timeout: int,
    scraper_site: str,
    resolved_fetch_url: str | None,
    extra_params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "company_key": company_key,
        "company_name": company_name,
        "company_aliases": [],
        "scraper_site": scraper_site,
        "career_page_url": career_page_url,
        "resolved_fetch_url": resolved_fetch_url,
        "search_term": None,
        "location": location,
        "country_indeed": country_indeed,
        "results_wanted": 0,
        "description_format": "markdown",
        "description_limit": None,
        "request_timeout": request_timeout,
        "extra_params": extra_params,
    }


def _find_greenhouse_board_token_in_page(
    session: requests.Session,
    page_url: str,
    page_text: str,
    timeout: int,
) -> str | None:
    board_token = _extract_greenhouse_board_token(page_text)
    if board_token:
        return board_token

    for script_url in _extract_script_urls(page_url, page_text):
        try:
            script_text = _fetch_text(session, script_url, timeout)
        except Exception:
            continue
        board_token = _extract_greenhouse_board_token(script_text)
        if board_token:
            return board_token
    return None


def _extract_greenhouse_board_token(value: str) -> str | None:
    for pattern in GREENHOUSE_BOARD_TOKEN_PATTERNS:
        match = pattern.search(value)
        if match:
            token = match.group("token").strip()
            if token:
                return token
    parsed = urlparse(value)
    host = (parsed.netloc or "").lower()
    if host in {"boards.greenhouse.io", "boards.eu.greenhouse.io", "job-boards.greenhouse.io"}:
        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts:
            return path_parts[0]
    return None


def _find_lever_slug_in_text(value: str) -> str | None:
    match = re.search(r"jobs\.lever\.co/(?P<slug>[^/?#\"']+)", value, re.I)
    return match.group("slug") if match else None


def _extract_lever_slug(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if host == "jobs.lever.co" and parts:
        return parts[0]
    if "api.lever.co" in host and "postings" in parts:
        index = parts.index("postings")
        if len(parts) > index + 1:
            return parts[index + 1]
    return None


def _extract_script_urls(page_url: str, page_text: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"<script[^>]+src=[\"']([^\"']+)[\"']", page_text, re.I):
        script_url = urljoin(page_url, match.group(1))
        if script_url not in urls:
            urls.append(script_url)
        if len(urls) >= 40:
            break
    for match in re.finditer(r"/_next/static/chunks/[^\"'\\\s<>]+?\.js", page_text):
        script_url = urljoin(page_url, match.group(0))
        if script_url not in urls:
            urls.append(script_url)
        if len(urls) >= 80:
            break
    return urls


def _try_fetch_json(
    session: requests.Session,
    url: str,
    timeout: int,
) -> Any | None:
    try:
        response = session.get(url, timeout=timeout, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def _infer_json_feed_config(
    payload: Any,
    company_name: str,
    url: str,
    country_indeed: str,
) -> dict[str, Any] | None:
    rows = _extract_rows(payload)
    if not rows:
        return None
    sample = next((row for row in rows if isinstance(row, dict)), None)
    if not sample:
        return None

    title_path = _first_existing_path(sample, ("title", "jobTitle", "job_title", "text", "name"))
    job_url_path = _first_existing_path(
        sample,
        ("absolute_url", "hostedUrl", "job_url", "jobUrl", "url", "applyUrl"),
    )
    if not title_path or not job_url_path:
        return None

    field_paths = {
        "title": title_path,
        "job_url": job_url_path,
        "apply_url": _first_existing_path(sample, ("apply_url", "applyUrl", job_url_path)),
        "job_url_direct": job_url_path,
        "id": _first_existing_path(sample, ("id", "jobId", "job_id", "requisition_id")),
        "city": _first_existing_path(sample, ("location.name", "categories.location", "location")),
        "description": _first_existing_path(
            sample,
            ("description", "content", "descriptionPlain", "jobDescription"),
        ),
        "listing_type": _first_existing_path(
            sample,
            ("listing_type", "employmentType", "categories.commitment", "type"),
        ),
        "job_function": _first_existing_path(
            sample,
            ("job_function", "category", "department", "categories.team"),
        ),
        "date_posted": _first_existing_path(
            sample,
            ("date_posted", "published_at", "updated_at", "openDate"),
        ),
    }
    field_paths = {key: value for key, value in field_paths.items() if value}
    config: dict[str, Any] = {
        "company_name": company_name,
        "company_url": url,
        "field_paths": field_paths,
        "constants": {"country": country_indeed},
    }
    location_path = field_paths.get("city")
    if location_path:
        config["location_filter_paths"] = [location_path]
    return config


def _extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("jobs", "data", "positions", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = _extract_rows(value)
                if nested:
                    return nested
    return []


def _first_existing_path(row: dict[str, Any], paths: tuple[str, ...]) -> str | None:
    for path in paths:
        if _get_path(row, path) is not None:
            return path
    return None


def _get_path(value: Any, path: str | None) -> Any:
    if not path:
        return None
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def _dataframe_sample(jobs: Any, sample_size: int) -> list[dict[str, Any]]:
    if jobs is None or getattr(jobs, "empty", False):
        return []
    sample = jobs.head(sample_size)
    records = sample.to_dict("records")
    return [_compact_sample_record(_json_safe(record)) for record in records]


def _compact_sample_record(record: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(record)
    for key, value in list(compacted.items()):
        if not isinstance(value, str):
            continue
        limit = 800 if key == "description" else 2000
        if len(value) > limit:
            compacted[key] = value[:limit].rstrip() + "...[truncated]"
    return compacted


def _fetch_text(session: requests.Session, url: str, timeout: int) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _build_session(user_agent: str | None) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = user_agent or DEFAULT_USER_AGENT
    return session


def _normalize_url(value: str) -> str:
    value = value.strip()
    if not re.match(r"^https?://", value, re.I):
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid career page URL: {value!r}")
    return value


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, field_name: str) -> str:
    text = _safe_text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "company"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
