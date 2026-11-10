import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time

from pydantic import ValidationError

from ..config import Settings
from ..http import ProviderError, SafeHTTP
from ..models import Place


class PlaceTokens:
    """Signed self-contained places avoid a server-side search/session store."""

    def __init__(self, secret: str):
        self.key = (secret or secrets.token_urlsafe(48)).encode()

    def encode(self, place: Place) -> str:
        data = place.model_dump(mode="json", exclude={"city_id"})
        raw = json.dumps(
            {"place": data, "expires": int(time.time()) + 7200}, separators=(",", ":")
        ).encode()
        payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        signature = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def decode(self, token: str) -> Place:
        try:
            if len(token) > 6000:
                raise ValueError
            payload, signature = token.split(".")
            expected = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            if data["expires"] < time.time():
                raise ValueError
            return Place(**data["place"], city_id=token)
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise ProviderError(
                "invalid_city", "Place selection expired or is invalid; search for the city again"
            ) from exc


class SearchLimiter:
    """Only timing state, never queries, IP addresses or results."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.next_call = 0.0

    async def acquire(self):
        # Reject excess callers instead of building an unbounded provider queue.
        async with self.lock:
            now = time.monotonic()
            if now < self.next_call:
                raise ProviderError(
                    "search_rate_limit", "Recherche trop rapide. Réessayez dans une seconde."
                )
            self.next_call = now + 1.05


async def search_places(
    query: str, http: SafeHTTP, settings: Settings, tokens: PlaceTokens
) -> list[Place]:
    places = []
    if settings.geocoder == "geonames":
        if not settings.geonames_username:
            raise ProviderError(
                "missing_geocoder_credentials",
                "GEONAMES_USERNAME must be configured by the operator",
            )
        data = await http.json(
            "https://secure.geonames.org/searchJSON",
            params={
                "q": query,
                "featureClass": "P",
                "maxRows": 8,
                "style": "FULL",
                "lang": "fr",
                "username": settings.geonames_username,
            },
            max_bytes=1_000_000,
        )
        if "status" in data or not isinstance(data.get("geonames"), list):
            raise ProviderError(
                "geocoder_error", "GeoNames returned an account, quota or format error"
            )
        for item in data["geonames"]:
            places.append(
                Place(
                    provider="geonames",
                    provider_id=str(item["geonameId"]),
                    label=item.get("name", item["toponymName"]),
                    country=item.get("countryName", item["countryCode"]),
                    country_code=item["countryCode"],
                    longitude=float(item["lng"]),
                    latitude=float(item["lat"]),
                    admin_labels=[item[k] for k in ("adminName1", "adminName2") if item.get(k)],
                    admin_codes={k: item[k] for k in ("adminCode1", "adminCode2") if item.get(k)},
                    alternate_names=[
                        a["name"] for a in item.get("alternateNames", [])[:20] if "name" in a
                    ],
                    source_url=f"https://www.geonames.org/{item['geonameId']}/",
                )
            )
    else:
        data = await http.json(
            "https://photon.komoot.io/api/",
            params=[
                ("q", query),
                ("limit", "8"),
                ("lang", "fr"),
                ("osm_tag", "place:city"),
                ("osm_tag", "place:town"),
                ("osm_tag", "place:village"),
            ],
            max_bytes=1_000_000,
        )
        if not isinstance(data.get("features"), list):
            raise ProviderError("geocoder_error", "Photon returned an unexpected result format")
        seen = set()
        for feature in data["features"]:
            p, g = feature.get("properties", {}), feature.get("geometry", {})
            if (
                not p.get("countrycode")
                or g.get("type") != "Point"
                or p.get("osm_value") not in ("city", "town", "village")
            ):
                continue
            key = f"{p['osm_type']}:{p['osm_id']}"
            if key in seen:
                continue
            seen.add(key)
            kind = {"N": "node", "W": "way", "R": "relation"}.get(p["osm_type"])
            if kind is None:
                continue
            places.append(
                Place(
                    provider="photon",
                    provider_id=key,
                    label=p["name"],
                    country=p.get("country", p["countrycode"]),
                    country_code=p["countrycode"].upper(),
                    longitude=g["coordinates"][0],
                    latitude=g["coordinates"][1],
                    admin_labels=[p[k] for k in ("state", "county") if p.get(k)],
                    alternate_names=[],
                    source_url=f"https://www.openstreetmap.org/{kind}/{p['osm_id']}",
                )
            )
    for place in places:
        place.city_id = tokens.encode(place)
    return places
