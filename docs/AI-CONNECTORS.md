# Source discovery and connector configuration

## Implemented workflow

1. Existing reviewed connectors run first, without model calls.
2. For an unsupported US city, the builder discovers the municipal and county layers from live TIGERweb metadata. It verifies the selected point, official name, state/GEOIDs, year and **exact topological equality** of the municipal and county boundaries. Only an exact match instantiates the reviewed ACS B19001 template. San Francisco passes this path; a city inside a larger county does not.
3. For other sources, deterministic adapters inspect ArcGIS layer schemas, CKAN package metadata, Socrata column metadata and official page titles/descriptions/API links. The UK CKAN catalog has a live search adapter. Other national catalogs need a reviewed endpoint; this is not an unrestricted global web crawler.
4. An optional model receives a bounded metadata description and produces a typed JSON connector proposal. It can propose observed field bindings and identify missing evidence. Python validates the URL, template, field names and obvious category errors; a malformed proposal can receive one repair attempt.
5. A general proposal remains `requires_review`, `blocked` or `rejected`. It cannot grant itself a license, invent income observations, change the host policy or execute code. Only the reviewed Census template currently activates automatically following its geography proof. The complete source data and polygons then pass the existing full validation before any map/indices are produced.

There is **no arbitrary code-generation/execution sandbox** in the public request path. A constrained JSON interpreter is used. Adding a new data family still requires a reviewed normalization/measurement contract; the model helps prepare that work. It does not prove scientific validity from field names alone.

## Model provider configuration

The existing OpenAI Responses web-search adapter remains optional. For a compatible hosted or local model:

```dotenv
ENABLE_AI_DISCOVERY=true
AI_PROVIDER=compatible
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=xingchen-agi/xing4.0-29b-a4b:free
AI_API_KEY=operator_supplied_key
AI_FREE_ONLY=true
```

For OpenRouter, the free-only guard rejects model identifiers without `:free` (except `openrouter/free`), model fallback lists and external paid-tool/plugin parameters. The user-selected model is preserved. HTTP 429 is shown as a provider limit; no paid fallback is attempted. Free availability is not guaranteed. [Official free-routing documentation](https://openrouter.ai/docs/guides/routing/model-variants/free).

For a local compatible server, configure its numeric loopback URL ending in `/v1`, its installed model ID, and `AI_ALLOW_LOCAL=true`. No API key is needed if the local server does not require one. This exception applies only to the explicitly configured model endpoint, never to discovered sources. Remote model endpoints require HTTPS and public DNS; redirects are refused. Compatible providers must support `/chat/completions` and `response_format: {"type":"json_object"}`.

The model does not require built-in web search or tool calling: Python controls the source tools. Compatible-mode discovery is limited to reviewed catalog endpoints and links found in their metadata; supplying a model does not create an unrestricted search engine. A separate search adapter could later expand this.

At most five source inspections and one model proposal plus one repair are allowed per analysis. Metadata only is sent to the model; source records, household tables, secrets and geometries are excluded. Source providers/model providers can have their own logging policies. There is no application dataset/result persistence.

## Operator probe

```powershell
.\.venv\Scripts\python.exe scripts/inspect_source.py 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/8' --city 'San Francisco' --country US --ai
```

This example URL was verified against live layer metadata; the runtime builder discovers IDs instead of relying on that example. The tool emits metadata/proposals to the terminal, never downloads full observations or saves city results. Omit `--ai` to inspect without a model. API errors are redacted.

## Model-selection requirements

- API callable from Python, preferably compatible with Chat Completions.
- Reliable instruction following and JSON objects with lists/null values.
- French/English comprehension; ability to reason over column names and descriptions.
- At least 16k tokens of context and about 2.5k output tokens for this bounded workflow.
- Ability to revise JSON once using concise validation errors.
- Clear quotas, availability, privacy terms and operator-controlled spending limits.

Statistics, geometry and source authorization remain deterministic. GPU requirements depend on the local model chosen; no local runtime/model is installed by this project.
