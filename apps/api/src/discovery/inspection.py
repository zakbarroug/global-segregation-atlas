"""Bounded metadata-only adapters for common public-data protocols."""

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from ..http import ProviderError, validate_url


def short(value, maximum=1000):
    return re.sub(r"<[^>]*>", " ", str(value or ""))[:maximum]


class PageMetadata(HTMLParser):
    """Only title, description and API links; no tables, scripts or observations."""

    def __init__(self, base):
        super().__init__()
        self.base, self.in_title = base, False
        self.title, self.description, self.resources = "", "", []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("name", "").lower() == "description":
            self.description = short(attrs.get("content"))
        if tag == "a" and len(self.resources) < 8:
            url = urljoin(self.base, attrs.get("href") or "")
            if re.search(
                r"/(?:MapServer|FeatureServer)/\d+(?:\?|$)|/api/3/action/package_show\?|/api/views/[a-z0-9-]+\.json$",
                url,
            ):
                try:
                    validate_url(url)
                    self.resources.append(
                        {"url": url, "format": "API", "name": "Linked official API metadata"}
                    )
                except ProviderError:
                    pass

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title = short(self.title + data, 300)


async def inspect_source(url, http):
    validate_url(url)
    parsed = urlsplit(url)
    # Only exact known read-only resource endpoints, with generated parameters.
    clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    report = {
        "url": clean,
        "format": "unsupported",
        "fields": [],
        "resources": [],
        "description": "",
        "license_evidence": "",
        "status": "unsupported",
    }
    if re.search(r"/(?:MapServer|FeatureServer)/\d+$", parsed.path.rstrip("/")):
        raw = await http.json(clean, params={"f": "json"}, max_bytes=1_000_000)
        report.update(
            format="arcgis",
            status="inspected",
            title=short(raw.get("name"), 300),
            description=short(raw.get("description")),
            geometry_type=short(raw.get("geometryType"), 80),
            pagination=bool(raw.get("advancedQueryCapabilities", {}).get("supportsPagination")),
            fields=[
                {
                    "name": short(f.get("name"), 120),
                    "label": short(f.get("alias"), 300),
                    "type": short(f.get("type"), 80),
                }
                for f in raw.get("fields", [])[:100]
            ],
            license_evidence=short(raw.get("copyrightText")),
        )
    elif parsed.path.endswith("/api/3/action/package_show"):
        dataset_id = parse_qs(parsed.query).get("id", [""])[0]
        if not re.fullmatch(r"[\w-]{1,150}", dataset_id):
            raise ProviderError(
                "catalog_identifier", "Identifiant de jeu de données CKAN invalide."
            )
        raw = await http.json(clean, params={"id": dataset_id}, max_bytes=1_000_000)
        if raw.get("success") is not True or not isinstance(raw.get("result"), dict):
            raise ProviderError(
                "catalog_schema", "Le catalogue n’a pas renvoyé de métadonnées valides."
            )
        dataset = raw["result"]
        report.update(
            url=clean + "?id=" + dataset_id,
            format="ckan",
            status="inspected",
            title=short(dataset.get("title"), 300),
            description=short(dataset.get("notes")),
            license_evidence=short(dataset.get("license_id")),
            resources=[
                {
                    "url": short(r.get("url"), 2000),
                    "format": short(r.get("format"), 80),
                    "name": short(r.get("name"), 200),
                }
                for r in dataset.get("resources", [])[:8]
            ],
        )
    elif re.search(r"/api/views/[a-z0-9]{4}-[a-z0-9]{4}\.json$", parsed.path):
        raw = await http.json(clean, max_bytes=1_000_000)
        report.update(
            format="socrata",
            status="inspected",
            title=short(raw.get("name"), 300),
            description=short(raw.get("description")),
            license_evidence=short(raw.get("licenseId")),
            fields=[
                {
                    "name": short(f.get("fieldName"), 120),
                    "label": short(f.get("name"), 300),
                    "type": short(f.get("dataTypeName"), 80),
                }
                for f in raw.get("columns", [])[:100]
            ],
        )
    else:
        body, content_type = await http.fetch(clean, max_bytes=1_000_000)
        if "html" in content_type:
            parser = PageMetadata(clean)
            parser.feed(body.decode("utf-8", errors="replace"))
            report.update(
                title=parser.title,
                description=parser.description,
                resources=parser.resources,
                status="metadata_only",
            )
    return report


async def search_catalog(place, http):
    # Reviewed portal endpoint, metadata only. More national catalogs can be added
    # here without changing the agent or persisting any observation.
    if place.country_code != "GB":
        return []
    base = "https://ckan.publishing.service.gov.uk/api/3/action"
    raw = await http.json(
        base + "/package_search",
        params={"q": f'"{place.label}" income', "rows": 3},
        max_bytes=1_000_000,
    )
    if raw.get("success") is not True:
        raise ProviderError("catalog_search", "La recherche du catalogue officiel a échoué.")
    results = raw.get("result", {}).get("results", [])
    proposals = []
    for record in results[:3]:
        identifier = record.get("id", "")
        if re.fullmatch(r"[\w-]{1,150}", identifier):
            proposals.append(
                {
                    "url": base + "/package_show?id=" + identifier,
                    "title": short(record.get("title"), 300),
                    "publisher": "data.gov.uk",
                    "reason": "Résultat du catalogue officiel ; compatibilité à vérifier",
                    "license_url": None,
                }
            )
    return proposals
