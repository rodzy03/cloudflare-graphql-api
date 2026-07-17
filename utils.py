from config import QUERY_DAYS_BACK, QUERY_HOUR_INTERVAL, SUB_DOMAIN
from datetime import datetime, timedelta
from io import BytesIO
from flask import send_file, jsonify
import pandas as pd
import re

# Strips a leading 2-letter country/language prefix from a path.
# e.g. /gb/education/search → /education/search
# This lets us aggregate traffic across all country variants of the same page.
_LANG_PREFIX = re.compile(r'^/[a-z]{2}/')

def normalize_path(path: str) -> str:
    """Strip leading 2-letter country/language prefix: /gb/education/... → /education/..."""
    return _LANG_PREFIX.sub('/', path)


def format_count(row: pd.Series) -> str:
    """Format a raw visit count into a human-readable string (e.g. 1500 → '1.5k')."""
    try:
        visits = int(row["total_count"])
        if visits >= 1000:
            val = round(visits / 1000, 1)
            return f"{int(val)}k" if val == int(val) else f"{val}k"
        return str(visits)
    except Exception:
        return "0"


def export_csv(result_df: pd.DataFrame):
    """Serialize a DataFrame to a CSV file response for browser download."""
    csv_string = result_df.to_csv(index=False)
    csv_bytes = BytesIO()
    csv_bytes.write(csv_string.encode("utf-8"))
    csv_bytes.seek(0)

    return send_file(
        csv_bytes,
        mimetype="text/csv",
        as_attachment=True,
        download_name="top_urls.csv"
    )


def generate_time_ranges(reference_time: datetime = None):
    """
    Split the configured lookback window into fixed-size hour intervals.

    Cloudflare's httpRequestsAdaptive API returns individual request records
    (not aggregated), capped at 10,000 per query. For busy sites, a full day
    of data easily exceeds that. Splitting into QUERY_HOUR_INTERVAL-sized
    chunks (default: 4h) keeps each request under the limit.

    Returns:
        (ranges, reference_time): list of (start, end) ISO strings + the base datetime.
    """
    if reference_time is None:
        reference_time = datetime.utcnow()

    ranges = []
    for i in range(QUERY_DAYS_BACK, 0, -1):
        for hour in range(0, 24, QUERY_HOUR_INTERVAL):
            start = (reference_time - timedelta(days=i)).replace(hour=hour, minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=QUERY_HOUR_INTERVAL)
            ranges.append((
                start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                end.strftime('%Y-%m-%dT%H:%M:%SZ')
            ))

    return ranges, reference_time


# Paths that are never meaningful content (admin tools, static pipelines, etc.)
EXCLUDED_PREFIXES = (
    "/education/files",
    "/education/themes",
    "/education/packages",
    "/education/updates",
    "/education/tools",
    "/education/image",
    "/education/dashboard",
    "/education___",
    "/cdn-cgi/",   # Cloudflare internal challenge/bot-management paths
)

# Static file extensions — not page URLs, irrelevant for the HTTP-access audit
EXCLUDED_SUFFIXES = (
    ".gif", ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".svg", ".ico",
    ".css", ".js", ".json", ".woff", ".woff2", ".ttf", ".eot",
    ".pl", ".xml", ".php", ".html", ".map", ".txt"
)

EXCLUDED_PATTERN = r"[{}~*]"  # Paths with special chars are malformed or scanner noise


def clean_and_filter_paths(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove static assets, internal tooling paths, and malformed URLs.

    Filters out:
    - Known static/admin path prefixes (EXCLUDED_PREFIXES)
    - Static file extensions (EXCLUDED_SUFFIXES)
    - Paths containing special characters (scanner noise)
    - Trailing slashes, except for bare root '/'
    """
    if "path" not in df.columns:
        raise ValueError("DataFrame must contain a 'path' column.")

    df = df[
        ~(
            df["path"].str.startswith(EXCLUDED_PREFIXES) |
            df["path"].str.endswith(EXCLUDED_SUFFIXES) |
            df["path"].str.contains(EXCLUDED_PATTERN, regex=True)
        )
    ].copy()

    df["path"] = df["path"].apply(lambda p: p.rstrip("/") if p != "/" else p)

    return df


def extract_paths_from_cf_data(data: list) -> pd.DataFrame:
    """
    Convert raw httpRequestsAdaptive records (individual requests) to a path DataFrame.
    Each record has a clientRequestPath field.
    """
    return pd.DataFrame([{"path": row["clientRequestPath"]} for row in data])


def extract_paths_from_cf_groups(data: list) -> pd.DataFrame:
    """
    Convert raw httpRequestsAdaptiveGroups records (pre-aggregated by Cloudflare)
    to a DataFrame with path and count columns.
    """
    return pd.DataFrame([{
        "path": row["dimensions"]["clientRequestPath"],
        "count": row["count"]
    } for row in data])


def aggregate_top_urls(df: pd.DataFrame, reference_time: datetime, days_back: int) -> pd.DataFrame:
    """
    Count visits per path and compute average visits per hour.
    Used by /get-top-urls (individual record data — counts are derived from value_counts).
    """
    result = df["path"].value_counts().reset_index()
    result.columns = ["path", "total_count"]

    total_hours = (datetime.utcnow() - (reference_time - timedelta(days=days_back))).total_seconds() / 3600
    result["visit_per_hour"] = (result["total_count"] / total_hours).round(4)
    result["total_count"] = result.apply(format_count, axis=1)
    result["path"] = SUB_DOMAIN + result["path"]
    return result


def aggregate_top_urls_from_groups(df: pd.DataFrame, reference_time: datetime, days_back: int) -> pd.DataFrame:
    """
    Sum pre-aggregated counts per path and compute average visits per hour.
    Used by /get-top-urls-groups (Cloudflare already grouped — counts come from the API).
    """
    result = df.groupby("path", as_index=False)["count"].sum()
    result = result.rename(columns={"count": "total_count"})
    result = result.sort_values("total_count", ascending=False).reset_index(drop=True)

    total_hours = (datetime.utcnow() - (reference_time - timedelta(days=days_back))).total_seconds() / 3600
    result["visit_per_hour"] = (result["total_count"] / total_hours).round(4)
    result["total_count"] = result.apply(format_count, axis=1)
    result["path"] = SUB_DOMAIN + result["path"]
    return result


def validate_top_parameter(top: int):
    """Validate that the ?top= query param is a positive integer."""
    if not top or top <= 0:
        error_msg = "Invalid 'top' parameter. Must be a positive integer."
        return False, jsonify({"error": error_msg}), 400
    return True, None, None


def validate_response_chunk_limit(response_chunk: list, limit: int = 10000, start: str = "", end: str = "") -> bool:
    """
    Warn if a response chunk hits Cloudflare's record limit.
    When the limit is reached, data for that time window is truncated —
    consider reducing QUERY_HOUR_INTERVAL in config.py to get full coverage.
    """
    if len(response_chunk) >= limit:
        print(f"Warning: Data limit hit ({limit} records) for range {start} → {end}.")
        print("Consider reducing QUERY_HOUR_INTERVAL in config.py to avoid losing data.")
        return True
    return False
