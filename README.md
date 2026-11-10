# Global Segregation Atlas

A working two-service, on-demand residential household-income segregation explorer. Next.js + MapLibre front end; Python FastAPI + deterministic statistics back end. French interface, worldwide place search, streamed progress and browser-generated GeoJSON/CSV exports.

**Measured connector:** New York City, using live U.S. Census ACS 5-year B19001 household-income counts and matching TIGERweb ACS-vintage census tracts across state 36 / counties 005, 047, 061, 081, 085. No extracts are shipped. All five counties must pass the exact-join checks.

**Automatic extension:** San Francisco now completes the same measured pipeline. Other contiguous-US cities can use it when live official municipal and county boundaries are exactly equal, their identities match and all income/geography checks pass. This proof is discovered per request; there is no hardcoded city dataset or approximate county substitution.

**Worldwide search does not mean worldwide measurement.** Vienna, Casablanca and other cities open immediately on the map and return an explicit `insufficient_data` outcome unless a reviewed compatible connector exists. Neither median income nor an AI prediction is substituted for household distributions.

## Start with Docker

Requires Docker Engine + Compose, internet access, and an activated [Census API key](https://api.census.gov/data/key_signup.html). Developer credentials are server-side; end users have no configuration.

```sh
cp .env.example .env
# Edit CENSUS_API_KEY in .env. Activate it using the Census confirmation email.
docker compose up --build
```

Open **http://localhost:3000**. API documentation: **http://localhost:8000/docs**. Health: **http://localhost:8000/health**. The compose file has only web and API services, read-only container filesystems, RAM-backed `/tmp`, memory limits and no data volumes. Ports bind to loopback; place a TLS ingress in front for a remote deployment.

If an existing `.env` already contains your activated key, do not overwrite it. The supplied development checkout keeps it locally, ignored; distributable archives exclude it.

## Start without Docker

Python 3.12+ and Node 22.12+ (Node 24 recommended):

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\python.exe -m pip install -c apps/api/requirements.lock -e "./apps/api[rank,test]"
.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Another terminal:
cd apps/web
npm ci
npm run dev
```

On Linux/macOS replace `.venv\Scripts\python.exe` with `.venv/bin/python`. Run the API from the repository root. Root `.env` is loaded by the Python settings. The frontend has defaults for localhost; for custom settings provide `API_INTERNAL_URL` and `MAP_STYLE_URL` in the web server environment (Compose passes them automatically).

For a local production build, run `npm run build` then `npm start` in `apps/web`. The next server proxies only `/api/places/search`, `/api/analysis`, `/api/providers` and `/api/health` to FastAPI. Keys never enter frontend bundles.

On Windows, after installing dependencies and building, `powershell -File scripts/start-local.ps1` starts both servers in hidden processes and prints their PIDs and a precise stop command. Use `-Development` for a development server. It refuses to replace an existing listener. No server logs are saved to disk.

## Configuration and provider terms

- `CENSUS_API_KEY`: required for Census **data queries**; Census now requires a key. Metadata and TIGERweb are public. A configured key may still need activation; an HTTP response is not proof of valid income data.
- `GEOCODER=photon`: modest local development uses [Photon's public demo](https://github.com/komoot/photon#demo-server), with 650 ms browser debounce and a global one-search-per-second rate cap in this single API process. This is not unlimited commercial infrastructure or a guaranteed service. Excess searches return 429; no query/result cache is maintained.
- `GEOCODER=geonames`, `GEONAMES_USERNAME`: use a developer GeoNames account for production, with a quota plan appropriate to traffic. See [GeoNames services](https://www.geonames.org/export/web-services.html). Production validation refuses the public Photon demo. Use one API worker or enforce provider quotas across replicas in your ingress; do not add a Redis cache to this application.
- `APP_ENV=production` additionally requires `PLACE_TOKEN_SECRET` of at least 32 random characters shared across workers. Place selections are signed, expire after two hours and do not require a server-side session store. Development generates a process secret if unset; restarting invalidates earlier selections.
- `MAP_STYLE_URL`: a browser-visible MapLibre style URL for a contracted provider. Limit any public tile token by origin. When blank, modest interactive development uses [OSM raster tiles under their usage policy](https://operations.osmfoundation.org/policies/tiles/), with visible attribution, normal browser HTTP caching and a Referer. No tile proxy, bulk download, offline mode or prefetch is implemented. Set a production tile provider before public deployment.
- `ACS_YEAR=2024`: default API vintage. The client offers reviewed ACS-era vintages; every request rechecks the actual official schema and geometry service. No cross-vintage fallback or guessed crosswalk.
- `ENABLE_AI_DISCOVERY=true`, `OPENAI_API_KEY`, `OPENAI_DISCOVERY_MODEL`: opt-in AI source-identification through the [OpenAI Responses web-search tool](https://developers.openai.com/api/docs/guides/tools-web-search). At most two search tool calls and five candidate URLs, restricted to reviewed national-statistics domains. `store:false`; only city labels and source requirements are transmitted. Independent deterministic verification checks host policy and HTTP responses. Source reachability does **not** establish a reusable dataset, compatible geography or approved income parser. No generated code runs, and no model-generated numbers enter the statistics engine. Discovery is optional and off by default.
- Other `.env.example` settings bound concurrent analyses, provider deadlines, download budgets, response size and area count. Live NYC works under the provided defaults.

The optional planner also accepts an OpenAI-compatible hosted/local API: `AI_PROVIDER=compatible`, `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`. `AI_ALLOW_LOCAL=true` explicitly allows a numeric loopback inference endpoint. For OpenRouter, `AI_FREE_ONLY=true` prevents paid model IDs and fallback/tool/plugin parameters; the configured model is preserved. Python searches reviewed catalogs and inspects their metadata, so the model does not need built-in search. See [AI-CONNECTORS.md](docs/AI-CONNECTORS.md) for the workflow, model requirements, operator probe and precise limitations. This includes the user-selected `xingchen-agi/xing4.0-29b-a4b:free` integration.

## Scientific methods

Income is **household money income before taxes**, annual income in the past 12 months, non-equivalized, reported in the final ACS vintage's inflation-adjusted USD. ACS 2024 covers 2020–2024; it is not a single-year census. B19001 has 16 ordered brackets including open-ended tails. Counts are estimates of households, not people or individual wages. Each input includes its published 90% margin of error where available; suppressed margins remain unavailable.

Fixed target groups: **low < $35,000**, B19001 cells 002–007; **high ≥ $100,000**, cells 014–017. These are not bottom/top quartiles. Intermediate incomes are excluded from D's two groups but included in isolation/exposure area denominators and both information-theory indices.

| Index | Implementation and meaning |
| --- | --- |
| Dissimilarity D | `0.5 Σ |low_i/LOW - high_i/HIGH|`; relative spatial separation of the two specified groups. |
| Low-income isolation | `Σ (low_i/LOW) (low_i/households_i)`; composition-dependent local low-income share experienced by a typical low-income household. |
| Exposure to high-income | `Σ (low_i/LOW) (high_i/households_i)`; local high-income share for a typical low-income household, not a causal interaction probability. |
| Multigroup information H | `(E - Σ (t_i/T) E_i)/E`; all 16 categories, natural-log entropy, safe `0 log 0`. Undefined when city entropy is zero. |
| Rank-order information Hᴿ | Published `segregation==2.6.0` `RankOrderInfoTheory`, degree-four polynomial profile. No locally invented approximation. Grouped cutpoints, no within-bin incomes or tail imputation. Empty citywide categories are removed without changing order. At least five distinct cumulative cutpoints are required. Unstable/out-of-range fits return unavailable. |

Reference: [PySAL rank-order information theory](https://pysal.org/segregation/generated/segregation.rankorder.RankOrderInfoTheory.html), [PySAL API](https://pysal.org/segregation/api.html). The rank-order estimate is **not an exact raw-income ranking**. Its fit is not a survey confidence interval. We do not implement an unvalidated population model or claim an `estimated` city status.

Validation rejects missing/suppressed/negative income estimates, inconsistent bracket totals, duplicate GEOIDs, unpopulated or insufficient spatial units, mismatched years, incomplete polygon joins, invalid CRS/topology, overlapping tract interiors and tracts outside the five-county footprint. Zero-household tracts have no choropleth share and contribute zero weight; they remain in coverage. A valid zero exposure is distinguished from an unavailable zero-denominator index. No count is allocated by clipping polygons.

The map colors **local household shares**, never a citywide scalar painted onto every tract. Source polygons are checked before 15 m topology-preserving display simplification in EPSG:5070; tiny visual boundary gaps can appear from per-feature simplification. Metrics use original full counts. MAUP, zoning sensitivity, survey sampling error, upward bias in sample-based segregation and differing income definitions prevent naive international ranking. No PPP/FX conversion or unsupported crosswalk is used.

## Stateless execution and security

No database, Redis, queue, server-side export files, dataset cache, pre-ingestion, source extract, user account, analytics or localStorage/IndexedDB/service worker. Data exist in request-local objects and the currently open browser page. Changing cities aborts the previous fetch and clears its displayed results. NDJSON supplies verified partial results; a missing terminal event is an interruption, not success. Exports are enabled only after a completed measured analysis and permitted reuse.

The application does **not** promise that Census, geocoders, tile providers, optional AI providers or hosting infrastructure keep no logs. Development build caches and normal browser basemap tile caching contain application assets/basemap resources, not persisted analysis datasets. Uvicorn is launched with request access logging disabled; do not add dataset/request body logging in production.

Data-source egress is HTTPS to exact reviewed hosts. No public request accepts an arbitrary fetch URL. URL credentials, nonstandard ports and private/reserved DNS answers are rejected. The optional model endpoint is separately configured by the operator: HTTPS/public DNS for remote providers, or explicitly enabled numeric loopback for local inference. Redirects are refused. Downloads are streamed with per-response and total request byte budgets; decoded output is bounded. Retries are bounded and respect provider Retry-After. AI proposals cannot expand the host allowlist or establish license permission. Apply matching network egress controls at the production host for defense beyond application DNS checks; DNS validation alone is not connection-level IP pinning.

POST bodies are limited to 16 KiB, the API has bounded concurrency, response bytes and overall request deadlines, and no unbounded application task queue. Disconnection cancels async provider operations; a bounded CPU geometry/reference-statistics thread already running may finish before its temporary objects are released. Container memory limits provide a final bound. For public traffic configure ingress request limits and timeouts at least as long as the analysis deadline, disable proxy buffering for NDJSON, and avoid recording URLs with credentials.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Service readiness and configured provider flags, no keys. |
| `GET /places/search?q=...` | Real global place results with countries, administrative labels, provider identities, coordinates and signed selection tokens. |
| `POST /analysis` | `{city_id, requested_year?, indices?}`; NDJSON events: started, geography_ready, source_found, downloading, validating, map_ready, metric_computed, insufficient_data/failed, complete. |
| `GET /providers` | Static connector metadata and scope, no fetched records. |

API types are in `apps/api/src/models.py`; event shapes are mirrored in `apps/web/src/lib/types.ts`. `geography_ready` first identifies the selected gazetteer point, then optionally provides the verified five-county outline. No geocoder bounding box is mislabeled as a municipality.

## Tests and reproducibility

```sh
.venv\Scripts\python.exe -m pytest apps/api/tests -m "not live" -q
.venv\Scripts\python.exe -m ruff check apps/api
.venv\Scripts\python.exe -m ruff format --check apps/api
cd apps/web
npm run test
npm run typecheck
npm run lint
npm run format:check
npm run build
```

The statistical tests include even/separated populations, manually derived D/isolation/exposure/H, scaling/permutation invariance, empty units, zero groups, missing/negative inputs, aggregation effects and comparisons to published PySAL implementations. All protocol/numerical fixtures live **only under tests** and are labeled synthetic. There is no production demo-data switch.

Explicit opt-in live checks (network and activated key required):

```powershell
$env:RUN_LIVE_TESTS='1'
.venv\Scripts\python.exe -m pytest apps/api/tests/test_live.py -q
Remove-Item Env:RUN_LIVE_TESTS
# Or a summary-only live run (does not save fetched data):
.venv\Scripts\python.exe scripts/live_check.py
```

`package-lock.json` locks the frontend. `apps/api/requirements.lock` captures the verified Python environment; installation with `-c` respects compatible platform wheels. See `docs/VERIFICATION.md` for checks actually run and remaining limits.

## Add a country or city

1. Add only source metadata to `discovery/catalog.py` and review the publisher's license, host, schema and rate limits.
2. Implement the typed contract in `connectors/base.py`: support confidence with exact place/extent identification, discover, fetch, normalize, boundaries, extent resolution and geography validation. Register the factory in `connectors/registry.py`. The pipeline ranks compatible connectors without storing their fetched records.
3. Demonstrate consistent **household counts** across exhaustive income categories and small-area polygons of the same vintage. Implement a documented crosswalk only with an explicit validation/uncertainty design.
4. Add adversarial/suppression/pagination tests and an opt-in official live test. Keep unsupported sources `metadata_only`. Define grouping and comparison limits for each connector; the current $35k/$100k grouping is U.S.-specific.

The next useful extension is a reviewed normalization template for an additional national source. Common ArcGIS/CKAN/Socrata metadata inspection and model-generated field proposals now reduce the research/configuration work. Automatic activation currently applies only to the reviewed ACS template with a proven exact city/county footprint; general proposals still require review and full validation.

## Repository

```text
apps/web/src/app/         Next.js app, same-origin streaming API bridge
apps/web/src/components/ Search, MapLibre, metrics, provenance and diagnostics
apps/web/src/lib/         Typed stream client, French/English vocabulary, exports
apps/api/src/connectors/  Official ACS/TIGERweb connector and provider contract
apps/api/src/geography/   Signed places, global search, geometry and join validation
apps/api/src/statistics/  Deterministic indices and PySAL rank-order adapter
apps/api/src/discovery/   Static metadata, optional AI agent, independent verifier
apps/api/tests/           Synthetic-only tests and gated live integration
scripts/                 Development checks and source packaging
docs/                    Method/verification notes
```

Sites hosting supports static/Worker deployments and cannot host this required Python service. This repository is prepared for two-service container hosting; it has not been published to Sites or another external host.
