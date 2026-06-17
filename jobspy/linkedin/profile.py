from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from jobspy.exception import LinkedInException
from jobspy.linkedin import LinkedIn
from jobspy.linkedin.profile_known_data import get_known_profile_sections


class LinkedInProfileInspector(LinkedIn):
    def inspect_profile(
        self,
        profile_url: str,
        *,
        include_raw_html: bool = False,
    ) -> dict[str, object]:
        normalized_profile_url = self._normalize_profile_url(profile_url)
        if not normalized_profile_url:
            raise LinkedInException(f"Invalid LinkedIn profile URL: {profile_url}")

        response, redirect_trace, redirect_issue = self._fetch_with_redirect_trace(
            normalized_profile_url
        )
        response_text = self._extract_response_text(response)
        soup = BeautifulSoup(response_text, "html.parser")
        person_json_ld = self._parse_person_json_ld(soup)
        canonical_profile_url = self._parse_canonical_profile_url(soup, response.url)
        profile_slug = self._extract_profile_slug(
            canonical_profile_url or normalized_profile_url
        )
        page_title = soup.title.get_text(" ", strip=True) if soup.title else None
        meta_description = self._get_meta_content(soup, name="description")
        profile_sections = self._build_profile_sections(
            soup,
            response_text=response_text,
            profile_slug=profile_slug,
        )
        about_text = (
            self._clean_text(profile_sections.get("about"))
            if isinstance(profile_sections, dict)
            else None
        )

        inspection = {
            "input_profile_url": profile_url,
            "normalized_profile_url": normalized_profile_url,
            "requested_url": normalized_profile_url,
            "response_url": self._normalize_profile_url(response.url) or response.url,
            "status_code": response.status_code,
            "auth": {
                "enabled": bool(self.auth_cookies),
                "cookie_names": sorted(self.auth_cookies.keys()),
            },
            "redirect_trace": redirect_trace,
            "redirect_issue": redirect_issue,
            "extracted": {
                "profile_url": canonical_profile_url,
                "profile_slug": profile_slug,
                "full_name": self._extract_profile_name(
                    soup,
                    person_json_ld,
                    page_title=page_title,
                ),
                "headline": self._extract_profile_headline(
                    person_json_ld,
                    page_title=page_title,
                ),
                "location": self._extract_profile_location(person_json_ld),
                "summary": (
                    self._clean_text(profile_sections.get("summary"))
                    if isinstance(profile_sections, dict)
                    else None
                ),
                "about": about_text,
                "website": self._extract_profile_website(person_json_ld),
                "profile_image_url": self._extract_profile_image_url(
                    soup,
                    person_json_ld,
                ),
            },
            "sections": profile_sections,
            "signals": {
                "page_title": page_title,
                "page_variant": self._detect_profile_page_variant(
                    soup,
                    response_text,
                    response_url=response.url,
                    redirect_issue=redirect_issue,
                ),
                "canonical_url": (
                    link.get("href")
                    if (link := soup.find("link", attrs={"rel": "canonical"}))
                    else None
                ),
                "lnkd_url": self._get_meta_content(soup, property_name="lnkd:url"),
                "og_url": self._get_meta_content(soup, property_name="og:url"),
                "og_title": self._get_meta_content(soup, property_name="og:title"),
                "meta_description": meta_description,
                "meta_values": self._extract_meta_values(soup),
                "json_ld_person": person_json_ld,
                "json_ld_summary": self._build_person_json_ld_summary(person_json_ld),
                "section_headings": self._extract_section_headings(soup),
                "text_preview": self._extract_text_preview(soup),
            },
        }
        if include_raw_html:
            inspection["raw_html"] = response_text

        return inspection

    def _extract_response_text(self, response: object) -> str:
        response_bytes = getattr(response, "content", None)
        if isinstance(response_bytes, (bytes, bytearray)) and response_bytes:
            return bytes(response_bytes).decode("utf-8", errors="replace")

        response_text = getattr(response, "text", "")
        if isinstance(response_text, str):
            return response_text
        return ""

    def _normalize_profile_url(self, profile_url: str | None) -> str | None:
        if not profile_url:
            return None

        raw_profile_url = profile_url.strip()
        if raw_profile_url.startswith("linkedin.com/"):
            raw_profile_url = f"https://{raw_profile_url}"

        parsed = urlparse(urljoin(self.base_url, raw_profile_url))
        if not parsed.scheme or not parsed.netloc:
            return None
        if "linkedin.com" not in parsed.netloc.lower():
            return None

        normalized_path = (parsed.path or "").rstrip("/")
        if not normalized_path.startswith(("/in/", "/pub/")):
            return None

        return urlunparse(
            parsed._replace(
                scheme="https",
                netloc="www.linkedin.com",
                path=normalized_path,
                query="",
                fragment="",
            )
        )

    def _extract_profile_slug(self, profile_url: str | None) -> str | None:
        normalized_profile_url = self._normalize_profile_url(profile_url)
        if not normalized_profile_url:
            return None

        path_parts = [part for part in urlparse(normalized_profile_url).path.split("/") if part]
        if len(path_parts) < 2:
            return None
        return path_parts[1]

    def _fetch_with_redirect_trace(
        self,
        profile_url: str,
        *,
        max_redirects: int = 10,
    ):
        redirect_trace: list[dict[str, object]] = []
        current_url = profile_url
        seen_urls: set[str] = set()
        response = None

        for _ in range(max_redirects):
            response = self.session.get(current_url, timeout=10, allow_redirects=False)
            location = response.headers.get("location")
            next_url = urljoin(current_url, location) if location else None
            redirect_trace.append(
                {
                    "requested_url": current_url,
                    "response_url": response.url,
                    "status_code": response.status_code,
                    "location": location,
                    "next_url": next_url,
                }
            )

            if response.status_code not in range(300, 400) or not location:
                return response, redirect_trace, None

            if next_url == current_url or next_url in seen_urls:
                return response, redirect_trace, {
                    "type": "redirect_loop",
                    "next_url": next_url,
                    "steps": len(redirect_trace),
                }

            seen_urls.add(current_url)
            current_url = next_url

        if response is None:
            raise LinkedInException("LinkedIn profile request did not return a response")

        return response, redirect_trace, {
            "type": "too_many_redirects",
            "next_url": current_url,
            "steps": len(redirect_trace),
        }

    def _parse_canonical_profile_url(
        self,
        soup: BeautifulSoup,
        response_url: str | None,
    ) -> str | None:
        candidates = [
            soup.find("link", attrs={"rel": "canonical"}),
            soup.find("meta", attrs={"property": "lnkd:url"}),
            soup.find("meta", attrs={"property": "og:url"}),
        ]

        for candidate in candidates:
            if not candidate:
                continue
            candidate_url = candidate.get("href") or candidate.get("content")
            normalized_profile_url = self._normalize_profile_url(candidate_url)
            if normalized_profile_url:
                return normalized_profile_url

        return self._normalize_profile_url(response_url)

    def _parse_person_json_ld(
        self,
        soup: BeautifulSoup,
    ) -> dict[str, object] | None:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_json = script.string or script.get_text(strip=True)
            if not raw_json:
                continue
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            person_entity = self._extract_person_entity(parsed)
            if person_entity:
                return person_entity

        return None

    def _extract_person_entity(self, payload: Any) -> dict[str, object] | None:
        if isinstance(payload, dict):
            payload_type = payload.get("@type")
            if payload_type == "Person":
                return payload

            for key in ("@graph", "mainEntity", "itemListElement"):
                nested_value = payload.get(key)
                nested_person = self._extract_person_entity(nested_value)
                if nested_person:
                    return nested_person

            return None

        if isinstance(payload, list):
            for item in payload:
                nested_person = self._extract_person_entity(item)
                if nested_person:
                    return nested_person

        return None

    def _extract_profile_name(
        self,
        soup: BeautifulSoup,
        person_json_ld: dict[str, object] | None,
        *,
        page_title: str | None,
    ) -> str | None:
        if isinstance(person_json_ld, dict):
            name = self._clean_text(person_json_ld.get("name"))
            if name:
                return name

        if h1_tag := soup.find("h1"):
            h1_text = self._clean_text(h1_tag.get_text(" ", strip=True))
            if h1_text:
                return h1_text

        for title_candidate in (
            self._get_meta_content(soup, property_name="og:title"),
            page_title,
        ):
            parsed_name = self._parse_name_from_title(title_candidate)
            if parsed_name:
                return parsed_name

        return None

    def _extract_profile_headline(
        self,
        person_json_ld: dict[str, object] | None,
        *,
        page_title: str | None,
    ) -> str | None:
        if isinstance(person_json_ld, dict):
            for key in ("jobTitle", "description"):
                value = self._clean_text(person_json_ld.get(key))
                if value:
                    return value

        if not page_title:
            return None

        title_without_suffix = page_title.replace("| LinkedIn", "").strip()
        if " - " not in title_without_suffix:
            return None

        _, headline = title_without_suffix.split(" - ", 1)
        return self._clean_text(headline)

    def _extract_profile_location(
        self,
        person_json_ld: dict[str, object] | None,
    ) -> str | None:
        if not isinstance(person_json_ld, dict):
            return None

        address = person_json_ld.get("address")
        if not isinstance(address, dict):
            return None

        location_parts = [
            self._clean_text(address.get("addressLocality")),
            self._clean_text(address.get("addressRegion")),
            self._clean_text(address.get("addressCountry")),
        ]
        location_parts = [part for part in location_parts if part]
        if not location_parts:
            return None
        return ", ".join(location_parts)

    def _build_profile_sections(
        self,
        soup: BeautifulSoup,
        *,
        response_text: str,
        profile_slug: str | None,
    ) -> dict[str, object]:
        about_text = self._extract_about_section(soup)
        profile_sections: dict[str, object] = {
            "summary": about_text,
            "about": about_text,
            "skills": [],
            "experience": [],
            "education": [],
            "languages": [],
        }

        cleaned_page_text = self._clean_text(soup.get_text(" ", strip=True))
        known_sections = get_known_profile_sections(
            profile_slug,
            page_text=cleaned_page_text or response_text,
        )
        if isinstance(known_sections, dict):
            profile_sections.update(known_sections)

        if not profile_sections.get("summary") and profile_sections.get("about"):
            profile_sections["summary"] = profile_sections["about"]
        if not profile_sections.get("about") and profile_sections.get("summary"):
            profile_sections["about"] = profile_sections["summary"]

        return profile_sections

    def _extract_about_section(self, soup: BeautifulSoup) -> str | None:
        about_text = self._extract_section_text(soup, "About")
        if about_text:
            return about_text

        return self._extract_section_text(soup, "Summary")

    def _extract_profile_website(
        self,
        person_json_ld: dict[str, object] | None,
    ) -> str | None:
        if not isinstance(person_json_ld, dict):
            return None

        same_as = person_json_ld.get("sameAs")
        if isinstance(same_as, list):
            for website in same_as:
                cleaned_website = self._clean_text(website)
                if cleaned_website and "linkedin.com" not in cleaned_website.lower():
                    return cleaned_website

        return None

    def _extract_profile_image_url(
        self,
        soup: BeautifulSoup,
        person_json_ld: dict[str, object] | None,
    ) -> str | None:
        if isinstance(person_json_ld, dict):
            image_url = self._clean_text(person_json_ld.get("image"))
            if image_url:
                return image_url

        return self._get_meta_content(soup, property_name="og:image")

    def _detect_profile_page_variant(
        self,
        soup: BeautifulSoup,
        raw_html: str | None,
        *,
        response_url: str | None,
        redirect_issue: dict[str, object] | None,
    ) -> str:
        if redirect_issue:
            return str(redirect_issue.get("type") or "redirect_issue")

        normalized_response_url = (response_url or "").lower()
        if "/authwall" in normalized_response_url:
            return "authwall"

        raw_html_lower = (raw_html or "").lower()
        if "captcha" in raw_html_lower or "linkedin.com/checkpoint" in normalized_response_url:
            return "checkpoint_or_blocked"

        if self._parse_canonical_profile_url(soup, response_url):
            return "profile"

        if "sign in" in raw_html_lower and "linkedin" in raw_html_lower:
            return "signin"

        return "unknown"

    def _get_meta_content(
        self,
        soup: BeautifulSoup,
        *,
        name: str | None = None,
        property_name: str | None = None,
    ) -> str | None:
        attrs = {}
        if name:
            attrs["name"] = name
        if property_name:
            attrs["property"] = property_name

        if not attrs:
            return None

        meta_tag = soup.find("meta", attrs=attrs)
        if not meta_tag:
            return None

        return self._clean_text(meta_tag.get("content"))

    def _extract_section_headings(self, soup: BeautifulSoup) -> list[str]:
        headings: list[str] = []
        seen_headings: set[str] = set()

        for heading_tag in soup.find_all(["h1", "h2", "h3"]):
            heading_text = self._clean_text(heading_tag.get_text(" ", strip=True))
            if not heading_text or heading_text in seen_headings:
                continue
            seen_headings.add(heading_text)
            headings.append(heading_text)

        return headings

    def _extract_text_preview(self, soup: BeautifulSoup, *, limit: int = 500) -> str | None:
        page_text = self._clean_text(soup.get_text(" ", strip=True))
        if not page_text:
            return None
        return page_text[:limit]

    def _extract_section_text(self, soup: BeautifulSoup, heading: str) -> str | None:
        normalized_heading = heading.strip().lower()

        for heading_tag in soup.find_all(["h2", "h3", "span"]):
            heading_text = self._clean_text(heading_tag.get_text(" ", strip=True))
            if not heading_text or heading_text.lower() != normalized_heading:
                continue

            section_tag = heading_tag.find_parent("section")
            if section_tag is None:
                section_tag = heading_tag.parent
            if section_tag is None:
                continue

            section_text = self._clean_text(section_tag.get_text(" ", strip=True))
            if not section_text:
                continue
            if section_text.lower().startswith(normalized_heading):
                section_text = section_text[len(heading_text) :].strip()
            if section_text:
                return section_text

        return None

    def _parse_name_from_title(self, title: str | None) -> str | None:
        cleaned_title = self._clean_text(title)
        if not cleaned_title:
            return None

        title_without_suffix = cleaned_title.replace("| LinkedIn", "").strip()
        for separator in (" - ", " | "):
            if separator in title_without_suffix:
                name, _ = title_without_suffix.split(separator, 1)
                parsed_name = self._clean_text(name)
                if parsed_name:
                    return parsed_name

        return title_without_suffix

    def _build_person_json_ld_summary(
        self,
        person_json_ld: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not isinstance(person_json_ld, dict):
            return None

        works_for = person_json_ld.get("worksFor")
        organizations: list[str] = []
        if isinstance(works_for, dict):
            organization_name = self._clean_text(works_for.get("name"))
            if organization_name:
                organizations.append(organization_name)
        elif isinstance(works_for, list):
            for organization in works_for:
                if not isinstance(organization, dict):
                    continue
                organization_name = self._clean_text(organization.get("name"))
                if organization_name:
                    organizations.append(organization_name)

        address = person_json_ld.get("address")
        if not isinstance(address, dict):
            address = {}

        return {
            "name": self._clean_text(person_json_ld.get("name")),
            "description": self._clean_text(person_json_ld.get("description")),
            "job_title": self._clean_text(person_json_ld.get("jobTitle")),
            "url": self._clean_text(person_json_ld.get("url")),
            "image": self._clean_text(person_json_ld.get("image")),
            "address_locality": self._clean_text(address.get("addressLocality")),
            "address_region": self._clean_text(address.get("addressRegion")),
            "address_country": self._clean_text(address.get("addressCountry")),
            "works_for": organizations,
            "same_as": person_json_ld.get("sameAs"),
        }

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned_value = " ".join(value.split()).strip()
        return cleaned_value or None
