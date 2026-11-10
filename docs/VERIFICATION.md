# Verification record

Executed on 7 November 2026 (Europe/Paris), using Python 3.12.10 and Node 24.19.0 on Windows.

## Official live integration

- An activated developer Census key was accepted by the 2024 ACS 5-year data API.
- The live NYC pipeline fetched all five county B19001 tables including estimates and margins of error, discovered the 2024 TIGERweb layer IDs from service metadata, paginated real tract boundaries, checked geometry/vintage/overlap/extent and completed the exact GEOID join.
- The explicit live pytest test passed with every map area matched and all five indices available: D, isolation, exposure, multigroup H and PySAL rank-order H.
- Real Photon queries resolved New York, Vienna and Casablanca, with same-name results in different countries. The browser verified the Austrian and Moroccan selections and their correct locations.
- Statistics Austria and HCP source pages were reached. Both cities honestly returned `insufficient_data`; reachable metadata was not promoted to a valid income-distribution dataset.
- Fetched records, income tables and generated GeoJSON were not written to a data file or bundled into this repository. This report records verification outcomes, not a stored analysis result.

## Automated checks

- Backend: 110 deterministic/mocked tests plus two explicitly enabled live Census/TIGERweb integration tests: 112 passed.
- Statistical cases cover closed-form examples, scaling, permutations, degenerate inputs, aggregation and independent PySAL D/H comparisons. Rank-order H is verified against even-distribution and full-separation closed forms. Regression tests also verify independence from the caller’s NumPy error mode; the adapter isolates PySAL’s thread-local arithmetic policy and validates the entire fitted profile.
- Security/connector cases cover blocked hosts and private DNS, redirects, download caps, retry delays, timeouts, source schema changes, suppression, missing margins, duplicate IDs, pagination, geography mismatch and overlapping polygons.
- API lifecycle cases verify body and response limits, capacity rejection, provider sibling cancellation, request cancellation cleanup, terminal NDJSON status and an overall deadline.
- AI discovery is exercised with mocked Responses API outputs: domain filters, `store:false`, bounded tools/candidates, schema rejection and independent verification. An AI-suggested source never grants data-processing/export permission.
- Frontend: twelve unit tests covering honest empty states, country disambiguation, missing metrics, streamed chunk boundaries, interruptions, invalid events and CSV formula safety.
- TypeScript, ESLint, Prettier, Ruff formatting/lint and the optimized Next.js production build all passed. The production build emits the MapLibre ESM worker explicitly.
- `pip check` found no broken dependency requirements. The current Starlette test client emits one deprecation warning about its HTTPX adapter; test assertions pass. This is test tooling, not a runtime data failure.

## Browser checks actually performed

- NYC real choropleth visibly rendered in MapLibre, with valid income shares, coverage and all five metric cards.
- Switching the indicator and selecting a tract with the keyboard-accessible dropdown worked. A real zero-household tract showed no share and retained its published margin of error.
- Export controls enabled for the completed NYC analysis and disabled after changing to an unsupported city. No live dataset download was retained during QA.
- Switching NYC → Vienna → Casablanca cleared previous overlays and metrics; the map centered on the new city while source verification ran.
- Canceling a new NYC run produced the explicit canceled state.
- Desktop (1440 × 1000) and mobile (390 × 844) layouts were inspected. Mobile DOM width did not exceed the viewport. Map attribution remained visible.
- Browser testing caught MapLibre 6's required explicit worker URL; this was corrected and the actual choropleth was rechecked.

## Boundaries of verification

- Docker is not installed on this workstation. Dockerfiles/Compose are supplied, but no container image build or `docker compose up` was executed here. The same service entry points were run directly.
- No OpenAI API key was configured, so the optional AI adapter was not called against a live paid API. Its protocol, error behavior and verification safeguards were tested with isolated synthetic fixtures.
- No GeoNames username was supplied. GeoNames parsing/disambiguation was tested using synthetic protocol fixtures; live worldwide search used Photon.
- No external deployment or commercial tile/geocoder account was created. Public Photon/OSM development access is not a production scaling guarantee.
- NYC and San Francisco have passed measured live analysis. The automatic ACS builder can activate for additional contiguous-US municipalities only after exact official city/county boundary equality is proved. Other data families receive inspected metadata and proposals, not automatic scientific approval.
- The application reports input margins of error, but does not infer survey confidence intervals for derived indices, compare currencies through FX, estimate household incomes or silently crosswalk boundary vintages.

## Connector-agent extension, 7 November 2026

- The user-selected OpenRouter model `xingchen-agi/xing4.0-29b-a4b:free` accepted the supplied credential and returned valid JSON in a live call. Two initial calls returned HTTP 429; later calls succeeded. No paid-model fallback was configured or used.
- A live model call on official TIGERweb metadata produced a schema-valid connector proposal. Independent checks blocked activation because compatible income distributions were absent. A field-category error in that proposal motivated an additional housing-unit/population rejection check. This is evidence that independent validation remains necessary, not a claim that model proposals are universally correct.
- San Francisco was resolved through the worldwide geocoder; official municipal and county polygons were exactly equal. The generated ACS configuration retrieved and validated the full official distribution/polygons and returned all five metrics. NYC also passed its live regression test.
- Twenty-four new deterministic tests cover boundary/identity mismatches, typed recipes, invented fields, housing-unit confusion, a bounded model repair, endpoint policy, paid-fallback rejection, redacted HTTP 429 and metadata-only ArcGIS/CKAN/Socrata inspection.
- The UK CKAN endpoint responded successfully to a live income catalog query. Austria catalog probes returned 404 and Morocco 403; neither endpoint was silently treated as usable. Only the verified UK catalog search endpoint was enabled.
- The final checks passed: 112 Python tests, 12 frontend tests, Ruff, TypeScript, ESLint, formatting and the optimized production build. The same pre-existing TestClient deprecation warning remains.

- The updated production application was restarted and its proxied health endpoint confirmed the exact requested OpenRouter model with the free-only guard enabled. Browser QA then selected San Francisco, observed the automatic connector proof, the real choropleth and all five metric cards. No browser console errors were observed. The expanded source-check details rendered correctly.
- The Windows launcher was corrected to use ASCII console output so it also runs under Windows PowerShell 5 without a UTF-8 parsing error. The corrected script launched both services successfully.
