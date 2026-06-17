from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from enum import Enum
from threading import Lock
from typing import Any, Optional

from pydantic import BaseModel


class JobType(Enum):
    FULL_TIME = (
        "fulltime",
        "períodointegral",
        "estágio/trainee",
        "cunormăîntreagă",
        "tiempocompleto",
        "vollzeit",
        "voltijds",
        "tempointegral",
        "全职",
        "plnýúvazek",
        "fuldtid",
        "دوامكامل",
        "kokopäivätyö",
        "tempsplein",
        "vollzeit",
        "πλήρηςαπασχόληση",
        "teljesmunkaidő",
        "tempopieno",
        "tempsplein",
        "heltid",
        "jornadacompleta",
        "pełnyetat",
        "정규직",
        "100%",
        "全職",
        "งานประจำ",
        "tamzamanlı",
        "повназайнятість",
        "toànthờigian",
    )
    PART_TIME = ("parttime", "teilzeit", "částečnýúvazek", "deltid")
    CONTRACT = ("contract", "contractor")
    TEMPORARY = ("temporary",)
    INTERNSHIP = (
        "internship",
        "prácticas",
        "ojt(onthejobtraining)",
        "praktikum",
        "praktik",
    )

    PER_DIEM = ("perdiem",)
    NIGHTS = ("nights",)
    OTHER = ("other",)
    SUMMER = ("summer",)
    VOLUNTEER = ("volunteer",)


class Country(Enum):
    """
    Gets the subdomain for Indeed and Glassdoor.
    The second item in the tuple is the subdomain (and API country code if there's a ':' separator) for Indeed
    The third item in the tuple is the subdomain (and tld if there's a ':' separator) for Glassdoor
    """

    ARGENTINA = ("argentina", "ar", "com.ar")
    AUSTRALIA = ("australia", "au", "com.au")
    AUSTRIA = ("austria", "at", "at")
    BAHRAIN = ("bahrain", "bh")
    BANGLADESH = ("bangladesh", "bd")  # Added Bangladesh
    BELGIUM = ("belgium", "be", "fr:be")
    BULGARIA = ("bulgaria", "bg")
    BRAZIL = ("brazil", "br", "com.br")
    CANADA = ("canada", "ca", "ca")
    CHILE = ("chile", "cl")
    CHINA = ("china", "cn")
    COLOMBIA = ("colombia", "co")
    COSTARICA = ("costa rica", "cr")
    CROATIA = ("croatia", "hr")
    CYPRUS = ("cyprus", "cy")
    CZECHREPUBLIC = ("czech republic,czechia", "cz")
    DENMARK = ("denmark", "dk")
    ECUADOR = ("ecuador", "ec")
    EGYPT = ("egypt", "eg")
    ESTONIA = ("estonia", "ee")
    FINLAND = ("finland", "fi")
    FRANCE = ("france", "fr", "fr")
    GERMANY = ("germany", "de", "de")
    GREECE = ("greece", "gr")
    HONGKONG = ("hong kong", "hk", "com.hk")
    HUNGARY = ("hungary", "hu")
    INDIA = ("india", "in", "co.in")
    INDONESIA = ("indonesia", "id")
    IRELAND = ("ireland", "ie", "ie")
    ISRAEL = ("israel", "il", "com")
    ITALY = ("italy", "it", "it")
    JAPAN = ("japan", "jp")
    KUWAIT = ("kuwait", "kw")
    LATVIA = ("latvia", "lv")
    LITHUANIA = ("lithuania", "lt")
    LUXEMBOURG = ("luxembourg", "lu")
    MALAYSIA = ("malaysia", "malaysia:my", "com")
    MALTA = ("malta", "malta:mt", "mt")
    MEXICO = ("mexico", "mx", "com.mx")
    MOROCCO = ("morocco", "ma")
    NETHERLANDS = ("netherlands", "nl", "nl")
    NEWZEALAND = ("new zealand", "nz", "co.nz")
    NIGERIA = ("nigeria", "ng")
    NORWAY = ("norway", "no")
    OMAN = ("oman", "om")
    PAKISTAN = ("pakistan", "pk")
    PANAMA = ("panama", "pa")
    PERU = ("peru", "pe")
    PHILIPPINES = ("philippines", "ph")
    POLAND = ("poland", "pl")
    PORTUGAL = ("portugal", "pt")
    QATAR = ("qatar", "qa")
    ROMANIA = ("romania", "ro")
    SAUDIARABIA = ("saudi arabia", "sa")
    SINGAPORE = ("singapore", "sg", "sg")
    SLOVAKIA = ("slovakia", "sk")
    SLOVENIA = ("slovenia", "sl")
    SOUTHAFRICA = ("south africa", "za")
    SOUTHKOREA = ("south korea", "kr")
    SPAIN = ("spain", "es", "es")
    SWEDEN = ("sweden", "se")
    SWITZERLAND = ("switzerland", "ch", "de:ch")
    TAIWAN = ("taiwan", "tw")
    THAILAND = ("thailand", "th")
    TURKEY = ("türkiye,turkey", "tr")
    UKRAINE = ("ukraine", "ua")
    UNITEDARABEMIRATES = ("united arab emirates", "ae")
    UK = ("uk,united kingdom", "uk:gb", "co.uk")
    USA = ("usa,us,united states", "www:us", "com")
    URUGUAY = ("uruguay", "uy")
    VENEZUELA = ("venezuela", "ve")
    VIETNAM = ("vietnam", "vn", "com")

    # internal for ziprecruiter
    US_CANADA = ("usa/ca", "www")

    # internal for linkedin
    WORLDWIDE = ("worldwide", "www")

    @property
    def indeed_domain_value(self):
        subdomain, _, api_country_code = self.value[1].partition(":")
        if subdomain and api_country_code:
            return subdomain, api_country_code.upper()
        return self.value[1], self.value[1].upper()

    @property
    def glassdoor_domain_value(self):
        if len(self.value) == 3:
            subdomain, _, domain = self.value[2].partition(":")
            if subdomain and domain:
                return f"{subdomain}.glassdoor.{domain}"
            else:
                return f"www.glassdoor.{self.value[2]}"
        else:
            raise Exception(f"Glassdoor is not available for {self.name}")

    def get_glassdoor_url(self):
        return f"https://{self.glassdoor_domain_value}/"

    @classmethod
    def from_string(cls, country_str: str):
        """Convert a string to the corresponding Country enum."""
        country_str = country_str.strip().lower()
        for country in cls:
            country_names = country.value[0].split(",")
            if country_str in country_names:
                return country
        valid_countries = [country.value for country in cls]
        raise ValueError(
            f"Invalid country string: '{country_str}'. Valid countries are: {', '.join([country[0] for country in valid_countries])}"
        )


class Location(BaseModel):
    country: Country | str | None = None
    city: Optional[str] = None
    state: Optional[str] = None

    def display_location(self) -> str:
        location_parts = []
        if self.city:
            location_parts.append(self.city)
        if self.state:
            location_parts.append(self.state)
        if isinstance(self.country, str):
            location_parts.append(self.country)
        elif self.country and self.country not in (
            Country.US_CANADA,
            Country.WORLDWIDE,
        ):
            country_name = self.country.value[0]
            if "," in country_name:
                country_name = country_name.split(",")[0]
            if country_name in ("usa", "uk"):
                location_parts.append(country_name.upper())
            else:
                location_parts.append(country_name.title())
        return ", ".join(location_parts)


class CompensationInterval(Enum):
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    HOURLY = "hourly"

    @classmethod
    def get_interval(cls, pay_period):
        interval_mapping = {
            "YEAR": cls.YEARLY,
            "HOUR": cls.HOURLY,
        }
        if pay_period in interval_mapping:
            return interval_mapping[pay_period].value
        else:
            return cls[pay_period].value if pay_period in cls.__members__ else None


class Compensation(BaseModel):
    interval: Optional[CompensationInterval] = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: Optional[str] = "USD"


class DescriptionFormat(Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN = "plain"

class JobPost(BaseModel):
    id: str | None = None
    title: str
    company_name: str | None
    job_url: str
    apply_url: str | None = None
    job_url_direct: str | None = None
    location: Optional[Location]

    description: str | None = None
    company_url: str | None = None
    company_url_direct: str | None = None

    job_type: list[JobType] | None = None
    compensation: Compensation | None = None
    date_posted: date | None = None
    emails: list[str] | None = None
    is_remote: bool | None = None
    listing_type: str | None = None
    applications_count: int | None = None

    # LinkedIn specific
    job_level: str | None = None

    # LinkedIn and Indeed specific
    company_industry: str | None = None

    # Indeed specific
    company_addresses: str | None = None
    company_num_employees: str | None = None
    company_revenue: str | None = None
    company_description: str | None = None
    company_logo: str | None = None
    banner_photo_url: str | None = None

    # LinkedIn only atm
    job_function: str | None = None

    # Naukri specific
    skills: list[str] | None = None  #from tagsAndSkills
    experience_range: str | None = None  #from experienceText
    company_rating: float | None = None  #from ambitionBoxData.AggregateRating
    company_reviews_count: int | None = None  #from ambitionBoxData.ReviewsCount
    vacancy_count: int | None = None  #from vacancy
    work_from_home_type: str | None = None  #from clusters.wfhType (e.g., "Hybrid", "Remote")

class JobResponse(BaseModel):
    jobs: list[JobPost] = []


class Site(Enum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    ZIP_RECRUITER = "zip_recruiter"
    GLASSDOOR = "glassdoor"
    GOOGLE = "google"
    GOOGLE_CAREERS = "google_careers"
    COMEET = "comeet"
    GREENHOUSE = "greenhouse"
    EIGHTFOLD = "eightfold"
    WORKDAY = "workday"
    REDHAT = "redhat"
    VARONIS = "varonis"
    APPLE = "apple"
    MICROSOFT = "microsoft"
    META = "meta"
    JSON_FEED = "json_feed"
    BAYT = "bayt"
    NAUKRI = "naukri"
    BDJOBS = "bdjobs"  # Add this line


class LinkedInScrapeMode(str, Enum):
    DEFAULT = "default"
    UNTIL_LAST_PAGE = "until-last-page"
    INSPECT_SINGLE_JOB = "inspect-single-job"
    INSPECT_SINGLE_PROFILE = "inspect-single-profile"


class GreenhouseScrapeMode(str, Enum):
    DEFAULT = "default"
    UNTIL_LAST_PAGE = "until-last-page"


class SalarySource(Enum):
    DIRECT_DATA = "direct_data"
    DESCRIPTION = "description"


class ScraperInput(BaseModel):
    site_type: list[Site]
    search_term: str | None = None
    google_search_term: str | None = None
    google_careers_url: str | None = None
    comeet_company_url: str | None = None
    eightfold_company_url: str | None = None
    workday_company_url: str | None = None
    redhat_base_url: str | None = None
    varonis_base_url: str | None = None
    apple_search_url: str | None = None
    microsoft_base_url: str | None = None
    meta_careers_url: str | None = None
    json_feed_url: str | None = None
    json_feed_config: dict[str, Any] | None = None

    location: str | None = None
    country: Country | None = Country.USA
    distance: int | None = None
    is_remote: bool = False
    job_type: JobType | None = None
    easy_apply: bool | None = None
    offset: int = 0
    linkedin_fetch_description: bool = False
    linkedin_company_ids: list[int] | None = None
    linkedin_geo_id: int | None = None
    linkedin_page_delay_min: float | None = None
    linkedin_page_delay_max: float | None = None
    linkedin_execution_mode: LinkedInScrapeMode = LinkedInScrapeMode.DEFAULT
    greenhouse_execution_mode: GreenhouseScrapeMode = GreenhouseScrapeMode.DEFAULT
    num_of_min: int | None = None
    description_format: DescriptionFormat | None = DescriptionFormat.MARKDOWN
    description_limit: int | None = 1
    indeed_debug_trace: bool = False
    comeet_debug_trace: bool = False
    eightfold_debug_trace: bool = False
    workday_debug_trace: bool = False
    redhat_debug_trace: bool = False
    varonis_debug_trace: bool = False
    greenhouse_location_name: str | None = None
    greenhouse_lat: float | None = None
    greenhouse_lon: float | None = None
    greenhouse_location_type: str | None = None
    greenhouse_country_short_name: str | None = None
    greenhouse_date_posted: str | None = None
    greenhouse_debug_trace: bool = False

    request_timeout: int = 60

    results_wanted: int = 15
    hours_old: int | None = None


class Scraper(ABC):
    def __init__(
        self, site: Site, proxies: list[str] | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        self.site = site
        self.proxies = proxies
        self.ca_cert = ca_cert
        self.user_agent = user_agent
        self._description_slot_lock = Lock()
        self._claimed_description_slots = 0

    def claim_description_slot(self) -> bool:
        scraper_input = getattr(self, "scraper_input", None)
        if scraper_input is None:
            return False

        limit = scraper_input.description_limit
        if limit is None:
            return True
        if limit <= 0:
            return False

        with self._description_slot_lock:
            if self._claimed_description_slots >= limit:
                return False
            self._claimed_description_slots += 1
            return True

    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...
