from __future__ import annotations

from jobspy.model import ScraperInput, Site
from jobspy.workday import Workday

DEFAULT_REDHAT_BASE_URL = (
    "https://redhat.wd5.myworkdayjobs.com/jobs/"
    "?a=084562884af243748dad7c84c304d89a"
)


class RedHat(Workday):
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
        self.site = Site.REDHAT

    def scrape(self, scraper_input: ScraperInput):
        delegated_input = scraper_input.model_copy(deep=True)
        delegated_input.site_type = [Site.WORKDAY]
        delegated_input.workday_company_url = self._resolve_base_url(scraper_input)
        if getattr(scraper_input, "redhat_debug_trace", False):
            delegated_input.workday_debug_trace = True
        response = super().scrape(delegated_input)
        for job in response.jobs:
            if self._safe_str(job.company_name) == "Careers at Red Hat":
                job.company_name = "Red Hat"
        return response

    def _resolve_base_url(self, scraper_input: ScraperInput) -> str:
        base_url = getattr(scraper_input, "redhat_base_url", None)
        normalized = self._safe_str(base_url)
        if normalized:
            return normalized
        return DEFAULT_REDHAT_BASE_URL
