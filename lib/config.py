"""
lib/config.py — Shared configuration for the Cloudflare GraphQL API.

Configure via a .env file at the project root. Required keys:

  CLOUDFLARE_API_TOKEN=<token>   API token with Analytics:Read on both zones.
  CLOUDFLARE_ZONE_ID=<id>        Zone ID for cambridge.edu.au.
  CLOUDFLARE_ZONE_ID_ORG=<id>    Zone ID for www.cambridge.org.

See .env.example for a full template.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# --- Cloudflare credentials ---
# API token must have Analytics:Read permission for both zones.
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")

# Zone ID for cambridge.edu.au (used by /get-top-urls endpoints)
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID", "")

# Zone ID for www.cambridge.org (used by /http-urls endpoints — different Cloudflare account)
ZONE_ID_ORG = os.getenv("CLOUDFLARE_ZONE_ID_ORG", "")

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

# --- cambridge.edu.au config (used by /get-top-urls) ---
SUB_DOMAIN = "https://www.cambridge.edu.au"
HOST = "www.cambridge.edu.au"
PATH = "education"  # Limits /get-top-urls queries to /education/* paths only

# --- cambridge.org config (used by /http-urls) ---
CAMBRIDGE_ORG_HOST = "www.cambridge.org"

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
        ("CLOUDFLARE_ZONE_ID_ORG", ZONE_ID_ORG),
    ] if not val]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Create a .env file at the project root — see .env.example for a template.", file=sys.stderr)
        sys.exit(1)
