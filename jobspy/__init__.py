from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

import pandas as pd

from jobspy.bayt import BaytScraper
from jobspy.bdjobs import BDJobs
from jobspy.apple import Apple
from jobspy.comeet import Comeet
from jobspy.chromium_cookies import resolve_linkedin_auth_context
from jobspy.eightfold import Eightfold
from jobspy.greenhouse import Greenhouse
from jobspy.glassdoor import Glassdoor
from jobspy.google import Google
from jobspy.google_careers import GoogleCareers
from jobspy.indeed import Indeed
from jobspy.json_feed import JsonFeed
from jobspy.linkedin import LinkedIn
from jobspy.meta import Meta
from jobspy.microsoft import Microsoft
from jobspy.naukri import Naukri
from jobspy.redhat import RedHat
from jobspy.varonis import Varonis
from jobspy.workday import Workday
from jobspy.model import (
    JobType,
    Location,
    JobResponse,
    Country,
    GreenhouseScrapeMode,
    LinkedInScrapeMode,
)
from jobspy.model import SalarySource, ScraperInput, Site
from jobspy.util import (
    set_logger_level,
    extract_salary,
    create_logger,
    get_enum_from_value,
    map_str_to_site,
    convert_to_annual,
    desired_order,
)
from jobspy.ziprecruiter import ZipRecruiter


# Update the SCRAPER_MAPPING dictionary in the scrape_jobs function

def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    google_careers_url: str | None = None,
    comeet_company_url: str | None = None,
    eightfold_company_url: str | None = None,
    workday_company_url: str | None = None,
    redhat_base_url: str | None = None,
    varonis_base_url: str | None = None,
    apple_search_url: str | None = None,
    microsoft_base_url: str | None = None,
    meta_careers_url: str | None = None,
    json_feed_url: str | None = None,
    json_feed_config: dict | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    description_limit: int | None = 1,
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    linkedin_geo_id: int | None = None,
    linkedin_execution_mode: str | LinkedInScrapeMode = LinkedInScrapeMode.DEFAULT,
    greenhouse_execution_mode: str | GreenhouseScrapeMode = GreenhouseScrapeMode.DEFAULT,
    num_of_min: int | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    user_agent: str = None,
    linkedin_auth_cookies: dict[str, str] | None = None,
    indeed_debug_trace: bool = False,
    comeet_debug_trace: bool = False,
    eightfold_debug_trace: bool = False,
    workday_debug_trace: bool = False,
    redhat_debug_trace: bool = False,
    varonis_debug_trace: bool = False,
    greenhouse_auth_cookies: dict[str, str] | None = None,
    greenhouse_xsrf_token: str | None = None,
    greenhouse_location_name: str | None = None,
    greenhouse_lat: float | None = None,
    greenhouse_lon: float | None = None,
    greenhouse_location_type: str | None = None,
    greenhouse_country_short_name: str | None = None,
    greenhouse_date_posted: str | None = None,
    greenhouse_debug_trace: bool = False,
    linkedin_page_delay_min: float | None = None,
    linkedin_page_delay_max: float | None = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Scrapes job data from job boards concurrently
    :return: Pandas DataFrame containing job data
    """
    SCRAPER_MAPPING = {
        Site.LINKEDIN: LinkedIn,
        Site.INDEED: Indeed,
        Site.ZIP_RECRUITER: ZipRecruiter,
        Site.GLASSDOOR: Glassdoor,
        Site.GOOGLE: Google,
        Site.GOOGLE_CAREERS: GoogleCareers,
        Site.COMEET: Comeet,
        Site.GREENHOUSE: Greenhouse,
        Site.EIGHTFOLD: Eightfold,
        Site.WORKDAY: Workday,
        Site.REDHAT: RedHat,
        Site.VARONIS: Varonis,
        Site.APPLE: Apple,
        Site.MICROSOFT: Microsoft,
        Site.META: Meta,
        Site.JSON_FEED: JsonFeed,
        Site.BAYT: BaytScraper,
        Site.NAUKRI: Naukri,
        Site.BDJOBS: BDJobs,  # Add BDJobs to the scraper mapping
    }
    set_logger_level(verbose)
    job_type = get_enum_from_value(job_type) if job_type else None
    linkedin_execution_mode = (
        LinkedInScrapeMode(linkedin_execution_mode)
        if isinstance(linkedin_execution_mode, str)
        else linkedin_execution_mode
    )
    greenhouse_execution_mode = (
        GreenhouseScrapeMode(greenhouse_execution_mode)
        if isinstance(greenhouse_execution_mode, str)
        else greenhouse_execution_mode
    )

    def get_site_type():
        site_types = [
            site
            for site in Site
            if site
            not in {
                Site.COMEET,
                Site.GREENHOUSE,
                Site.EIGHTFOLD,
                Site.WORKDAY,
                Site.REDHAT,
                Site.VARONIS,
                Site.APPLE,
                Site.MICROSOFT,
                Site.META,
                Site.GOOGLE_CAREERS,
                Site.JSON_FEED,
            }
        ]
        if isinstance(site_name, str):
            site_types = [map_str_to_site(site_name)]
        elif isinstance(site_name, Site):
            site_types = [site_name]
        elif isinstance(site_name, list):
            site_types = [
                map_str_to_site(site) if isinstance(site, str) else site
                for site in site_name
            ]
        return site_types

    country_enum = Country.from_string(country_indeed)

    scraper_input = ScraperInput(
        site_type=get_site_type(),
        country=country_enum,
        search_term=search_term,
        google_search_term=google_search_term,
        google_careers_url=google_careers_url,
        comeet_company_url=comeet_company_url,
        eightfold_company_url=eightfold_company_url,
        workday_company_url=workday_company_url,
        redhat_base_url=redhat_base_url,
        varonis_base_url=varonis_base_url,
        apple_search_url=apple_search_url,
        microsoft_base_url=microsoft_base_url,
        meta_careers_url=meta_careers_url,
        json_feed_url=json_feed_url,
        json_feed_config=json_feed_config,
        location=location,
        distance=distance,
        is_remote=is_remote,
        job_type=job_type,
        easy_apply=easy_apply,
        description_format=description_format,
        description_limit=description_limit,
        linkedin_fetch_description=linkedin_fetch_description,
        linkedin_geo_id=linkedin_geo_id,
        linkedin_page_delay_min=linkedin_page_delay_min,
        linkedin_page_delay_max=linkedin_page_delay_max,
        linkedin_execution_mode=linkedin_execution_mode,
        greenhouse_execution_mode=greenhouse_execution_mode,
        num_of_min=num_of_min,
        results_wanted=results_wanted,
        linkedin_company_ids=linkedin_company_ids,
        offset=offset,
        hours_old=hours_old,
        indeed_debug_trace=indeed_debug_trace,
        comeet_debug_trace=comeet_debug_trace,
        eightfold_debug_trace=eightfold_debug_trace,
        workday_debug_trace=workday_debug_trace,
        redhat_debug_trace=redhat_debug_trace,
        varonis_debug_trace=varonis_debug_trace,
        greenhouse_location_name=greenhouse_location_name,
        greenhouse_lat=greenhouse_lat,
        greenhouse_lon=greenhouse_lon,
        greenhouse_location_type=greenhouse_location_type,
        greenhouse_country_short_name=greenhouse_country_short_name,
        greenhouse_date_posted=greenhouse_date_posted,
        greenhouse_debug_trace=greenhouse_debug_trace,
    )
    resolved_linkedin_auth_cookies = linkedin_auth_cookies
    if (
        resolved_linkedin_auth_cookies is None
        and Site.LINKEDIN in scraper_input.site_type
    ):
        resolved_linkedin_auth_cookies, _ = resolve_linkedin_auth_context()

    def scrape_site(site: Site) -> Tuple[str, JobResponse]:
        scraper_class = SCRAPER_MAPPING[site]
        if site == Site.LINKEDIN:
            scraper = scraper_class(
                proxies=proxies,
                ca_cert=ca_cert,
                user_agent=user_agent,
                auth_cookies=resolved_linkedin_auth_cookies,
            )
        elif site == Site.GREENHOUSE:
            scraper = scraper_class(
                proxies=proxies,
                ca_cert=ca_cert,
                user_agent=user_agent,
                auth_cookies=greenhouse_auth_cookies,
                xsrf_token=greenhouse_xsrf_token,
            )
        else:
            scraper = scraper_class(
                proxies=proxies,
                ca_cert=ca_cert,
                user_agent=user_agent,
            )
        scraped_data: JobResponse = scraper.scrape(scraper_input)
        cap_name = site.value.capitalize()
        site_name = "ZipRecruiter" if cap_name == "Zip_recruiter" else cap_name
        site_name = "LinkedIn" if cap_name == "Linkedin" else cap_name
        create_logger(site_name).info(f"finished scraping")
        return site.value, scraped_data

    site_to_jobs_dict = {}

    def worker(site):
        site_val, scraped_info = scrape_site(site)
        return site_val, scraped_info

    with ThreadPoolExecutor() as executor:
        future_to_site = {
            executor.submit(worker, site): site for site in scraper_input.site_type
        }

        for future in as_completed(future_to_site):
            site_value, scraped_data = future.result()
            site_to_jobs_dict[site_value] = scraped_data

    jobs_dfs: list[pd.DataFrame] = []

    for site, job_response in site_to_jobs_dict.items():
        for job in job_response.jobs:
            job_data = job.dict()
            job_url = job_data["job_url"]
            job_data["site"] = site
            job_data["company"] = job_data["company_name"]
            job_data["job_type"] = (
                ", ".join(job_type.value[0] for job_type in job_data["job_type"])
                if job_data["job_type"]
                else None
            )
            job_data["emails"] = (
                ", ".join(job_data["emails"]) if job_data["emails"] else None
            )
            if job_data["location"]:
                job_data["location"] = Location(
                    **job_data["location"]
                ).display_location()

            # Handle compensation
            compensation_obj = job_data.get("compensation")
            if compensation_obj and isinstance(compensation_obj, dict):
                job_data["interval"] = (
                    compensation_obj.get("interval").value
                    if compensation_obj.get("interval")
                    else None
                )
                job_data["min_amount"] = compensation_obj.get("min_amount")
                job_data["max_amount"] = compensation_obj.get("max_amount")
                job_data["currency"] = compensation_obj.get("currency", "USD")
                job_data["salary_source"] = SalarySource.DIRECT_DATA.value
                if enforce_annual_salary and (
                    job_data["interval"]
                    and job_data["interval"] != "yearly"
                    and job_data["min_amount"]
                    and job_data["max_amount"]
                ):
                    convert_to_annual(job_data)
            else:
                if country_enum == Country.USA:
                    (
                        job_data["interval"],
                        job_data["min_amount"],
                        job_data["max_amount"],
                        job_data["currency"],
                    ) = extract_salary(
                        job_data["description"],
                        enforce_annual_salary=enforce_annual_salary,
                    )
                    job_data["salary_source"] = SalarySource.DESCRIPTION.value

            job_data["salary_source"] = (
                job_data["salary_source"]
                if "min_amount" in job_data and job_data["min_amount"]
                else None
            )

            #naukri-specific fields
            job_data["skills"] = (
                ", ".join(job_data["skills"]) if job_data["skills"] else None
            )
            job_data["experience_range"] = job_data.get("experience_range")
            job_data["company_rating"] = job_data.get("company_rating")
            job_data["company_reviews_count"] = job_data.get("company_reviews_count")
            job_data["vacancy_count"] = job_data.get("vacancy_count")
            job_data["work_from_home_type"] = job_data.get("work_from_home_type")

            job_df = pd.DataFrame([job_data])
            jobs_dfs.append(job_df)

    if jobs_dfs:
        # Step 1: Filter out all-NA columns from each DataFrame before concatenation
        filtered_dfs = [df.dropna(axis=1, how="all") for df in jobs_dfs]

        # Step 2: Concatenate the filtered DataFrames
        jobs_df = pd.concat(filtered_dfs, ignore_index=True)

        # Step 3: Ensure all desired columns are present, adding missing ones as empty
        for column in desired_order:
            if column not in jobs_df.columns:
                jobs_df[column] = None  # Add missing columns as empty

        # Reorder the DataFrame according to the desired order
        jobs_df = jobs_df[desired_order]

        # Step 4: Sort the DataFrame as required
        return jobs_df.sort_values(
            by=["site", "date_posted"], ascending=[True, False]
        ).reset_index(drop=True)
    else:
        return pd.DataFrame()


# Add BDJobs to __all__
__all__ = [
    "BDJobs",
]
