# Company Board Israel Investigation

## Goal

Find 50 large technology or technology-adjacent S&P 500 companies and identify the Israel-focused career-board search target for each one.

This is an investigation artifact, not an implementation plan. The purpose is to decide which company boards are good next candidates after the existing company-board scrapers such as Amdocs, Marvell, Red Hat, and Varonis.

## Selection Rule

The company list is based on S&P 500 companies by index weight, using the US500 table updated June 1, 2026. I selected the highest-ranked technology, internet, semiconductor, enterprise software, data-center, communications-equipment, and tech-infrastructure companies until reaching 50 names.

Primary data file:

- `COMPANY_BOARD_ISRAEL_TARGETS.csv`

Primary S&P source:

- https://us500.com/tools/data/sp500-companies-by-weight?__source=newsletter%7Cwarrenbuffettwatch

## Recommended First Scraper Targets

These are the cleanest-looking targets because they use scraper-friendly ATS systems or have strong Israel hiring footprints.

| Company | Platform | Israel search target | Why it is a good candidate |
| --- | --- | --- | --- |
| Applied Materials | Workday | `q=Israel` | Confirmed Workday tenant and strong Israel presence. |
| KLA | Workday | `q=Israel` | Confirmed Workday tenant and strong Israel presence. |
| Cadence | Workday | `q=Israel` | Confirmed Workday tenant and likely useful EDA roles. |
| Analog Devices | Workday | `q=Israel` | Confirmed Workday tenant and semiconductor relevance. |
| NXP | Workday | `q=Israel` | Confirmed Workday tenant and semiconductor relevance. |
| Broadcom | Workday | `q=Israel` | Confirmed Workday tenant and official Israel matches visible. |
| Palo Alto Networks | SmartRecruiters | `search=Israel` | SmartRecruiters is usually straightforward to scrape. |
| Western Digital | SmartRecruiters | `search=Israel` | SmartRecruiters board responds cleanly. |
| Palantir | Lever | `location=Tel Aviv, Israel` | Lever board is highly structured and scraper-friendly. |
| Apple | Apple careers | `location=israel-ISR` | Stable official Israel location parameter. |
| Google | Google Careers | `location=Israel` | Official search route and active Israel jobs visible. |
| Microsoft | Microsoft Careers | `lc=Israel` | Official location filter and active Israel careers page. |
| Amazon | Amazon Jobs | `loc_query=Israel` | Stable official jobs search query. |
| Intuit | Phenom / company careers | Israel location route | Official Israel search route responds cleanly. |
| Synopsys | Phenom / company careers | Israel location route | Official Israel search route responds cleanly. |

## Higher-Effort But Valuable Targets

These are still attractive, but they likely need browser/API discovery because the public page is JavaScript-heavy, blocks shell fetches, or routes through a vendor shell.

| Company | Platform | Israel search target | Investigation note |
| --- | --- | --- | --- |
| Intel | Intel careers | `Israel` | Important Israel employer, but shell fetches were blocked or redirected. |
| Dell | Oracle Cloud / company careers | `location=Israel` | Israel locations are visible in official search results; route needs browser/API discovery. |
| Oracle | Oracle Cloud Recruiting | `location=Israel` | Likely needs Oracle recruiting API handling. |
| Meta | Meta Careers | `offices[]=Tel Aviv, Israel` | Search shell responds, likely backed by GraphQL. |
| Tesla | Tesla careers | `location=Israel` | Official page exposes Israel location, but shell fetch returned `403`. |
| Cisco | Phenom / company careers | `location=Israel` | Official route responds, but data extraction likely API-backed. |
| Micron | Eightfold / company careers | `query=Israel` | Route responds; API payload should be inspected. |
| AMD | Eightfold / company careers | `keywords=Israel` | Route responds; API payload should be inspected. |
| Qualcomm | Eightfold / company careers | `query=Israel` | Route responds; API payload should be inspected. |
| Adobe | Phenom / company careers | `keywords=Israel` | Route responds; API payload should be inspected. |

## Full 50-Company List

| # | S&P rank | Ticker | Company | Platform | Israel search term/filter |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | NVDA | NVIDIA | Phenom / company careers | `Israel` |
| 2 | 2 | AAPL | Apple | Apple careers | `location=israel-ISR` |
| 3 | 3 | MSFT | Microsoft | Microsoft careers | `lc=Israel` |
| 4 | 4 | AMZN | Amazon | Amazon Jobs | `loc_query=Israel` |
| 5 | 5 | AVGO | Broadcom | Workday | `q=Israel` |
| 6 | 6 | GOOGL/GOOG | Alphabet / Google | Google Careers | `location=Israel` |
| 7 | 8 | TSLA | Tesla | Tesla careers | `location=Israel` |
| 8 | 9 | META | Meta Platforms | Meta Careers | `offices[]=Tel Aviv, Israel` |
| 9 | 10 | MU | Micron Technology | Eightfold / company careers | `query=Israel` |
| 10 | 14 | AMD | Advanced Micro Devices | Eightfold / company careers | `keywords=Israel` |
| 11 | 16 | ORCL | Oracle | Oracle Cloud Recruiting | `location=Israel` |
| 12 | 19 | INTC | Intel | Intel careers | `Israel` |
| 13 | 21 | CSCO | Cisco Systems | Phenom / company careers | `location=Israel` |
| 14 | 24 | LRCX | Lam Research | Eightfold / company careers | `query=Israel` |
| 15 | 26 | AMAT | Applied Materials | Workday | `q=Israel` |
| 16 | 30 | PLTR | Palantir Technologies | Lever | `location=Tel Aviv, Israel` |
| 17 | 31 | NFLX | Netflix | Netflix careers | `query=Israel` |
| 18 | 39 | IBM | IBM | IBM careers | `q=Israel` |
| 19 | 41 | DELL | Dell Technologies | Oracle Cloud / company careers | `location=Israel` |
| 20 | 42 | TXN | Texas Instruments | Oracle Cloud Recruiting | `location=Israel` |
| 21 | 44 | KLAC | KLA | Workday | `q=Israel` |
| 22 | 46 | SNDK | SanDisk | Company careers | `keywords=Israel` |
| 23 | 47 | QCOM | Qualcomm | Eightfold / company careers | `query=Israel` |
| 24 | 49 | PANW | Palo Alto Networks | SmartRecruiters | `search=Israel` |
| 25 | 53 | ANET | Arista Networks | Company careers | `search=Israel` |
| 26 | 55 | STX | Seagate | Phenom / company careers | `location=Israel` |
| 27 | 56 | ADI | Analog Devices | Workday | `q=Israel` |
| 28 | 58 | APP | AppLovin | Company careers | `Israel` |
| 29 | 61 | CRWD | CrowdStrike | Workday | `q=Israel` |
| 30 | 62 | WDC | Western Digital | SmartRecruiters | `search=Israel` |
| 31 | 64 | APH | Amphenol | Company / business-unit boards | `country=Israel` |
| 32 | 69 | GLW | Corning | SAP SuccessFactors / company careers | `locationsearch=Israel` |
| 33 | 73 | CRM | Salesforce | Salesforce careers | `search=Israel` |
| 34 | 82 | UBER | Uber | Uber careers | `location=Israel` |
| 35 | 88 | NOW | ServiceNow | ServiceNow careers | `location=Israel` |
| 36 | 91 | VRT | Vertiv | Workday | `q=Israel` |
| 37 | 99 | CDNS | Cadence Design Systems | Workday | `q=Israel` |
| 38 | 102 | ACN | Accenture | Accenture careers | `jk=Israel` |
| 39 | 106 | FTNT | Fortinet | Company careers | `location=Israel` |
| 40 | 110 | ADBE | Adobe | Phenom / company careers | `keywords=Israel` |
| 41 | 111 | EQIX | Equinix | Company careers | `keyword=Israel` |
| 42 | 119 | SNPS | Synopsys | Phenom / company careers | `location=Israel` |
| 43 | 121 | DDOG | Datadog | Company careers | `location=Israel` |
| 44 | 126 | ADP | Automatic Data Processing | ADP careers | `location=Israel` |
| 45 | 131 | CIEN | Ciena | Workday | `q=Israel` |
| 46 | 133 | INTU | Intuit | Phenom / company careers | `location=Israel` |
| 47 | 144 | COHR | Coherent | Workday / company careers | `Israel` |
| 48 | 145 | NXPI | NXP Semiconductors | Workday | `q=Israel` |
| 49 | 148 | LITE | Lumentum Holdings | Workday | `q=Israel` |
| 50 | 149 | MPWR | Monolithic Power Systems | Company careers | `Location: Israel` |

## Notes

- The CSV contains the direct Israel search URL, shell HTTP check result, and priority note for every company.
- `Workday`, `Lever`, and `SmartRecruiters` are the most promising reusable scraper patterns from this list.
- Some company pages returned `403`, `404`, `406`, `500`, or JavaScript shells from direct shell requests. Those are not automatic failures; they mean the browser route or backing API needs discovery before implementation.
- For the next implementation round, start with Workday, Lever, and SmartRecruiters boards before the heavier Oracle Cloud, Meta, Tesla, and fully custom portals.
