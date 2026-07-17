"""
Origin rule classifiers for www.cambridge.org.

Mirrors the Cloudflare origin rules that determine which backend serves each request.
Used to tag HTTP-traffic paths with which stream owns them.

Output streams:
  drupal    — Drupal CMS (covers education, academic, english, edumar streams + Drupal-specific paths)
  c5        — C5 legacy platform (catch-all for remaining content paths)
  unmatched — Falls outside all known origin rules (e.g. /highereducation/, /engage/)
"""

import re

_BASE = r"https://www\.cambridge\.org"
_LANG = r"(?:[a-z]{2}/)?"  # Optional 2-letter country/language prefix, e.g. /gb/, /us/

# ---------------------------------------------------------------------------
# Drupal patterns
# All traffic that Cloudflare routes to the Drupal origin.
# Includes: education stream, academic stream, english stream, edumar stream,
# and Drupal-specific paths (profile, sitemap, gigya, etc.)
# ---------------------------------------------------------------------------

_DRUPAL_PATTERNS = [
    # Education stream: /education/* and /{lang}/education/*
    re.compile(_BASE + r"/+(?:[a-z]{2}/+)?education(?:/|$)"),

    # Academic stream: /universitypress/* and /{lang}/universitypress/*
    re.compile(_BASE + r"/+(?:[a-z]{2}/+)?universitypress(?:/|$)"),

    # Edumar stream: event and news paths
    re.compile(_BASE + r"/" + _LANG + r"(?:news-and-events|event-registration|form/cu-events-registration-form/confirmation)"),

    # English stream: /cambridgeenglish/* and /{lang}/cambridgeenglish/*
    # Note: grammar-and-beyond-2nd-edition is excluded below and falls to C5
    re.compile(_BASE + r"/+(?:[a-z]{2}/+)?cambridgeenglish(?:/|$)"),

    # Drupal-specific: bare universitypress root
    re.compile(_BASE + r"/" + _LANG + r"(?:universitypress)/?$"),

    # Drupal-specific: system/utility files
    re.compile(_BASE + r"/(?:index\.php|\.well-known/security\.txt|sitemap\.xml|sitemaps/[^/]+/sitemap-drupal\.xml|sitemap_generator/[^/]+/sitemap\.xsl)"),

    # Drupal-specific: file download endpoints
    re.compile(_BASE + r"/(?:download_file/(?:force|stream)/\d+)"),

    # Drupal-specific: API endpoints
    re.compile(_BASE + r"/" + _LANG + r"api/(?:cambridge_regionalization|checkout|ecommerce|product)"),

    # Drupal-specific: module/theme/gigya paths
    re.compile(_BASE + r"/" + _LANG + r"(?:report-piracy|pittbuilding|libraries|webform|themes|modules|gigya|themes/custom|sites/default/files)"),

    # Drupal-specific: AJAX and autocomplete
    re.compile(_BASE + r"/" + _LANG + r"(?:.*/)?" + r"(?:views/ajax|search-title/autoCompleteList)"),

    # Drupal-specific: profile page (bare, no subpaths)
    re.compile(_BASE + r"/" + _LANG + r"profile/?$"),

    # Drupal-specific: CMS pages and auth flows
    re.compile(
        _BASE + r"/" + _LANG +
        r"(?:media/oembed|signin|register|signin-preload|signin-api|forgot-password|reset-password"
        r"|verify-email|completion|search-title/autocompletelist|internationaleducation|booksellers"
        r"|rights-and-permissions|newsroom|modern-slavery|msa-statement|jobs|inclusion|history"
        r"|human-trafficking|gender-pay|governance|education-reform|educationreform|ed-reform"
        r"|edreform|diversity|copyright|accessibility|anti-slavery|who-we-are|what-we-do"
        r"|contact-us|services|slavery|societies|story|terms-and-conditions|terms-of-use"
        r"|terms-use|terms|shopping-help/terms-and-conditions|educationreform/contact-us2"
        r"|educationreform/unicef|ell-teacher-resource|english|our-story|legal|shopping-help"
        r"|shopping-help/remittance-information|shopping-help/delivery-and-returns|partnership"
        r"|cambridgelms|all-news-insights|news-and-insights|people-and-planet|about-us"
        r"|the-assessment-network|educational-research|archives-and-heritage"
        r"|resource-password-confirm|resource-password-validation|payment_options"
        r"|node/\d+|access-request-form|core/misc)"
    ),

    # Drupal-specific: universitypress sub-pages
    re.compile(
        _BASE + r"/" + _LANG +
        r"universitypress/(?:bibles/coronation|bibles/familychronicle/brown-calfskin-edition"
        r"|bibles/familychronicle|bibles/illuminated-gospel-of-st-john|who-we-serve"
        r"|what-we-offer|conferences-and-events|about-us|environmental-sustainability|alerts_new)"
    ),

    re.compile(_BASE + r"/checkout/payment"),
    re.compile(_BASE + r"/africa/"),
]

# signin/logout is excluded from Drupal — C5 handles logout
_DRUPAL_EXCLUDE_SIGNIN = re.compile(_BASE + r"/" + _LANG + r"signin/logout")

# grammar-and-beyond is excluded from the English stream AND Drupal — it falls to C5
# This is an explicit carve-out in the original Cloudflare English stream rule
_DRUPAL_EXCLUDE_GRAMMAR = re.compile(
    _BASE + r"/" + _LANG + r"cambridgeenglish/catalog/adult-courses/grammar-and-beyond-2nd-edition"
)

# ---------------------------------------------------------------------------
# C5 patterns
# C5 is the legacy platform — a catch-all for paths not served by Drupal.
# The main rule matches almost everything; exclusions carve out known non-C5 paths.
# ---------------------------------------------------------------------------

# Matches any path with at least one segment (e.g. /something or /gb/something)
_C5_MAIN = re.compile(_BASE + r"/(?:[a-z]{2}/)?[^/].+")

_C5_EXCLUSIONS = [
    # Static root files
    re.compile(_BASE + r"/(?:robots\.txt|ads\.txt|favicon\.ico|app-ads\.txt|index\.php)$"),

    # Paths explicitly routed to Drupal by the C5 exclusion rule
    re.compile(_BASE + r"/" + _LANG + r"(?:register|education/order_request_form|universitypress/author-services|universitypress/library-etextbooks-trial-request)"),

    # Legacy/deprecated sections not served by C5
    re.compile(_BASE + r"/(?:assets-delivery|checkout|about-us|go|GO|pdp|authorhub|core|highereducation|engage|aca/|elt/blog|global-nav/|book-fair-audiobooks/|[a-z]{2}?/education/blog)"),

    # Old C5 path exclusions — legacy URLs no longer active
    re.compile(_BASE + r"/(?:login|ventures|venturesarcade|akamai|americas|asia|aspnet_client|atoz|brandcenter|interchange/audioprogram|browse|caribbean_NOT_USED|c5catalogue|date|features|ieltsassets|image_guidelines|images|includes|javascript|js|login|online_new|planets|policy|press|elt/|rhythmyx|scripts|pittnew|spain|style|yournewsite|webb|vyre|cambridgespanish|africa|maintenanceProof|aus/c5catalogue|assets/|css/|turnleft)"),

    # US-specific legacy catalogue paths
    re.compile(
        _BASE + r"/us/(?:series|catalogue|CSPM|Connections|Library|SeriesSearch|SubjectSearch|ads"
        r"|Thermodynamics|Nellis_Klein|a6titles|academicprofessional|agriculture|american_government"
        r"|americancongress5|americanhistory|anthropology|archaeology|archive_ed_pdf|areastudies"
        r"|art|assets|astronomy|bookfair|books|brochures|browse|cae|cais|cambridge425"
        r"|cambridgehistories|canto|cep|chemistry|classical|cmar|cmftpb|computerscience"
        r"|criminology|css|darwin|del_awards|dev_libraries|dickens|discountassets|discipline"
        r"|dvd_9780521862493|earlyModern|earthsciences|economics|email|emails|emailtemplates"
        r"|engineering|epidemiology|errata|esl|esl_new|exhibits|features|film|foramazon"
        r"|geography|global_workplace|history|historyofislam|historyofscience|homepage|hss"
        r"|huddleston|images|js|kaviany|language|law|libraries|lifesciences|linguistics"
        r"|linguisticstexts|literature|mail|management|materialsscience|mathematics|medicine"
        r"|medievalstudies|military_history|music|notesforauthors|numericalrecipes"
        r"|numericalrecipes3|offers|online|organismalBiology|philosophy|physics|politicalscience"
        r"|popularScience|privacy|promotion|psychology|publicity|r-books|redirect|religion"
        r"|religiontexts|researchimagination|resources|scripts|searchsample|seasonal|shakespeare"
        r"|sociology|software|special|stahl|stahl_2008|stahl_jun2013|stahl_v6|stm|subjects"
        r"|talbert|teacheraccesscode|testscripts|textbooks|textiles|unsubscribe|uspromotion|zoology)"
    ),
]


def classify_path(path: str) -> str:
    """
    Returns the origin stream for a given request path: drupal | c5 | unmatched.

    Mirrors the priority order of Cloudflare origin rules:
    Drupal patterns are checked first (most specific), then C5 catch-all,
    then anything remaining is unmatched (not covered by any origin rule).

    Args:
        path: URL path, e.g. '/education/search' or '/gb/universitypress/about'
    """
    full_uri = f"https://www.cambridge.org{path}"

    # Check Drupal first — but honour the two explicit exclusions:
    # signin/logout goes to C5, grammar-and-beyond falls to C5 (not Drupal)
    if not _DRUPAL_EXCLUDE_SIGNIN.search(full_uri) and not _DRUPAL_EXCLUDE_GRAMMAR.search(full_uri):
        for pattern in _DRUPAL_PATTERNS:
            if pattern.search(full_uri):
                return "drupal"

    # C5 catch-all — matches everything except paths in the exclusion list
    if _C5_MAIN.search(full_uri):
        for excl in _C5_EXCLUSIONS:
            if excl.search(full_uri):
                # Path matches C5 main rule but is excluded — treat as unmatched
                return "unmatched"
        return "c5"

    return "unmatched"
