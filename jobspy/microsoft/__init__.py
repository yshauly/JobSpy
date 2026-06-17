from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from jobspy.eightfold import Eightfold
from jobspy.model import ScraperInput, Site

DEFAULT_MICROSOFT_BASE_URL = (
    "https://jobs.careers.microsoft.com/global/en/search?lc=Israel"
)


class Microsoft(Eightfold):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            proxies=proxies,
            ca_cert=ca_cert,
            user_agent=user_agent,
        )
        self.site = Site.MICROSOFT

    def scrape(self, scraper_input: ScraperInput):
        delegated_input = scraper_input.model_copy(deep=True)
        delegated_input.site_type = [Site.EIGHTFOLD]
        delegated_input.eightfold_company_url = self._resolve_base_url(scraper_input)
        return super().scrape(delegated_input)

    def _resolve_base_url(self, scraper_input: ScraperInput) -> str:
        raw_url = self._safe_str(scraper_input.microsoft_base_url) or DEFAULT_MICROSOFT_BASE_URL
        parsed = urlparse(raw_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        location = self._safe_str((query_params.get("location") or [None])[0])
        if location is None:
            location = self._safe_str((query_params.get("lc") or [None])[0])
        if location:
            query_params["location"] = [location]
        query_params.pop("lc", None)

        normalized_query = urlencode(
            [(key, value) for key, values in query_params.items() for value in values],
            doseq=True,
        )
        normalized_parsed = parsed
        if parsed.netloc.lower() == "jobs.careers.microsoft.com":
            normalized_parsed = parsed._replace(
                netloc="apply.careers.microsoft.com",
                path="/careers",
            )
        return urlunparse(normalized_parsed._replace(query=normalized_query))
