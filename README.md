# Cloudflare GraphQL API

Flask service that queries the Cloudflare Analytics GraphQL API and exposes endpoints for traffic analysis across Cambridge University Press & Assessment web properties.

## Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/` | Lists all available endpoints |
| GET | `/v1/cloudflare/get-top-urls` | Top accessed URLs from individual request records (chunked to avoid the 10k limit) |
| GET | `/v1/cloudflare/get-top-urls-groups` | Top accessed URLs using Cloudflare's pre-aggregated data (faster) |
| GET | `/v1/cloudflare/http-urls` | `cambridge.org` paths that received plain HTTP traffic |
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
| `stream` | string | No | Filter by origin stream: `drupal`, `c5`, or `unmatched` |
| `start` | string | No | ISO 8601 UTC start datetime (overrides `QUERY_DAYS_BACK` default) |
| `end` | string | No | ISO 8601 UTC end datetime (overrides `QUERY_DAYS_BACK` default) |
| `generate` | int | No | Set to `1` to download as CSV |

## Quick Start

```bash
cp .env.example .env
# Fill in CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_ZONE_ID_ORG

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 app.py
```

The service starts on `http://localhost:5000`.

## Environment Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `CLOUDFLARE_API_TOKEN` | Yes | API token with Analytics:Read on both zones |
| `CLOUDFLARE_ZONE_ID` | Yes | Zone ID for `cambridge.edu.au` (used by `/get-top-urls` endpoints) |
| `CLOUDFLARE_ZONE_ID_ORG` | Yes | Zone ID for `www.cambridge.org` (used by `/http-urls` endpoints — different CF account) |

See `.env.example` for a template.

## Configuration

`config.py` exposes additional settings:

| Setting | Default | Description |
| ------- | ------- | ----------- |
| `QUERY_DAYS_BACK` | `7` | Rolling lookback window in days |
| `QUERY_HOUR_INTERVAL` | `4` | Hour-slice size per GraphQL request for `/get-top-urls`. Reduce if hitting the 10k record limit. |
| `HOST` | `www.cambridge.edu.au` | Hostname filter for `/get-top-urls` |
| `PATH` | `education` | Path prefix filter for `/get-top-urls` |
| `CAMBRIDGE_ORG_HOST` | `www.cambridge.org` | Hostname for `/http-urls` |

## Project Structure

```
app.py            - Flask app: GraphQL query functions + route handlers
config.py         - Configuration (env vars + query tuning constants)
utils.py          - Data processing: path cleaning, aggregation, CSV export, time ranges
origin_rules.py   - Path classifier: maps cambridge.org paths to drupal / c5 / unmatched streams
logger.py         - HTTP error log manager (writes to error_400.log / error_500.log)
requirements.txt  - Python dependencies
.env.example      - Environment variable template
```

## Notes

- `/get-top-urls` uses `httpRequestsAdaptive` (individual records, capped at 10k per request). The date range is split into `QUERY_HOUR_INTERVAL`-sized windows to stay under the limit.
- `/get-top-urls-groups` uses `httpRequestsAdaptiveGroups` (Cloudflare aggregates server-side), so a single request covers the full window with no chunking needed.
- `/http-urls` trusts Cloudflare's logged data. `/http-urls/verify` confirms live state by probing each candidate over plain HTTP with `allow_redirects=False` using 20 concurrent workers.
- Country/language prefixes (`/gb/`, `/us/`, etc.) are stripped before aggregation so regional variants of the same page are counted together.
- The `stream` classifier in `origin_rules.py` mirrors the priority order of the live Cloudflare origin rules.
