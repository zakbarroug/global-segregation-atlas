# Metadata only. No downloaded data, city observations or computed results.
CATALOG = [
    {
        "id": "us_acs_b19001",
        "countries": ["US"],
        "coverage": "New York City; other contiguous-US municipalities when an exact live city/county boundary equivalence is verified",
        "publisher": "U.S. Census Bureau",
        "url": "https://api.census.gov/data.html",
        "adapter": "CensusNYCConnector",
        "status": "measured_when_validated",
    },
    {
        "id": "at_statistics",
        "countries": ["AT"],
        "coverage": "Austria: source discovery only; no reviewed household-income distribution adapter",
        "publisher": "Statistics Austria",
        "url": "https://www.statistik.at/en/statistics/population-and-society/income-and-living-conditions",
        "adapter": None,
        "status": "metadata_only",
    },
    {
        "id": "ma_hcp",
        "countries": ["MA"],
        "coverage": "Morocco: source discovery only; no reviewed household-income distribution adapter",
        "publisher": "Haut-Commissariat au Plan",
        "url": "https://www.hcp.ma/",
        "adapter": None,
        "status": "metadata_only",
    },
    {
        "id": "uk_ckan",
        "countries": ["GB"],
        "coverage": "United Kingdom: live catalog search and connector proposals; no automatic measurement permission",
        "publisher": "data.gov.uk",
        "url": "https://ckan.publishing.service.gov.uk/",
        "adapter": None,
        "status": "metadata_only",
    },
]

OFFICIAL_DOMAINS = {
    "AT": ["www.statistik.at", "data.statistik.gv.at", "www.wien.gv.at", "www.data.gv.at"],
    "MA": ["www.hcp.ma", "data.gov.ma"],
    "US": ["www.census.gov", "api.census.gov", "tigerweb.geo.census.gov", "data.sfgov.org"],
    "GB": ["www.ons.gov.uk", "api.ons.gov.uk", "ckan.publishing.service.gov.uk"],
    "FR": ["www.insee.fr", "api.insee.fr"],
    "CA": ["www.statcan.gc.ca", "www150.statcan.gc.ca"],
    "AU": ["www.abs.gov.au"],
    "BR": ["www.ibge.gov.br", "servicodados.ibge.gov.br"],
}
