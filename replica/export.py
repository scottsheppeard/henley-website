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


# ── The contact form ─────────────────────────────────────────────────────────
#
# Gravity Forms renders the form, a hidden iframe for its AJAX submit, and an
# inline initialiser, in that order. All three go; replica/form.html goes in
# their place. Gravity's stylesheets stay (the removal rules only take scripts),
# which is what makes the replacement look the same.

GFORM_BLOCK_RE = re.compile(
    r"<div class='gf_browser_[^']*gform_wrapper[^>]*>.*?</form>\s*</div>"
    r"(?:\s*<iframe[^>]*gform_ajax_frame_\d+[^>]*>.*?</iframe>)?"
    r"(?:\s*<script>.*?</script>)?",
    re.S,
)


def replace_form(text: str, form_html: str) -> str:
    replaced, count = GFORM_BLOCK_RE.subn(lambda _m: form_html, text, count=1)
    if count != 1:
        raise ExportError("no Gravity Forms block to replace; refusing to ship the page without a form")
    return replaced


# ── Sitemaps ─────────────────────────────────────────────────────────────────

def rewrite_sitemap(text: str) -> str:
    """Yoast's index names its children; those names are redirected to the
    index by the existing rules, so they are renamed here. Page <loc>s keep
    the production origin — that is what a sitemap is for."""
    text = text.replace(f"{ORIGIN}/post-sitemap.xml", f"{ORIGIN}/sitemap-posts.xml")
    text = text.replace(f"{ORIGIN}/page-sitemap.xml", f"{ORIGIN}/sitemap-pages.xml")
    return text.replace(f'href="{ORIGIN}/main-sitemap.xsl"', 'href="/main-sitemap.xsl"')


# ── Fetching ─────────────────────────────────────────────────────────────────

def fetch(url: str, expect: int = 200) -> bytes:
    """One GET, three attempts on transport errors and 5xx, and the body only
    if the status is the one expected. A 200 for a page that should 404, or a
    404 for a page that should exist, is an export that must not ship."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status, body = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, body = error.code, error.read()
            if status >= 500:
                last_error = error
                time.sleep(2 * (attempt + 1))
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
            continue
        if status != expect:
            raise ExportError(f"{url}: expected {expect}, got {status}")
        return body
    raise ExportError(f"{url}: {last_error}")


# ── The run ──────────────────────────────────────────────────────────────────

def _is_fetchable_asset(path: str) -> bool:
    """find_assets matches any /wp-content/ or /wp-includes/ reference, but a
    handful of those are not files: WordPress's speculationrules script lists
    glob patterns ("/wp-content/uploads/*") and Gravity Forms' inline config
    stores bare base paths ("/wp-content/plugins/gravityforms") for building
    other URLs in JS. Neither is fetchable, and both are prefixes of real
    asset paths, so writing them as files would block the real ones."""
    name = path.rsplit("/", 1)[-1]
    return "." in name and "*" not in path


def run(origin: str, out: Path, manifest_path: Path, form_path: Path | None = None,
        form_html: str | None = None) -> None:
    if form_html is None:
        form_html = (form_path or HERE / "form.html").read_text(encoding="utf-8")
    source = json.loads(MANIFEST_SOURCE.read_text(encoding="utf-8"))

    records: list[dict] = []
    assets: set[str] = set()

    def write(file: str, data: bytes, url_path: str, kind: str) -> None:
        target = out / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({"file": file, "url": origin + url_path, "kind": kind,
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    pages = [(entry["path"], page_file(entry["path"])) for entry in source["urls"]] + EXTRA_PAGES
    for url_path, file in pages:
        text = fetch(origin + url_path).decode("utf-8")
        if url_path == "/contact/":
            text = replace_form(text, form_html)
        elif GFORM_BLOCK_RE.search(text):
            raise ExportError(f"{url_path} embeds a Gravity Form; only /contact/ is expected to")
        cleaned = clean_html(text)
        assets |= find_assets(cleaned)
        write(file, cleaned.encode("utf-8"), url_path, "page")
        print(f"  page   {url_path}")

    text = fetch(origin + NOT_FOUND_PROBE, expect=404).decode("utf-8")
    cleaned = clean_html(text)
    assets |= find_assets(cleaned)
    write("404.html", cleaned.encode("utf-8"), NOT_FOUND_PROBE, "404")
    print("  404    (WordPress's 404 template)")

    for url_path, file in FEEDS:
        write(file, fetch(origin + url_path), url_path, "feed")
        print(f"  feed   {url_path}")

    for url_path, file in SITEMAPS:
        body = fetch(origin + url_path)
        if file.endswith(".xml"):
            body = rewrite_sitemap(body.decode("utf-8")).encode("utf-8")
        write(file, body, url_path, "sitemap")
        print(f"  sitemap {url_path} -> /{file}")

    write(ROBOTS[1], fetch(origin + ROBOTS[0]), ROBOTS[0], "robots")

    pending = sorted(p for p in assets if _is_fetchable_asset(p))
    seen: set[str] = set()
    while pending:
        path = pending.pop(0)
        if path in seen:
            continue
        seen.add(path)
        body = fetch(origin + path)
        if path.endswith(".css"):
            css_text = body.decode("utf-8")
            for extra in sorted(find_css_assets(css_text, path)):
                if extra not in seen and _is_fetchable_asset(extra):
                    pending.append(extra)
            body = rewrite_css(css_text).encode("utf-8")
        write(asset_file(path), body, path, "asset")
    print(f"  assets {len(seen)}")

    records.sort(key=lambda r: r["file"])
    manifest_path.write_text(json.dumps({
        "$comment": "Generated by replica/export.py. Every file in replica/site, where it came from, and its hash.",
        "origin": origin,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {kind: sum(1 for r in records if r["kind"] == kind)
                   for kind in ("page", "404", "feed", "sitemap", "robots", "asset")},
        "files": records,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origin", default=ORIGIN)
    parser.add_argument("--out", type=Path, default=HERE / "site")
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--form", type=Path, default=HERE / "form.html")
    args = parser.parse_args(argv)
    try:
        print(f"exporting {args.origin} -> {args.out}")
        run(args.origin, args.out, args.manifest, args.form)
    except ExportError as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
