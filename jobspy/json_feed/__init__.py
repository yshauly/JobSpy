from __future__ import annotations

import html as html_lib
import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

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
    get_enum_from_job_type,
    markdown_converter,
    plain_converter,
)

log = create_logger("JsonFeed")

DEFAULT_ROWS_KEYS = ("jobs", "data", "positions", "results", "items")
TEMPLATE_FIELD_PATTERN = re.compile(r"{([^{}]+)}")


class JsonFeed(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.JSON_FEED,
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
        feed_url = self._safe_str(scraper_input.json_feed_url)
        if not feed_url:
            raise ValueError("JSON feed scrape requires scraper_input.json_feed_url")

        config = self._coerce_dict(scraper_input.json_feed_config)
        log.info(f"Fetching JSON feed jobs from {feed_url}")
        payload = self._fetch_payload(feed_url, config)
        rows = self._extract_rows(payload, self._get_config_value(config, "rows_path"))
        rows = [
            row
            for row in rows
            if isinstance(row, dict) and self._matches_filters(row, config)
        ]
        rows = self._apply_location_filter(rows, config, scraper_input.location)

        start = max(scraper_input.offset or 0, 0)
        target_count = (
            scraper_input.results_wanted if scraper_input.results_wanted > 0 else None
        )
        selected_rows = rows[start:]
        if target_count is not None:
            selected_rows = selected_rows[:target_count]

        job_posts: list[JobPost] = []
        for row in selected_rows:
            job_post = self._build_job_post(row, config)
            if job_post:
                job_posts.append(job_post)

        log.info(
            f"JSON feed scrape finished for {feed_url} with {len(job_posts)} job(s)"
        )
        return JobResponse(jobs=job_posts)

    def _fetch_payload(self, feed_url: str, config: dict[str, Any]) -> Any:
        method = (self._safe_str(config.get("method")) or "GET").upper()
        request_kwargs: dict[str, Any] = {
            "headers": self._coerce_dict(config.get("headers")),
            "timeout": self.scraper_input.request_timeout,
            "verify": False,
        }
        if method != "GET":
            if "json_body" in config:
                request_kwargs["json"] = config.get("json_body")
            elif "form_data" in config:
                request_kwargs["data"] = config.get("form_data")

        response = self.session.request(method, feed_url, **request_kwargs)
        response.raise_for_status()
        html_row_selector = self._safe_str(config.get("html_row_selector"))
        if html_row_selector:
            return self._extract_html_rows(
                response.text,
                html_row_selector=html_row_selector,
                config=config,
                base_url=getattr(response, "url", None) or feed_url,
            )

        html_json_script_id = self._safe_str(config.get("html_json_script_id"))
        if html_json_script_id:
            return self._extract_html_json_script(
                response.text,
                script_id=html_json_script_id,
            )
        return response.json()

    def _extract_html_json_script(self, html: str, *, script_id: str) -> Any:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id=script_id)
        if script is None:
            raise ValueError(f"HTML JSON script id={script_id!r} was not found")

        script_text = script.string or script.get_text()
        if not script_text or not script_text.strip():
            raise ValueError(f"HTML JSON script id={script_id!r} was empty")
        return json.loads(script_text)

    def _extract_html_rows(
        self,
        html: str,
        *,
        html_row_selector: str,
        config: dict[str, Any],
        base_url: str,
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        fields = self._coerce_dict(config.get("html_fields"))
        rows: list[dict[str, Any]] = []
        for element in soup.select(html_row_selector):
            row: dict[str, Any] = {}
            for field_name, field_config in fields.items():
                value = self._extract_html_field(
                    element,
                    field_config,
                    base_url=base_url,
                )
                if value is not None:
                    row[field_name] = value
            if row:
                rows.append(row)
        return rows

    def _extract_html_field(
        self,
        element: Any,
        field_config: Any,
        *,
        base_url: str,
    ) -> str | None:
        if isinstance(field_config, str):
            field_config = {"selector": field_config}
        if not isinstance(field_config, dict):
            return None

        selector = self._safe_str(field_config.get("selector"))
        target = (
            element
            if not selector or selector == "."
            else element.select_one(selector)
        )
        if target is None:
            return None

        attr = self._safe_str(field_config.get("attr")) or "text"
        if attr == "text":
            value = target.get_text(" ", strip=True)
        elif attr == "html":
            value = target.decode_contents()
        else:
            value = target.get(attr)

        text = self._safe_str(value)
        if not text:
            return None
        if bool(field_config.get("urljoin")):
            return urljoin(base_url, text)
        return text

    def _extract_rows(self, payload: Any, rows_path: Any) -> list[Any]:
        if rows_path is not None:
            rows = self._get_path(payload, rows_path)
            if not isinstance(rows, list):
                raise ValueError(f"JSON feed rows_path={rows_path!r} did not resolve to a list")
            return rows

        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict):
            for key in DEFAULT_ROWS_KEYS:
                rows = payload.get(key)
                if isinstance(rows, list):
                    return rows
            data = payload.get("data")
            if isinstance(data, dict):
                for key in DEFAULT_ROWS_KEYS:
                    rows = data.get(key)
                    if isinstance(rows, list):
                        return rows

        raise ValueError(
            "JSON feed response must be a list or expose a list through rows_path"
        )

    def _matches_filters(self, row: dict[str, Any], config: dict[str, Any]) -> bool:
        filters = config.get("filters") or []
        if not isinstance(filters, list):
            return True

        for filter_config in filters:
            if not isinstance(filter_config, dict):
                continue

            value = self._get_path(row, filter_config.get("path"))
            if "exists" in filter_config:
                exists = value is not None and value != ""
                if bool(filter_config["exists"]) != exists:
                    return False

            if "equals" in filter_config:
                expected = filter_config["equals"]
                if isinstance(expected, list):
                    if not any(self._values_equal(value, item) for item in expected):
                        return False
                elif not self._values_equal(value, expected):
                    return False

            if "contains" in filter_config:
                value_text = (self._safe_str(value) or "").casefold()
                expected_text = (self._safe_str(filter_config["contains"]) or "").casefold()
                if expected_text not in value_text:
                    return False

            if "in" in filter_config and isinstance(filter_config["in"], list):
                if not any(self._values_equal(value, item) for item in filter_config["in"]):
                    return False

        return True

    def _apply_location_filter(
        self,
        rows: list[dict[str, Any]],
        config: dict[str, Any],
        location: str | None,
    ) -> list[dict[str, Any]]:
        location_text = self._safe_str(location)
        location_paths = config.get("location_filter_paths") or []
        if not location_text or not location_paths or not isinstance(location_paths, list):
            return rows

        normalized_location = location_text.casefold()
        filtered_rows = []
        for row in rows:
            for path in location_paths:
                value = self._safe_str(self._get_path(row, path))
                if value and normalized_location in value.casefold():
                    filtered_rows.append(row)
                    break
        return filtered_rows

    def _build_job_post(
        self,
        row: dict[str, Any],
        config: dict[str, Any],
    ) -> JobPost | None:
        title = self._safe_str(self._resolve_field(row, config, "title"))
        job_url = self._safe_str(self._resolve_field(row, config, "job_url"))
        if not title or not job_url:
            return None

        description = self._build_description(row, config)
        detail_config = self._coerce_dict(config.get("detail_fetch"))
        if (
            detail_config
            and (not description or bool(detail_config.get("replace_description")))
            and self.claim_description_slot()
        ):
            detail_description = self._build_detail_description(
                row,
                config,
                detail_config,
                job_url,
            )
            if detail_description:
                description = detail_description

        emails = extract_emails_from_text(description or "") or None
        company_name = (
            self._safe_str(self._resolve_field(row, config, "company_name"))
            or self._company_name_from_url(job_url)
        )
        company_url = self._safe_str(self._resolve_field(row, config, "company_url"))

        return JobPost(
            id=self._safe_str(self._resolve_field(row, config, "id")),
            title=title,
            company_name=company_name,
            job_url=job_url,
            apply_url=self._safe_str(self._resolve_field(row, config, "apply_url")) or job_url,
            job_url_direct=self._safe_str(
                self._resolve_field(row, config, "job_url_direct")
            ) or job_url,
            location=self._build_location(row, config),
            description=description,
            company_url=company_url,
            company_url_direct=self._safe_str(
                self._resolve_field(row, config, "company_url_direct")
            )
            or company_url,
            company_logo=self._safe_str(self._resolve_field(row, config, "company_logo")),
            job_type=self._parse_job_type(self._resolve_field(row, config, "job_type")),
            date_posted=self._parse_date(
                self._resolve_field(row, config, "date_posted")
            ),
            emails=emails,
            is_remote=self._parse_bool(self._resolve_field(row, config, "is_remote")),
            listing_type=self._safe_str(
                self._resolve_field(row, config, "listing_type")
            ),
            job_level=self._safe_str(self._resolve_field(row, config, "job_level")),
            company_industry=self._safe_str(
                self._resolve_field(row, config, "company_industry")
            ),
            company_description=self._safe_str(
                self._resolve_field(row, config, "company_description")
            ),
            job_function=self._safe_str(
                self._resolve_field(row, config, "job_function")
            ),
            skills=self._parse_skills(self._resolve_field(row, config, "skills")),
        )

    def _build_location(
        self,
        row: dict[str, Any],
        config: dict[str, Any],
    ) -> Location | None:
        city = self._safe_str(self._resolve_field(row, config, "city"))
        state = self._safe_str(self._resolve_field(row, config, "state"))
        country = self._safe_str(self._resolve_field(row, config, "country"))

        city = self._apply_value_map("city", city, config)
        state = self._apply_value_map("state", state, config)
        country = self._apply_value_map("country", country, config)

        if not city and not state and not country:
            return None
        return Location(city=city, state=state, country=country)

    def _build_description(
        self,
        row: dict[str, Any],
        config: dict[str, Any],
    ) -> str | None:
        template = self._safe_str(self._get_template(config, "description"))
        if template:
            return self._convert_description_fragment(
                self._format_template(template, row)
            )

        sections = config.get("description_sections")
        if isinstance(sections, list):
            rendered_sections = []
            for section in sections:
                if isinstance(section, str):
                    title = None
                    path = section
                elif isinstance(section, dict):
                    title = self._safe_str(section.get("title"))
                    path = section.get("path")
                else:
                    continue

                content = self._safe_str(self._get_path(row, path))
                if not content:
                    continue
                rendered_sections.append(
                    self._render_description_section(title, content)
                )
            return self._join_description_sections(rendered_sections)

        description_paths = config.get("description_paths")
        if isinstance(description_paths, list):
            fragments = [
                self._convert_description_fragment(value)
                for value in (
                    self._safe_str(self._get_path(row, path))
                    for path in description_paths
                )
                if value
            ]
            return "\n\n".join(fragment for fragment in fragments if fragment) or None

        value = self._resolve_field(row, config, "description")
        return self._convert_description_fragment(value)

    def _build_detail_description(
        self,
        row: dict[str, Any],
        config: dict[str, Any],
        detail_config: dict[str, Any],
        fallback_url: str,
    ) -> str | None:
        detail_url = self._resolve_detail_url(row, config, detail_config, fallback_url)
        if not detail_url:
            return None

        try:
            detail_payload = self._fetch_detail_payload(detail_url, detail_config)
        except Exception as exc:
            log.debug(f"Failed to fetch JSON feed detail URL {detail_url}: {exc}")
            return None

        payload_path = detail_config.get("payload_path")
        if payload_path is not None:
            detail_payload = self._get_path(detail_payload, payload_path)

        if not isinstance(detail_payload, dict):
            return None
        return self._build_description(detail_payload, detail_config)

    def _resolve_detail_url(
        self,
        row: dict[str, Any],
        config: dict[str, Any],
        detail_config: dict[str, Any],
        fallback_url: str,
    ) -> str | None:
        url_template = self._safe_str(detail_config.get("url_template"))
        if url_template:
            detail_url = self._format_template(url_template, row)
        else:
            url_path = detail_config.get("url_path")
            detail_url = (
                self._safe_str(self._get_path(row, url_path)) if url_path else None
            )

        if not detail_url:
            url_field = self._safe_str(detail_config.get("url_field"))
            if url_field and url_field != "job_url":
                detail_url = self._safe_str(self._resolve_field(row, config, url_field))
            else:
                detail_url = fallback_url

        if not detail_url:
            return None
        if bool(detail_config.get("urljoin")):
            return urljoin(fallback_url, detail_url)
        return detail_url

    def _fetch_detail_payload(
        self,
        detail_url: str,
        detail_config: dict[str, Any],
    ) -> Any:
        method = (self._safe_str(detail_config.get("method")) or "GET").upper()
        request_kwargs: dict[str, Any] = {
            "headers": self._coerce_dict(detail_config.get("headers")),
            "timeout": self.scraper_input.request_timeout,
            "verify": False,
        }
        if method != "GET":
            if "json_body" in detail_config:
                request_kwargs["json"] = detail_config.get("json_body")
            elif "form_data" in detail_config:
                request_kwargs["data"] = detail_config.get("form_data")

        response = self.session.request(method, detail_url, **request_kwargs)
        response.raise_for_status()

        html_json_script_id = self._safe_str(detail_config.get("html_json_script_id"))
        if html_json_script_id:
            return self._extract_html_json_script(
                response.text,
                script_id=html_json_script_id,
            )

        html_description_selector = detail_config.get("html_description_selector")
        if html_description_selector:
            return self._extract_html_description_payload(
                response.text,
                selector_config=html_description_selector,
            )

        return response.json()

    def _extract_html_description_payload(
        self,
        html: str,
        *,
        selector_config: Any,
    ) -> dict[str, str]:
        selectors = (
            selector_config if isinstance(selector_config, list) else [selector_config]
        )
        soup = BeautifulSoup(html, "html.parser")
        attr = "html"
        for selector in selectors:
            if isinstance(selector, dict):
                attr = self._safe_str(selector.get("attr")) or "html"
                selector = selector.get("selector")
            selector = self._safe_str(selector)
            if not selector:
                continue
            element = soup.select_one(selector)
            if element is None:
                continue
            if attr == "text":
                value = element.get_text(" ", strip=True)
            else:
                value = element.decode_contents()
            description = self._safe_str(value)
            if description:
                return {"description": description}
        return {}

    def _render_description_section(self, title: str | None, content: str) -> str:
        converted_content = self._convert_description_fragment(content)
        if not converted_content:
            return ""

        description_format = getattr(
            self.scraper_input,
            "description_format",
            DescriptionFormat.MARKDOWN,
        )
        if not title:
            return converted_content
        if description_format == DescriptionFormat.HTML:
            return f"<h3>{html_lib.escape(title)}</h3>{converted_content}"
        if description_format == DescriptionFormat.PLAIN:
            return f"{title}\n{converted_content}"
        return f"### {title}\n\n{converted_content}"

    def _join_description_sections(self, sections: list[str]) -> str | None:
        sections = [section.strip() for section in sections if section and section.strip()]
        if not sections:
            return None

        description_format = getattr(
            self.scraper_input,
            "description_format",
            DescriptionFormat.MARKDOWN,
        )
        separator = "\n" if description_format == DescriptionFormat.HTML else "\n\n"
        return separator.join(sections)

    def _convert_description_fragment(self, value: Any) -> str | None:
        text = self._safe_str(value)
        if not text:
            return None

        text = html_lib.unescape(text)
        description_format = getattr(
            self.scraper_input,
            "description_format",
            DescriptionFormat.MARKDOWN,
        )
        is_html = bool(re.search(r"<[a-zA-Z][^>]*>", text))

        if description_format == DescriptionFormat.HTML:
            return text if is_html else html_lib.escape(text)
        if description_format == DescriptionFormat.PLAIN:
            return plain_converter(text) if is_html else text
        return markdown_converter(text) if is_html else text

    def _resolve_field(
        self,
        row: dict[str, Any],
        config: dict[str, Any],
        field_name: str,
    ) -> Any:
        template = self._get_template(config, field_name)
        if template:
            return self._format_template(template, row)

        path = self._get_field_path(config, field_name)
        if path is not None:
            value = self._get_path(row, path)
            value = self._apply_value_map(field_name, value, config)
            if value is not None:
                return value

        constants = self._coerce_dict(config.get("constants"))
        if field_name in constants:
            return constants[field_name]
        if field_name in {
            "company_name",
            "company_url",
            "company_url_direct",
            "company_logo",
            "country",
        }:
            return config.get(field_name)
        return None

    def _get_field_path(self, config: dict[str, Any], field_name: str) -> Any:
        field_paths = self._coerce_dict(config.get("field_paths"))
        if field_name in field_paths:
            return field_paths[field_name]
        return config.get(f"{field_name}_path")

    def _get_template(self, config: dict[str, Any], field_name: str) -> Any:
        templates = self._coerce_dict(config.get("templates"))
        if field_name in templates:
            return templates[field_name]
        return config.get(f"{field_name}_template")

    def _get_config_value(self, config: dict[str, Any], key: str) -> Any:
        return config.get(key)

    def _format_template(self, template: str, row: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            value = self._get_path(row, match.group(1).strip())
            return "" if value is None else str(value)

        return TEMPLATE_FIELD_PATTERN.sub(replace, template)

    def _get_path(self, value: Any, path: Any) -> Any:
        if path is None:
            return None
        if isinstance(path, (list, tuple)):
            for candidate_path in path:
                candidate_value = self._get_path(value, candidate_path)
                if candidate_value is not None:
                    return candidate_value
            return None
        if not isinstance(path, str):
            return None
        if path in {"", "$"}:
            return value

        current = value
        for part in self._split_path(path):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    current = self._get_named_list_item(current, part)
            else:
                return None

            if current is None:
                return None
        return current

    def _get_named_list_item(self, items: list[Any], name: str) -> Any:
        normalized_name = name.casefold()
        for item in items:
            if not isinstance(item, dict):
                continue
            item_name = self._safe_str(item.get("name"))
            if item_name and item_name.casefold() == normalized_name:
                return item
        return None

    def _split_path(self, path: str) -> list[str]:
        normalized = path.replace("[", ".").replace("]", "")
        return [part for part in normalized.split(".") if part]

    def _apply_value_map(
        self,
        field_name: str,
        value: Any,
        config: dict[str, Any],
    ) -> Any:
        value_maps = self._coerce_dict(config.get("value_maps"))
        field_map = value_maps.get(field_name)
        if not isinstance(field_map, dict):
            field_map = config.get(f"{field_name}_map")
        if not isinstance(field_map, dict):
            return value
        key = self._safe_str(value)
        if key is None:
            return value
        return field_map.get(key, field_map.get(value, value))

    def _values_equal(self, left: Any, right: Any) -> bool:
        if isinstance(left, (int, float, bool)) or isinstance(right, (int, float, bool)):
            return left == right
        return (self._safe_str(left) or "").casefold() == (
            self._safe_str(right) or ""
        ).casefold()

    def _parse_date(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = self._safe_str(value)
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        text = self._safe_str(value)
        if not text:
            return None
        normalized = text.casefold()
        if normalized in {"true", "1", "yes", "y", "remote"}:
            return True
        if normalized in {"false", "0", "no", "n", "onsite", "hybrid"}:
            return False
        return None

    def _parse_job_type(self, value: Any) -> list[JobType] | None:
        if value is None:
            return None
        items = value if isinstance(value, list) else [value]
        parsed: list[JobType] = []
        for item in items:
            text = self._safe_str(item)
            if not text:
                continue
            normalized = text.casefold().replace(" ", "").replace("-", "")
            job_type = get_enum_from_job_type(normalized)
            if job_type and job_type not in parsed:
                parsed.append(job_type)
        return parsed or None

    def _parse_skills(self, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, list):
            items = value
        else:
            text = self._safe_str(value)
            if not text:
                return None
            items = re.split(r"[,;]\s*", text)

        parsed = []
        for item in items:
            text = self._safe_str(item)
            if text and text not in parsed:
                parsed.append(text)
        return parsed or None

    def _company_name_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0]
        if not host:
            return None
        parts = [part for part in host.split(".") if part and part != "www"]
        if not parts:
            return None
        return parts[0].replace("-", " ").replace("_", " ").title()

    def _coerce_dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _safe_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None
