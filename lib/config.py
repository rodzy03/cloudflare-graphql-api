"""
lib/config.py — Shared configuration for the Cloudflare GraphQL API.

Configure via a .env file at the project root. Required keys:

  CLOUDFLARE_API_TOKEN=<token>   API token with Analytics:Read on the zone(s) below.
  CLOUDFLARE_ZONE_ID=<id>        Primary zone ID, used by /get-top-urls endpoints.
  PRIMARY_HOST=<host>            Hostname to query, e.g. www.example.com.

See .env.example for the full template, including the optional secondary
zone/host used by /http-urls endpoints.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# --- Cloudflare credentials ---
# API token must have Analytics:Read permission for the zone(s) below.
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")

# --- Primary zone (used by /get-top-urls and /get-top-urls-groups) ---
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID", "")
PRIMARY_HOST = os.getenv("PRIMARY_HOST", "")

# Optional path prefix to scope /get-top-urls queries, e.g. "blog" limits to
# /blog/*. Leave unset to match all paths.
PRIMARY_PATH_PREFIX = os.getenv("PRIMARY_PATH_PREFIX", "").strip("/")

PRIMARY_BASE_URL = f"https://{PRIMARY_HOST}" if PRIMARY_HOST else ""

# --- Secondary zone (used by /http-urls endpoints) ---
# Falls back to the primary zone/host if unset — only configure these
# separately if that traffic lives on a different zone (e.g. a different
# Cloudflare account) than the primary one above.
ZONE_ID_SECONDARY = os.getenv("CLOUDFLARE_ZONE_ID_SECONDARY") or ZONE_ID
SECONDARY_HOST = os.getenv("SECONDARY_HOST") or PRIMARY_HOST

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

# Path to the classifier rules file used by lib/classifier.py.
CLASSIFIER_RULES_PATH = os.getenv("CLASSIFIER_RULES_PATH", "classifier_rules.example.json")

"""
Time range configuration for querying analytics data.

QUERY_DAYS_BACK:
    - Number of past days to include in the query.
    - Example: 7 means query data for the past 7 days.

QUERY_HOUR_INTERVAL:
    - Time slice size (hours) per GraphQL request for /get-top-urls.
    - Cloudflare's httpRequestsAdaptive returns individual records (not aggregated),
      so large windows hit the 10,000-record limit per request.
    - Splitting into 4-hour blocks keeps each chunk under the limit.
    - Not used by httpRequestsAdaptiveGroups endpoints — those aggregate server-side.
"""

QUERY_DAYS_BACK = 7
QUERY_HOUR_INTERVAL = 4


def validate_config():
    """Fail fast at startup if required Cloudflare credentials are missing."""
    missing = [name for name, val in [
        ("CLOUDFLARE_API_TOKEN", API_TOKEN),
        ("CLOUDFLARE_ZONE_ID", ZONE_ID),
        ("PRIMARY_HOST", PRIMARY_HOST),
    ] if not val]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Create a .env file at the project root — see .env.example for a template.", file=sys.stderr)
        sys.exit(1)
