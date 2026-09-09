# Cloudflare GraphQL API

Flask service that queries the Cloudflare Analytics GraphQL API and exposes endpoints for traffic analysis on your own Cloudflare-proxied site(s).

## Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/` | Lists all available endpoints |
| GET | `/v1/cloudflare/get-top-urls` | Top accessed URLs from individual request records (chunked to avoid the 10k limit) |
| GET | `/v1/cloudflare/get-top-urls-groups` | Top accessed URLs using Cloudflare's pre-aggregated data (faster) |
| GET | `/v1/cloudflare/http-urls` | Paths on `SECONDARY_HOST` that received plain HTTP traffic |
| GET | `/v1/cloudflare/http-urls/verify` | Live-probes HTTP candidates to confirm which paths still respond 200 (not just redirected) |

### Query parameters

**`/get-top-urls` and `/get-top-urls-groups`**

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `top` | int | Yes | Number of top results to return |
| `generate` | int | No | Set to `1` to download as CSV |

**`/http-urls` and `/http-urls/verify`**

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `stream` | string | No | Filter by classifier stream — see [Path classifier](#path-classifier) |
| `start` | string | No | ISO 8601 UTC start datetime (overrides `QUERY_DAYS_BACK` default) |
| `end` | string | No | ISO 8601 UTC end datetime (overrides `QUERY_DAYS_BACK` default) |
| `generate` | int | No | Set to `1` to download as CSV |

## Quick Start

```bash
cp .env.example .env
# Fill in CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, PRIMARY_HOST at minimum

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 app.py
```

The service starts on `http://localhost:5000`.

## Environment Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `CLOUDFLARE_API_TOKEN` | Yes | API token with Analytics:Read on the zone(s) below |
| `CLOUDFLARE_ZONE_ID` | Yes | Primary zone ID — used by `/get-top-urls` endpoints |
| `PRIMARY_HOST` | Yes | Hostname to query, e.g. `www.example.com` |
| `PRIMARY_PATH_PREFIX` | No | Scope `/get-top-urls` queries to paths under this prefix (e.g. `blog` limits to `/blog/*`). Leave blank to match all paths |
| `CLOUDFLARE_ZONE_ID_SECONDARY` | No | Secondary zone ID for `/http-urls` endpoints. Falls back to `CLOUDFLARE_ZONE_ID` if unset — only set separately if that traffic lives on a different zone/account |
| `SECONDARY_HOST` | No | Hostname for `/http-urls` endpoints. Falls back to `PRIMARY_HOST` if unset |
| `CLASSIFIER_RULES_PATH` | No | Path to the classifier rules file (see below). Defaults to the bundled `classifier_rules.example.json` |

See `.env.example` for a template.

## Configuration

`config.py` also exposes these tuning constants:

| Setting | Default | Description |
| ------- | ------- | ----------- |
| `QUERY_DAYS_BACK` | `7` | Rolling lookback window in days |
| `QUERY_HOUR_INTERVAL` | `4` | Hour-slice size per GraphQL request for `/get-top-urls`. Reduce if hitting the 10k record limit |

## Path classifier

`/http-urls` and `/http-urls/verify` tag each path with a named "stream" (e.g. which backend or team owns it) so results can be filtered with `?stream=`. Rules aren't hardcoded — they're loaded from a JSON file at startup (`CLASSIFIER_RULES_PATH`, default `classifier_rules.example.json`):

```json
{
  "streams": [
    { "name": "api", "include": ["^/api(?:/|$)"] },
    { "name": "static", "include": ["\\.(?:js|css|png)$"] },
    { "name": "app", "include": ["^/.+"], "exclude": ["^/robots\\.txt$"] }
  ],
  "default": "unmatched"
}
```

Streams are evaluated in order; the first one whose `include` pattern matches the path (and none of its `exclude` patterns do) wins. Anything matching no stream falls back to `default`.

Copy the example, adapt the patterns to your own routing, and point `CLASSIFIER_RULES_PATH` at it (e.g. `classifier_rules.json` — already gitignored, same pattern as `.env`).

## Project Structure

```
app.py              - Thin entry point: creates Flask app, registers routes Blueprint, starts server
requirements.txt    - Python dependencies
.env.example        - Environment variable template
classifier_rules.example.json - Example path-classifier ruleset
lib/
  config.py         - Cloudflare credentials and query tuning constants
  cloudflare.py     - Cloudflare Analytics GraphQL API client (three query functions)
  pipeline.py       - Data processing: path cleaning, aggregation, CSV export, time ranges
  classifier.py     - Config-driven path classifier (see classifier_rules.example.json)
  logger.py         - HTTP error log manager (writes to error_400.log / error_500.log)
  routes.py         - Flask Blueprint with all route handlers
```

## Notes

- `/get-top-urls` uses `httpRequestsAdaptive` (individual records, capped at 10k per request). The date range is split into `QUERY_HOUR_INTERVAL`-sized windows to stay under the limit.
- `/get-top-urls-groups` uses `httpRequestsAdaptiveGroups` (Cloudflare aggregates server-side), so a single request covers the full window with no chunking needed.
- `/http-urls` trusts Cloudflare's logged data. `/http-urls/verify` confirms live state by probing each candidate over plain HTTP with `allow_redirects=False` using 20 concurrent workers.
- Country/language prefixes (`/gb/`, `/us/`, etc.) are stripped before aggregation so regional variants of the same page are counted together.
