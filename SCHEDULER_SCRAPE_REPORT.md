# Scheduler Scrape Report

## Overview

`--scheduler` runs in `Asia/Jerusalem` on a fixed hourly cadence at `hh:30`, starting at `07:30` and ending at `22:30`.

Hourly scheduler sites:

- LinkedIn
- Indeed
- Glassdoor
- Amdocs
- Marvell
- Red Hat
- Varonis

Three-hour scheduler sites, anchored to `07:30`:

- Comeet
- Greenhouse

Three-hour runs therefore happen at:

- `07:30`
- `10:30`
- `13:30`
- `16:30`
- `19:30`
- `22:30`

## Site Matrix

| Scheduler label | Underlying source/platform | Cadence in `--scheduler` | Main scheduler filters | Output and persistence | Notes |
| --- | --- | --- | --- | --- | --- |
| LinkedIn | LinkedIn jobs feed | Hourly | `location=Israel`, default Israel `geoId`, `execution_mode=until-last-page`, `num_of_min=1440` on the scheduled `07:30` run and `60` on later runs, descriptions enabled | Writes `linkedin_jobs.json`, then persists to the `jobs` table | The LinkedIn scheduler step goes through `run_once()`, which currently scrapes both `linkedin` and `redhat` together in the same call, so `linkedin_jobs.json` can contain Red Hat rows too. |
| Indeed | Indeed | Hourly | `search_term=None`, `location=Israel`, `country_indeed=Israel`, `distance=50` when not overridden, `hours_old=24` on the scheduled `07:30` run and `1` on later runs | Writes `indeed_jobs.json`, then persists to the `jobs` table | Persistence mode always keeps descriptions enabled for parsing. |
| Glassdoor | Glassdoor | Hourly | `search_term=None`, `location=Israel`, `country_indeed=Israel`, fixed `hours_old=72` | Writes `glassdoor_jobs.json`, then persists to the `jobs` table | Glassdoor does not use the rolling 24h/60m window. It stays on a fixed 3-day lookback. |
| Amdocs | Eightfold company feed | Hourly | `search_term=None`, base URL defaults to `DEFAULT_AMDOCS_BASE_URL`, descriptions enabled | Writes `amdocs_jobs.json`, then persists to the `jobs` table | This is a company-specific Eightfold scrape, not a general board-wide search. |
| Marvell | Workday company feed | Hourly | `search_term=None`, `country_indeed=Israel`, base URL defaults to `DEFAULT_MARVELL_BASE_URL`, descriptions enabled | Writes `marvell_jobs.json`, then persists to the `jobs` table | This uses the generic `workday` scraper against Marvell's configured company URL. |
| Red Hat | Red Hat Workday wrapper | Hourly | `search_term=None`, `location=Israel`, `country_indeed=Israel`, base URL defaults to `DEFAULT_REDHAT_BASE_URL`, descriptions enabled | Writes `redhat_jobs.json`, then persists to the `jobs` table | Red Hat also appears inside the LinkedIn scheduler step because `run_once()` includes `redhat` in its scrape call. |
| Varonis | Jobvite-backed Varonis scraper | Hourly | `search_term=None`, `location=Israel`, `country_indeed=Israel`, base URL defaults to `DEFAULT_VARONIS_BASE_URL`, full Israel pull, descriptions enabled | Writes `varonis_jobs.json`, then persists to the `jobs` table | This is exposed as a dedicated `varonis` scraper, but the run report labels its platform as `jobvite`. |
| Comeet | Comeet ATS company pages | Every 3 hours | `search_term=None`, country filter fixed to `Israel`, `results_wanted=0` for full-company pulls | Writes `comeet_jobs.json`, then persists via `populate_comeet_jobs_table()` | Reads all companies from `company_comeet_job_urls` first, then scrapes each Comeet company page one by one. |
| Greenhouse | Greenhouse ATS | Every 3 hours | `search_term=None`, `location=Israel`, `country_indeed=Israel`, `greenhouse_date_posted=past_ten_days`, `execution_mode=until-last-page` | Writes `greenhouse_jobs.json`, then persists to the `jobs` table | Requires authenticated Greenhouse cookies. In scheduler mode, it defaults to `jobspy/greenhouse/greenhouse.cookies` if no cookie input is provided. |

## Dedicated Comeet Section

### What the scheduler runs

On each three-hour scheduler tick, `--scheduler` calls the Comeet batch persistence flow, not the one-company debug flow. The entry point is `run_comeet_persist_all_israel()`.

### Dependency before it can run

Comeet does not discover companies on its own during scheduler execution. It first reads every row from `company_comeet_job_urls`.

That table must already be populated by running:

- `--populate-comeet-base-urls`

The population step extracts normalized company base URLs such as:

- `https://www.comeet.com/jobs/<company-slug>/<company-code>`

### Comeet batch flow

- Load all company records from `company_comeet_job_urls`.
- For each `comeet_base_url`, call `scrape_jobs(site_name="comeet", results_wanted=0, country_indeed="Israel", description_format="markdown")`.
- Merge all returned company dataframes into one combined jobs dataframe.
- Save the combined result to `comeet_jobs.json`.
- Persist the normalized rows with `populate_comeet_jobs_table()`.

### How the Comeet scraper extracts jobs

For each company page, the Comeet scraper:

- Fetches the company page URL stored in `comeet_company_url`.
- Extracts embedded JSON from `COMPANY_DATA` and `COMPANY_POSITIONS_DATA`.
- Falls back to `POSITION_DATA` when the page exposes a single job instead of a positions list.
- Filters positions by country aliases derived from the requested country.
- Deduplicates jobs by `job_url` before returning them.

### What gets captured from Comeet

The Comeet job normalization includes:

- Title
- Company name
- Hosted job URL and apply URL
- Direct active-page URL when present
- Location
- Markdown description
- Job type
- Remote or hybrid signal
- Experience level
- Company URL
- Company logo
- Company description
- Date posted
- Emails found explicitly or inside the description

### Comeet scheduler behavior in practice

- Scope: all companies stored in `company_comeet_job_urls`
- Geography: Israel only in `--scheduler`
- Results mode: full-company pulls with `results_wanted=0`
- Trace level: disabled during scheduler runs
- Persistence path: `comeet_jobs.json` -> `populate_comeet_jobs_table()`
- Schedule: `07:30`, `10:30`, `13:30`, `16:30`, `19:30`, `22:30` Israel time

## Important Implementation Notes

- The hourly LinkedIn scheduler step uses `run_once()`, and `run_once()` currently scrapes `["linkedin", "redhat"]` together. That means Red Hat is touched once inside the LinkedIn step and again in the dedicated Red Hat scheduler step.
- The scheduler publishes one `scrape.finished` event per tick with all successful site runs collected into a single payload.
- Scheduler mode forces `save_db=True` and suppresses preview output for the site-specific scheduler args it builds.

## Files Reviewed

- `jobspy/__main__.py`
- `jobspy/comeet/__init__.py`
- `jobspy/jobs_table.py`
- `tests/test_main.py`
