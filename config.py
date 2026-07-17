"""
Configuration settings for the Cloudflare GraphQL API.
Adjust these values as needed for your environment.
"""

import os
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
# Defined here so it's injectable in tests; app.py reads it directly.
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
