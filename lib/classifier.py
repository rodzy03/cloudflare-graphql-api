"""
lib/classifier.py — Configurable request-path classifier.

Tags request paths with a named "stream" — e.g. which backend or team owns a
path — so /http-urls and /http-urls/verify can filter results by stream.

Rules live in an external JSON file (path set by CLASSIFIER_RULES_PATH in
lib/config.py) rather than in code, so this can be adapted to any site's
routing without touching Python. See classifier_rules.example.json for the
shape and a generic starter ruleset.
"""

import json
import re
import sys

from .config import CLASSIFIER_RULES_PATH


def _load_rules(path: str) -> dict:
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(
            f"WARNING: classifier rules file not found at '{path}'. "
            "All paths will be classified as the default stream. "
            "See classifier_rules.example.json for the expected format.",
            file=sys.stderr,
        )
        return {"streams": [], "default": "unmatched"}

    streams = [
        {
            "name": stream["name"],
            "include": [re.compile(p) for p in stream.get("include", [])],
            "exclude": [re.compile(p) for p in stream.get("exclude", [])],
        }
        for stream in raw.get("streams", [])
    ]
    return {"streams": streams, "default": raw.get("default", "unmatched")}


_RULES = _load_rules(CLASSIFIER_RULES_PATH)


def classify_path(path: str) -> str:
    """
    Returns the configured stream name for a request path, or the rules
    file's configured default if no stream's rule matches.

    Streams are evaluated in the order they appear in the rules file — the
    first stream whose include pattern matches the path (and none of its
    exclude patterns do) wins.
    """
    for stream in _RULES["streams"]:
        if any(pattern.search(path) for pattern in stream["exclude"]):
            continue
        if any(pattern.search(path) for pattern in stream["include"]):
            return stream["name"]
    return _RULES["default"]
