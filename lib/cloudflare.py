"""
lib/cloudflare.py — Cloudflare Analytics GraphQL API client.

Each function builds and sends one query to the Cloudflare GraphQL Analytics
API and returns the raw JSON response. No data transformation happens here —
that lives in lib/pipeline.py.

Two dataset types are used:
  httpRequestsAdaptive       — individual request records, capped at 10k per query.
                               Chunked by the caller (lib/routes.py) to avoid the limit.
  httpRequestsAdaptiveGroups — pre-aggregated by Cloudflare server-side.
                               One request covers the full date range.
"""

import requests

from .config import API_TOKEN, GRAPHQL_URL, ZONE_ID, ZONE_ID_SECONDARY, PRIMARY_HOST, PRIMARY_PATH_PREFIX, SECONDARY_HOST

_CF_HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}


def graphql_api_request(start: str, end: str) -> dict:
    """
    Fetches individual HTTP request records from Cloudflare (httpRequestsAdaptive).
    Used by /get-top-urls — returns one record per request, not aggregated.

    Filters:
      - Only real user traffic (likely_human + eyeball source)
      - Scoped to PRIMARY_HOST and PRIMARY_PATH_PREFIX (if set)
      - Chunked into QUERY_HOUR_INTERVAL windows to stay under the 10k record limit
    """
    path_like = f"/{PRIMARY_PATH_PREFIX}%" if PRIMARY_PATH_PREFIX else "%"
    query = f'''
    {{
      viewer {{
        zones(filter: {{ zoneTag: "{ZONE_ID}" }}) {{
          httpRequestsAdaptive(
            filter: {{
                clientRequestHTTPHost: "{PRIMARY_HOST}",
                botManagementDecision_in: ["likely_human"],
                requestSource_in: ["eyeball"],
                clientRequestPath_like: "{path_like}",
                datetime_geq: "{start}",
                datetime_lt: "{end}"
            }}
            limit: 10000
          ) {{
            clientRequestPath
            datetime
          }}
        }}
      }}
    }}
    '''
    response = requests.post(GRAPHQL_URL, headers=_CF_HEADERS, json={'query': query}, timeout=30)
    response.raise_for_status()
    return response.json()


def graphql_api_request_groups(start: str, end: str) -> dict:
    """
    Fetches pre-aggregated HTTP request counts from Cloudflare (httpRequestsAdaptiveGroups).
    Used by /get-top-urls-groups — Cloudflare groups records server-side, so one
    request covers the full date range without hitting the 10k limit.

    Filters:
      - clientSSLProtocol: "none" → plain HTTP traffic only (no TLS)
      - Scoped to PRIMARY_HOST
    """
    query = f'''
    {{
      viewer {{
        zones(filter: {{ zoneTag: "{ZONE_ID}" }}) {{
          httpRequestsAdaptiveGroups(
            filter: {{
              clientSSLProtocol: "none"
              clientRequestHTTPHost: "{PRIMARY_HOST}"
              datetime_geq: "{start}"
              datetime_lt: "{end}"
            }}
            limit: 10000
            orderBy: [count_DESC]
          ) {{
            count
            dimensions {{
              clientRequestPath
              clientRequestHTTPMethodName
            }}
          }}
        }}
      }}
    }}
    '''
    response = requests.post(GRAPHQL_URL, headers=_CF_HEADERS, json={'query': query}, timeout=30)
    response.raise_for_status()
    return response.json()


def graphql_api_request_http_urls(start: str, end: str) -> dict:
    """
    Fetches pre-aggregated HTTP-only traffic for SECONDARY_HOST.
    Used by /http-urls and /http-urls/verify.

    Key filters:
      - clientSSLProtocol: "none"  → plain HTTP requests (client connected without TLS)
      - edgeResponseStatus: 200    → pre-filters to paths where the origin returned 200.
                                     Note: this reflects the origin status, not the final
                                     Cloudflare edge response — some of these paths may
                                     still redirect at the edge. /verify confirms live state.
      - ZONE_ID_SECONDARY          → falls back to the primary zone if not configured separately
    """
    query = f'''
    {{
      viewer {{
        zones(filter: {{ zoneTag: "{ZONE_ID_SECONDARY}" }}) {{
          httpRequestsAdaptiveGroups(
            filter: {{
              clientSSLProtocol: "none"
              clientRequestHTTPHost: "{SECONDARY_HOST}"
              edgeResponseStatus: 200
              datetime_geq: "{start}"
              datetime_leq: "{end}"
            }}
            limit: 10000
            orderBy: [count_DESC]
          ) {{
            count
            dimensions {{
              clientRequestPath
            }}
          }}
        }}
      }}
    }}
    '''
    response = requests.post(GRAPHQL_URL, headers=_CF_HEADERS, json={'query': query}, timeout=30)
    response.raise_for_status()
    return response.json()
