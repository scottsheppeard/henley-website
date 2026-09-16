#!/usr/bin/env python3
"""
export.py — fetch thehenley.com.au and write a static, self-contained copy.

The output is the website. Not a source for one: the HTML, CSS and JavaScript
Elementor produced are kept exactly as served, because the whole point of this
stream is that the public cannot tell the difference. What changes is listed
in docs/superpowers/specs/2026-09-16-legacy-replica-design.md §3 and §4 and
implemented, one rule per function, below.

    forms/.venv/bin/python replica/export.py            # writes replica/site and replica/manifest.json
    forms/.venv/bin/python replica/export.py --out /tmp/x --manifest /tmp/x.json

Standard library only, so it runs with any Python 3.11+ on the host.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ORIGIN = "https://thehenley.com.au"
HOST = "thehenley.com.au"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 henley-replica-export"
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MANIFEST_SOURCE = REPO / "source/migration-manifest.json"

# Addresses the sitemap does not list but the URL gate requires. (url, file).
EXTRA_PAGES = [("/news/page/2/", "news/page/2/index.html")]
FEEDS = [("/feed/", "feed/index.xml"), ("/news/feed/", "news/feed/index.xml")]
# Yoast's index is served at /sitemap-index.xml (the old name 301s to it) and
# its children are renamed, because the existing redirects send the old child
# names to the index — keeping them would loop.
SITEMAPS = [
    ("/sitemap_index.xml", "sitemap-index.xml"),
    ("/page-sitemap.xml", "sitemap-pages.xml"),
    ("/post-sitemap.xml", "sitemap-posts.xml"),
    ("/main-sitemap.xsl", "main-sitemap.xsl"),
]
ROBOTS = ("/robots.txt", "robots.txt")
# Any path WordPress has never had; its 404 template is the replica's 404 page.
NOT_FOUND_PROBE = "/replica-404-probe-2026/"


class ExportError(Exception):
    """The export cannot produce a faithful site; stop rather than ship a wrong one."""


# ── Where things land ────────────────────────────────────────────────────────

def page_file(url_path: str) -> str:
    """`/a/b/` -> `a/b/index.html`; `/` -> `index.html`."""
    if not url_path.endswith("/"):
        raise ExportError(f"page path {url_path!r} has no trailing slash; nginx would 404 it")
    return "index.html" if url_path == "/" else url_path.strip("/") + "/index.html"


def asset_file(url_path: str) -> str:
    """The asset's own path, without query or fragment: nginx ignores both when
    it resolves a file, so `style.css?ver=1.0.4` in the HTML still serves it."""
    return url_path.split("?", 1)[0].split("#", 1)[0].lstrip("/")


# ── Asset discovery ──────────────────────────────────────────────────────────
#
# Regexes rather than an HTML parser, deliberately: a parser would also have to
# re-serialise the document, and the one thing this export must not do is
# change markup it does not mean to. Elementor puts asset URLs in href, src,
# srcset, data-lazy-src, data-lazy-srcset, inline style attributes and
# JSON-escaped data-settings; a URL is a URL wherever it sits.

ASSET_ABS_RE = re.compile(r"https?://thehenley\.com\.au(/wp-(?:content|includes)/[^\s\"'<>(),\\]+)")
ASSET_REL_RE = re.compile(r"(?<![\w./:-])(/wp-(?:content|includes)/[^\s\"'<>(),\\]+)")


def _asset_path(raw: str) -> str | None:
    path = html.unescape(raw).split("?", 1)[0].split("#", 1)[0]
    if path.endswith("/") or path.endswith(".php"):
        return None
    return path


def find_assets(text: str) -> set[str]:
    """Every same-origin file under /wp-content/ or /wp-includes/ the document references."""
    unescaped = text.replace("\\/", "/")
    found: set[str] = set()
    for regex in (ASSET_ABS_RE, ASSET_REL_RE):
        for match in regex.finditer(unescaped):
            path = _asset_path(match.group(1))
            if path:
                found.add(path)
    return found


CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)")
CSS_IMPORT_RE = re.compile(r"@import\s+(?!url\()['\"]([^'\"]+)['\"]")


def find_css_assets(css_text: str, css_path: str) -> set[str]:
    """Same-origin files a stylesheet pulls in, resolved against the stylesheet's own path."""
    found: set[str] = set()
    refs = [m.group(2) for m in CSS_URL_RE.finditer(css_text)]
    refs += [m.group(1) for m in CSS_IMPORT_RE.finditer(css_text)]
    for ref in refs:
        ref = ref.strip()
        if ref.startswith(("data:", "#")):
            continue
        split = urlsplit(urljoin(ORIGIN + css_path, ref))
        if split.netloc and split.netloc != HOST:
            continue
        path = _asset_path(split.path)
        if path and path.startswith(("/wp-content/", "/wp-includes/")):
            found.add(path)
    return found


# ── Post-processing ──────────────────────────────────────────────────────────
#
# Each entry is one thing WordPress adds that has no meaning without WordPress
# behind it, or that would advertise an endpoint the replica answers 410. The
# name is what the manifest and the tests refer to. Nothing else in the page is
# touched by this step.

REMOVALS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern, re.S | re.I)) for name, pattern in [
        ("REST discovery link",   r"<link\s+rel=[\"']https://api\.w\.org/[\"'][^>]*>\s*"),
        ("REST alternate link",   r"<link\s+rel=[\"']alternate[\"']\s+title=[\"']JSON[\"']\s+type=[\"']application/json[\"'][^>]*>\s*"),
        ("EditURI link",          r"<link\s+rel=[\"']EditURI[\"'][^>]*>\s*"),
        ("wlwmanifest link",      r"<link\s+rel=[\"']wlwmanifest[\"'][^>]*>\s*"),
        ("shortlink",             r"<link\s+rel=[\"']shortlink[\"'][^>]*>\s*"),
        ("pingback link",         r"<link\s+rel=[\"']pingback[\"'][^>]*>\s*"),
        ("oEmbed links",          r"<link\s+rel=[\"']alternate[\"']\s+title=[\"']oEmbed[^>]*>\s*"),
        ("comments feed link",    r"<link\s+rel=[\"']alternate[\"'][^>]*Comments Feed[^>]*>\s*"),
        ("generator meta",        r"<meta\s+name=[\"']generator[\"'][^>]*>\s*"),
        ("Site Kit adsense meta", r"<meta\s+name=[\"']google-adsense-platform-[^>]*>\s*"),
        ("emoji styles",          r"<style\s+id=[\"']wp-emoji-styles-inline-css[\"']>.*?</style>\s*"),
        # WordPress 7.1 no longer inlines the emoji loader on these pages, but
        # older cached copies and the style block still carry it; harmless when
        # it matches nothing.
        ("emoji script",          r"<script[^>]*>(?:(?!</script>).)*_wpemojiSettings(?:(?!</script>).)*</script>\s*"),
        ("Gravity Forms scripts", r"<script[^>]*src=[\"'][^\"']*/plugins/gravity(?:forms|-forms)[^\"']*[\"'][^>]*>\s*</script>\s*"),
        ("Gravity Forms inline",  r"<script(?:\s[^>]*)?>(?:(?!</script>).)*\bgform(?:(?!</script>).)*</script>\s*"),
    ]
]


def remove_wordpress_tags(text: str) -> str:
    for _name, regex in REMOVALS:
        text = regex.sub("", text)
    return text


# WordPress nonces in the inline Elementor and REST configuration rotate every
# day. Their endpoints answer 410 here, so their value is irrelevant — but a
# refreshed export would otherwise differ on every page for no reason.
NONCE_RE = re.compile(r'"nonce":"[0-9a-f]{6,}"')


def normalise_nonces(text: str) -> str:
    return NONCE_RE.sub('"nonce":"0000000000"', text)


# Metadata that must keep naming the production origin: the canonical, every
# <meta> (og:*, twitter:*), the RSS alternates and the JSON-LD graph. Search
# engines and social scrapers read the absolute URL; on dev it is deliberately
# "wrong" in the same way the Astro site's was.
PROTECTED_RE = re.compile(
    r"<link\b[^>]*\brel=[\"']canonical[\"'][^>]*>"
    r"|<link\b[^>]*\brel=[\"']alternate[\"'][^>]*\btype=[\"']application/rss\+xml[\"'][^>]*>"
    r"|<meta\b[^>]*>"
    r"|<script\b[^>]*application/ld\+json[^>]*>.*?</script>",
    re.S | re.I,
)
ORIGIN_THEN_QUOTE_RE = re.compile(r"https?://thehenley\.com\.au(?=[\"'])")
ORIGIN_THEN_SLASH_RE = re.compile(r"https?://thehenley\.com\.au(?=/)")
# Inside JSON-escaped inline configuration only *asset* URLs are relativised.
# Site URLs (home_url, ajaxurl) stay: code concatenates onto them and their
# endpoints answer 410 on the replica anyway.
ORIGIN_ESCAPED_ASSET_RE = re.compile(r"https?:\\/\\/thehenley\.com\.au(?=\\/wp-(?:content|includes)\\/)")


def _relativise(span: str) -> str:
    span = ORIGIN_THEN_QUOTE_RE.sub("/", span)      # href="https://thehenley.com.au" -> href="/"
    span = ORIGIN_THEN_SLASH_RE.sub("", span)       # https://thehenley.com.au/x -> /x
    return ORIGIN_ESCAPED_ASSET_RE.sub("", span)    # https:\/\/thehenley.com.au\/wp-content\/x -> \/wp-content\/x


def rewrite_origin(text: str) -> str:
    """Same-origin references become root-relative, so dev serves its own copy
    of every asset and page rather than reaching back to production. The
    JSON-escaped form (https:\\/\\/…) is left alone on purpose."""
    out: list[str] = []
    position = 0
    for match in PROTECTED_RE.finditer(text):
        out.append(_relativise(text[position:match.start()]))
        out.append(match.group(0))
        position = match.end()
    out.append(_relativise(text[position:]))
    return "".join(out)


def rewrite_css(text: str) -> str:
    return ORIGIN_THEN_SLASH_RE.sub("", text)


def clean_html(text: str) -> str:
    """The whole post-processing pass for a page, in the only order that works:
    remove first (so a removed tag's URL is never rewritten), then normalise,
    then relativise."""
    return rewrite_origin(normalise_nonces(remove_wordpress_tags(text)))
