"""
lib/routes.py — Flask Blueprint with all Cloudflare Analytics API route handlers.

This module is the orchestration layer: it wires together the Cloudflare client
(lib/cloudflare.py), the data pipeline (lib/pipeline.py), and the path classifier
(lib/classifier.py) to serve each endpoint.

RANGES and reference_time are computed once at import time so all routes share
a consistent "now" anchor for the rolling lookback window.
"""

import requests
import pandas as pd
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, jsonify, request

from .config import CAMBRIDGE_ORG_HOST, QUERY_DAYS_BACK
from .cloudflare import (
    graphql_api_request,
    graphql_api_request_groups,
    graphql_api_request_http_urls,
)
from .pipeline import (
    export_csv,
    aggregate_top_urls,
    aggregate_top_urls_from_groups,
    generate_time_ranges,
    validate_top_parameter,
    clean_and_filter_paths,
    extract_paths_from_cf_data,
    extract_paths_from_cf_groups,
    validate_response_chunk_limit,
    normalize_path,
)
from .classifier import classify_path
from .logger import HttpErrorLogManager

bp = Blueprint('cloudflare', __name__)
logger = HttpErrorLogManager.create()

# Computed once at startup. reference_time is the "now" anchor used for all
# relative date calculations (so results are consistent within a single run).
RANGES, reference_time = generate_time_ranges()


def _resolve_date_range(start_param, end_param):
    """
    Returns (start, end) ISO datetime strings for a query.
    If ?start= and ?end= are provided in the request, use those.
    Otherwise fall back to the rolling window defined by QUERY_DAYS_BACK in config.
    """
    if start_param and end_param:
        return start_param, end_param
    start = (reference_time - timedelta(days=QUERY_DAYS_BACK)).strftime('%Y-%m-%dT%H:%M:%SZ')
    end = reference_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    return start, end


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/v1/cloudflare/get-top-urls-groups')
def top_urls_groups():
    """
    Returns top accessed URLs using Cloudflare's pre-aggregated data.
    Faster than /get-top-urls — single CF request instead of chunked loops.

    Query Parameters:
        top (int): Number of top results to return (required, > 0).
        generate (int): If 1, returns CSV download instead of JSON.
    """
    top = request.args.get("top", type=int)
    generate = request.args.get("generate", type=int)

    is_valid, error_response, status_code = validate_top_parameter(top)
    if not is_valid:
        logger.log_error(status_code, f"Invalid 'top' parameter: {top}")
        return error_response, status_code

    try:
        start = (reference_time - timedelta(days=QUERY_DAYS_BACK)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end = reference_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        response = graphql_api_request_groups(start, end)
        raw_data = response["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]

        if not raw_data:
            logger.log_error(400, "No data returned from Cloudflare API.")
            return jsonify({"error": "No data found."}), 400

        df = extract_paths_from_cf_groups(raw_data)
        df = clean_and_filter_paths(df)
        result = aggregate_top_urls_from_groups(df, reference_time, QUERY_DAYS_BACK).head(top)

        if generate:
            return export_csv(result)

        return jsonify({
            "count": len(result),
            "data": result.to_dict(orient="records")
        }), 200

    except Exception as e:
        logger.log_error(500, f"Exception in top_urls_groups: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@bp.route('/v1/cloudflare/get-top-urls')
def top_urls():
    """
    Returns top accessed URLs from Cloudflare individual request data.
    Splits the date range into QUERY_HOUR_INTERVAL chunks to stay under
    Cloudflare's 10,000-record-per-query limit.

    Query Parameters:
        top (int): Number of top results to return (required, > 0).
        generate (int): If 1, returns CSV download instead of JSON.
    """
    top = request.args.get("top", type=int)
    generate = request.args.get("generate", type=int)

    is_valid, error_response, status_code = validate_top_parameter(top)
    if not is_valid:
        logger.log_error(status_code, f"Invalid 'top' parameter: {top}")
        return error_response, status_code

    try:
        raw_data = []
        for start, end in RANGES:
            response = graphql_api_request(start, end)
            chunk = response["data"]["viewer"]["zones"][0]["httpRequestsAdaptive"]

            validate_response_chunk_limit(chunk, limit=10000, start=start, end=end)
            raw_data.extend(chunk)

        if not raw_data:
            logger.log_error(400, "No data returned from Cloudflare API.")
            return jsonify({"error": "No data found."}), 400

        df = extract_paths_from_cf_data(raw_data)
        df = clean_and_filter_paths(df)
        result = (aggregate_top_urls(df, reference_time, QUERY_DAYS_BACK).head(top))

        if generate:
            return export_csv(result)

        return jsonify({
            "count": len(result),
            "data": result.to_dict(orient="records")
        }), 200

    except Exception as e:
        logger.log_error(500, f"Exception in top_urls: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@bp.route('/v1/cloudflare/http-urls')
def http_urls():
    """
    Lists www.cambridge.org paths that received plain HTTP traffic.
    Data comes from Cloudflare — includes false positives (paths that may now redirect).
    Use /http-urls/verify for a live-probed, confirmed list.

    Query Parameters:
        stream (str): Filter by origin stream — drupal | c5 | unmatched.
        start (str): ISO 8601 UTC start datetime (overrides config default).
        end (str):   ISO 8601 UTC end datetime (overrides config default).
        generate (int): If 1, returns CSV download.
    """
    stream_filter = request.args.get("stream")
    generate = request.args.get("generate", type=int)
    start, end = _resolve_date_range(request.args.get("start"), request.args.get("end"))

    try:
        response = graphql_api_request_http_urls(start, end)
        if response.get("errors"):
            msg = response["errors"][0]["message"]
            logger.log_error(500, f"Cloudflare API error: {msg}")
            return jsonify({"error": f"Cloudflare API error: {msg}"}), 500
        raw_data = response["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]

        if not raw_data:
            return jsonify({"error": "No HTTP traffic found for this period."}), 400

        # Strip country prefix (/gb/, /us/, etc.) so /gb/education/search and
        # /us/education/search are counted together as /education/search
        aggregated = {}
        for item in raw_data:
            raw_path = item["dimensions"]["clientRequestPath"]
            canonical = normalize_path(raw_path)
            aggregated[canonical] = aggregated.get(canonical, 0) + item["count"]

        # Remove static assets, Cloudflare internals, and noise paths
        df = pd.DataFrame([{"path": p} for p in aggregated])
        df = clean_and_filter_paths(df)
        cleaned_paths = set(df["path"].tolist())

        rows = [
            {"path": canonical, "count": count, "stream": classify_path(canonical)}
            for canonical, count in aggregated.items()
            if canonical in cleaned_paths
        ]

        if stream_filter:
            rows = [r for r in rows if r["stream"] == stream_filter]

        rows.sort(key=lambda r: r["count"], reverse=True)

        if generate:
            df_out = pd.DataFrame(rows)
            return export_csv(df_out.rename(columns={
                "path": "Page URL",
                "count": "Count",
                "stream": "Stream"
            }))

        return jsonify({
            "host": CAMBRIDGE_ORG_HOST,
            "protocol": "HTTP (clientSSLProtocol: none)",
            "date_range": {"start": start, "end": end},
            "count": len(rows),
            "data": rows
        }), 200

    except Exception as e:
        logger.log_error(500, f"Exception in http_urls: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@bp.route('/v1/cloudflare/http-urls/verify')
def http_urls_verify():
    """
    Confirms which URLs are actually accessible over plain HTTP right now.

    Unlike /http-urls (which trusts Cloudflare's logged data), this endpoint
    probes each candidate URL directly over HTTP with allow_redirects=False.
    Only paths that respond with HTTP 200 — not 301/302 — are returned.

    Uses 20 concurrent workers to probe URLs in parallel (sequential probing
    would time out for large candidate sets like the unmatched stream).

    Query Parameters:
        stream (str): Filter before probing — drupal | c5 | unmatched.
        start (str): ISO 8601 UTC start datetime (overrides config default).
        end (str):   ISO 8601 UTC end datetime (overrides config default).
        generate (int): If 1, returns CSV download.
    """
    stream_filter = request.args.get("stream")
    generate = request.args.get("generate", type=int)
    start, end = _resolve_date_range(request.args.get("start"), request.args.get("end"))

    try:
        response = graphql_api_request_http_urls(start, end)
        if response.get("errors"):
            msg = response["errors"][0]["message"]
            return jsonify({"error": f"Cloudflare API error: {msg}"}), 500
        raw_data = response["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]

        if not raw_data:
            return jsonify({"error": "No HTTP traffic found for this period."}), 400

        # Same normalise-and-clean pipeline as /http-urls
        aggregated = {}
        for item in raw_data:
            raw_path = item["dimensions"]["clientRequestPath"]
            canonical = normalize_path(raw_path)
            aggregated[canonical] = aggregated.get(canonical, 0) + item["count"]

        df = pd.DataFrame([{"path": p} for p in aggregated])
        df = clean_and_filter_paths(df)
        cleaned_paths = set(df["path"].tolist())

        candidates = [
            {"path": canonical, "count": count, "stream": classify_path(canonical)}
            for canonical, count in aggregated.items()
            if canonical in cleaned_paths
        ]

        if stream_filter:
            candidates = [r for r in candidates if r["stream"] == stream_filter]

        # Probe each candidate over plain HTTP (no redirect following)
        def probe(row):
            url = f"http://{CAMBRIDGE_ORG_HOST}{row['path']}"
            try:
                resp = requests.get(url, allow_redirects=False, timeout=10)
                # Only include URLs that serve content (200), not those that redirect
                if resp.status_code == 200:
                    return {**row, "status": resp.status_code}
            except Exception:
                pass
            return None

        confirmed = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(probe, row): row for row in candidates}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    confirmed.append(result)

        confirmed.sort(key=lambda r: r["count"], reverse=True)

        if generate:
            df = pd.DataFrame(confirmed)
            return export_csv(df.rename(columns={
                "path": "Page URL",
                "count": "CF HTTP hits",
                "stream": "Stream",
                "status": "HTTP Status"
            }))

        return jsonify({
            "host": CAMBRIDGE_ORG_HOST,
            "date_range": {"start": start, "end": end},
            "count": len(confirmed),
            "data": confirmed
        }), 200

    except Exception as e:
        logger.log_error(500, f"Exception in http_urls_verify: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@bp.route('/')
def index():
    return jsonify({
        "message": "Cloudflare GraphQL Data API",
        "endpoints": [
            "/v1/cloudflare/get-top-urls?top=10&generate=1",
            "/v1/cloudflare/get-top-urls-groups?top=10&generate=1",
            "/v1/cloudflare/http-urls",
            "/v1/cloudflare/http-urls?stream=drupal",
            "/v1/cloudflare/http-urls?generate=1",
            "/v1/cloudflare/http-urls/verify",
            "/v1/cloudflare/http-urls/verify?stream=unmatched",
            "/v1/cloudflare/http-urls/verify?generate=1"
        ]
    })
