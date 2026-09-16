# Like-for-like replica of thehenley.com.au — implementation plan

**Status — 2026-09-17:** Tasks 1–13, including 11b, are implemented, landed and verified on dev. Production cutover remains pending Scott’s review and the runbook prerequisites. See [verification and deployment evidence](../../2026-09-17-replica-verification.md); historical step checkboxes below are not the current status.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve a static, self-contained copy of the live WordPress site from nginx, with the contact form posting to the existing enquiry receiver, verified indistinguishable from today's site, deployed to dev.thehenley.com.au as the cutover candidate.

**Architecture:** A committed Python script fetches every page, feed, sitemap and same-origin asset from `https://thehenley.com.au`, strips only WordPress discovery tags and the Gravity Forms JavaScript, swaps the contact form for a plain one on Gravity's own CSS classes, and writes the result to `replica/site/`. A build-less Docker image serves that tree with the existing nginx redirects and a replica-specific security policy. The existing receiver, runbook, URL gate and proxy checks are reused unchanged or with one small flag each.

**Tech Stack:** Python 3.11 standard library (no new venv: tests run with `forms/.venv`, which has pytest), nginx:alpine, Docker Compose, Node 22 via `scripts/with-node.sh`, Playwright 1.63 and sharp (already a devDependency) for the fidelity and console checks.

**Spec:** `docs/superpowers/specs/2026-09-16-legacy-replica-design.md` — read it first; the sections below cite it as §n.

## Global Constraints

- Work only in the worktree `/mnt/persistent/git/worktrees/henley-website/replica` on branch `stream/replica`. Never `git checkout` in `/mnt/persistent/dev/henley-website`.
- Nothing under `src/`, `astro.config.mjs`, `deploy/Dockerfile`, `deploy/nginx.conf` or `deploy/security-headers.conf` is modified. Those belong to the redesign stream (§"Why this exists").
- The export is fetched from the live origin `https://thehenley.com.au`. `source/live-capture-2026-09-09/` is immutable and is used only as test fixtures.
- `replica/site/` is committed. Nothing in it is minified, reformatted or re-encoded (§3: "Fidelity beats tidiness").
- Cross-origin references (Google Fonts, Typekit `azk7leu`, Font Awesome kit `6ec9d3cb9f`, GTM `GTM-PGSH3HF7` and `GTM-M3MV9VG`, gtag `GT-TXH3QGV`, Facebook, Instagram, forms.office.com) stay exactly as served (§2).
- The receiver's contract is unchanged: fields `name`, `email`, `phone`, `enquiry_text`, `interest_apartment` (value `Apartment Living`), `interest_aged_care` (value `Private Aged Care`), `page_path`, honeypot `company`; POST to `/api/enquiry`; success is a 303 to `/thank-you/?sent=1` (§4).
- Python tests run as `forms/.venv/bin/python -m pytest replica/tests -q`. Node runs as `scripts/with-node.sh …`.
- Commit at the end of every task, message in the repo's style (a subject line that says what changed and why, a body that explains the non-obvious), ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never run `stream finish`, `--abandon`, `git worktree remove` or `git branch -D`. Landing (`stream land`) is Task 13 and is the last thing done.

---

## File map

| Path | Responsibility |
|---|---|
| `replica/export.py` | Fetch, discover assets, post-process, write the tree and the manifest. Stdlib only. |
| `replica/form.html` | The replacement contact form fragment (§4). |
| `replica/tests/conftest.py` | Puts `replica/` on `sys.path`; loads capture fixtures. |
| `replica/tests/test_export.py` | Unit tests for every post-processing rule, asset discovery and the form swap. |
| `replica/site/` | The committed export. Generated; never hand-edited except as `README.md` describes. |
| `replica/manifest.json` | Every file written, its source URL and sha256. Generated. |
| `replica/README.md` | How to refresh, verify and (rarely) edit. |
| `replica/compare.mjs` | Screenshot fidelity check, live vs candidate (§6.4). |
| `replica/console-check.mjs` | Console errors, failed requests and CSP violations per page (§6.6). |
| `deploy/Dockerfile.replica` | nginx:alpine serving `replica/site`; build arg `SITE_ENV`. |
| `deploy/nginx.replica.conf` | The replica's server config; `deploy/nginx.conf` stays the Astro site's. |
| `deploy/security-headers.replica.conf` | Replica CSP and the other four headers, plus the robots-tag include. |
| `deploy/robots-tag.nonprod.conf`, `deploy/robots-tag.prod.conf` | `X-Robots-Tag` on nonprod only (F05). |
| `deploy/compose.nonprod.yml`, `deploy/compose.prod.yml` | `site` builds `Dockerfile.replica`. |
| `scripts/check-urls.sh` | Gains `--noindex` / `--indexable`. |
| `scripts/check-urls-fixture.sh` | Proves those flags fail when they should. |
| `scripts/check-enquiry-flow.sh` | Gains `SITE_DIR` so it reads the replica's contact page. |
| `docs/runbook-cutover.md`, `docs/decisions.md`, `docs/plan-2026-09-09-website-rebuild.md` | Updated for the split and the build-less deploy. |

Deviations from the spec, decided while planning and recorded here so the spec can be amended in Task 1:

1. The replica gets its own `deploy/nginx.replica.conf` rather than editing `deploy/nginx.conf`. The Astro Dockerfile runs `nginx -t` on `nginx.conf` and needs its `_astro` location; sharing the file would couple the two streams.
2. `X-Robots-Tag` is baked in at image build via `ARG SITE_ENV` and a copied include file, not rendered by envsubst at start. The container runs as the unprivileged `nginx` user, which cannot write `/etc/nginx/conf.d/` at start, so the template mechanism would fail silently.
3. Two more removals: the `Comments Feed` alternate link (the replica does not serve `/comments/feed/`) and Site Kit's `google-adsense-platform-*` meta tags.
4. Yoast's child sitemaps are exported as `/sitemap-pages.xml` and `/sitemap-posts.xml`, because the existing redirect rules send `/page-sitemap.xml` and `/post-sitemap.xml` to the index and keeping the old names would loop.
5. jQuery and two WordPress scripts live under `/wp-includes/js/`, which the existing config answers 410. The replica config serves `/wp-includes/js/` as static files and keeps the 410 for everything else under `/wp-includes/`.
6. Two WordPress nonces embedded in every page's inline config (`"nonce":"…"`) rotate daily. They are normalised to zeros so a refreshed export diffs cleanly; the endpoints they authorise answer 410 on the replica anyway.

---

### Task 1: Scaffold the replica directory, amend the spec, and pin the URL-to-file mapping

**Files:**
- Create: `replica/export.py`, `replica/tests/conftest.py`, `replica/tests/test_export.py`, `replica/README.md`
- Modify: `.gitignore`, `.dockerignore`, `docs/superpowers/specs/2026-09-16-legacy-replica-design.md`

**Interfaces:**
- Produces: `page_file(url_path: str) -> str`, `asset_file(url_path: str) -> str`, module constants `ORIGIN`, `EXTRA_PAGES`, `FEEDS`, `SITEMAPS`, `ROBOTS`, `NOT_FOUND_PROBE`, exception `ExportError`.

- [ ] **Step 1: Ignore rules.** Append to `.gitignore`:

```gitignore

# Replica (stream/replica). The export is committed, including its PNG
# favicons, which the blanket *.png rule above would otherwise drop.
!replica/site/**/*.png
replica/screenshots/
replica/__pycache__/
replica/tests/__pycache__/
```

Append to `.dockerignore`:

```
!replica/site/**/*.png
replica/screenshots/
replica/tests/
```

- [ ] **Step 2: Amend the spec** for the six deviations listed above. In §1 change `deploy/Dockerfile.replica … nginx:alpine serving replica/site — no build stage` to add `deploy/nginx.replica.conf` and the two `robots-tag.*.conf` files. In §5 replace the paragraph beginning "**F05 is fixed here.**" with:

```markdown
**F05 is fixed here.** Nonprod becomes a full duplicate of production, so the
`X-Robots-Tag: noindex, nofollow` header must actually be served. It comes
from the container, not NPM: `Dockerfile.replica` takes `ARG SITE_ENV` and
copies `deploy/robots-tag.${SITE_ENV}.conf` to `/etc/nginx/conf.d/robots-tag.conf`,
which `security-headers.replica.conf` includes — so the header rides with the
other security headers into every location. The nonprod compose file passes
`SITE_ENV: nonprod`; prod passes `prod`, whose file is empty.
`check-urls.sh --noindex` asserts the header is present and `--indexable`
that it is absent.
```

In §5 replace "`deploy/nginx.conf` changes:" with "`deploy/nginx.replica.conf` is a copy of `deploy/nginx.conf` with these changes (the Astro site keeps its own file):" and add a bullet: "`/wp-includes/js/` is served as static files, since jQuery and two WordPress scripts live there; the rest of `/wp-includes/` stays 410." In §3 "Removed" add "the `Comments Feed` alternate link; Site Kit's `google-adsense-platform-*` meta tags; the two rotating `"nonce"` values in inline configuration, normalised to zeros." In §2 add after the sitemaps bullet: "Yoast's child sitemaps are written as `sitemap-pages.xml` and `sitemap-posts.xml` and the index rewritten to name them, because the existing redirects send the old names to the index." Also in §2 replace "(Python 3, stdlib plus `requests` and `beautifulsoup4`, pinned in `replica/requirements.txt`)" with "(Python 3.11, standard library only — a parser would re-serialise markup it must not touch, so the rules are regexes over the served text; tests run with `forms/.venv`, which already has pytest)".

- [ ] **Step 3: Write the failing tests** at `replica/tests/conftest.py`:

```python
"""Test fixtures for the replica export.

The 2026-09-09 capture is the fixture set: real Elementor pages as WordPress
served them, immutable, so every rule is tested against the markup it has to
handle rather than a hand-written approximation of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPLICA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = REPLICA_DIR.parent
CAPTURE = REPO_ROOT / "source/live-capture-2026-09-09/pages"

sys.path.insert(0, str(REPLICA_DIR))


@pytest.fixture(scope="session")
def capture():
    def read(slug: str) -> str:
        return (CAPTURE / f"{slug}.html").read_text(encoding="utf-8")
    return read


@pytest.fixture(scope="session")
def form_html() -> str:
    return (REPLICA_DIR / "form.html").read_text(encoding="utf-8")
```

and `replica/tests/test_export.py`:

```python
"""Tests for replica/export.py — every rule that changes what WordPress served."""
from __future__ import annotations

import pytest

import export


# ── Where each URL lands on disk ─────────────────────────────────────────────

@pytest.mark.parametrize("url_path, expected", [
    ("/", "index.html"),
    ("/contact/", "contact/index.html"),
    ("/news/page/2/", "news/page/2/index.html"),
    ("/how-it-works-the-costs-of-retirement-living/",
     "how-it-works-the-costs-of-retirement-living/index.html"),
])
def test_page_file(url_path, expected):
    assert export.page_file(url_path) == expected


def test_page_file_refuses_a_path_without_trailing_slash():
    # nginx's try_files serves /x/ from x/index.html; a page saved anywhere
    # else would 404 at the address the old site published.
    with pytest.raises(export.ExportError):
        export.page_file("/contact")


@pytest.mark.parametrize("url_path, expected", [
    ("/wp-content/themes/thehenley/style.css", "wp-content/themes/thehenley/style.css"),
    ("/wp-content/themes/thehenley/style.css?ver=1.0.4", "wp-content/themes/thehenley/style.css"),
    ("/wp-includes/js/jquery/jquery.min.js?ver=3.7.1#x", "wp-includes/js/jquery/jquery.min.js"),
])
def test_asset_file_strips_query_and_fragment(url_path, expected):
    assert export.asset_file(url_path) == expected
```

- [ ] **Step 4: Run to verify they fail**

Run: `forms/.venv/bin/python -m pytest replica/tests -q`
Expected: errors — `ModuleNotFoundError: No module named 'export'`.

- [ ] **Step 5: Write the minimal implementation** at `replica/export.py`:

```python
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
```

- [ ] **Step 6: Run to verify they pass**

Run: `forms/.venv/bin/python -m pytest replica/tests -q`
Expected: `7 passed`.

- [ ] **Step 7: Write `replica/README.md`** (first version; Task 12 finishes it):

```markdown
# Replica of thehenley.com.au

A static copy of the WordPress site, served by nginx in place of WordPress so
the public sees no change. Spec: `docs/superpowers/specs/2026-09-16-legacy-replica-design.md`.

## Refresh the export

    forms/.venv/bin/python replica/export.py
    git diff --stat replica/

Review the diff before committing: it should show only what changed on the
live site since the last export.

## Tests

    forms/.venv/bin/python -m pytest replica/tests -q
```

- [ ] **Step 8: Commit**

```bash
git add .gitignore .dockerignore replica docs/superpowers/specs/2026-09-16-legacy-replica-design.md
git commit -m "replica: scaffold the export and pin where each address lands on disk"
```

---

### Task 2: Discover same-origin assets in HTML and CSS

**Files:**
- Modify: `replica/export.py`
- Test: `replica/tests/test_export.py`

**Interfaces:**
- Produces: `find_assets(text: str) -> set[str]` (URL paths, no query, under `/wp-content/` or `/wp-includes/`), `find_css_assets(css_text: str, css_path: str) -> set[str]`.

- [ ] **Step 1: Write the failing tests** (append to `test_export.py`):

```python
# ── Asset discovery ──────────────────────────────────────────────────────────

def test_find_assets_reads_every_syntax_elementor_uses():
    text = """
    <link rel='stylesheet' href='https://thehenley.com.au/wp-content/themes/thehenley/style.css?ver=1.0.4' />
    <script src="https://thehenley.com.au/wp-includes/js/jquery/jquery.min.js?ver=3.7.1"></script>
    <img src="https://thehenley.com.au/wp-content/uploads/2023/04/a.jpg"
         srcset="https://thehenley.com.au/wp-content/uploads/2023/04/a-300x200.jpg 300w, https://thehenley.com.au/wp-content/uploads/2023/04/a-768x512.jpg 768w"
         data-lazy-src="https://thehenley.com.au/wp-content/uploads/2023/04/b.jpg">
    <div data-settings='{"background_image":{"url":"https:\\/\\/thehenley.com.au\\/wp-content\\/uploads\\/2023\\/04\\/bg.jpeg"}}'></div>
    <div style="background-image:url(https://thehenley.com.au/wp-content/uploads/2023/04/c.png);"></div>
    <a href="/wp-content/uploads/2026/07/fees.pdf">Fees</a>
    <a href="https://thehenley.com.au/contact/">not an asset</a>
    <a href="https://thehenley.com.au/wp-admin/admin-ajax.php">not an asset</a>
    """
    assert export.find_assets(text) == {
        "/wp-content/themes/thehenley/style.css",
        "/wp-includes/js/jquery/jquery.min.js",
        "/wp-content/uploads/2023/04/a.jpg",
        "/wp-content/uploads/2023/04/a-300x200.jpg",
        "/wp-content/uploads/2023/04/a-768x512.jpg",
        "/wp-content/uploads/2023/04/b.jpg",
        "/wp-content/uploads/2023/04/bg.jpeg",
        "/wp-content/uploads/2023/04/c.png",
        "/wp-content/uploads/2026/07/fees.pdf",
    }


def test_find_assets_on_the_captured_home_page(capture):
    found = export.find_assets(capture("home"))
    assert "/wp-content/themes/thehenley/style.css" in found
    assert "/wp-includes/js/jquery/jquery.min.js" in found
    assert "/wp-content/uploads/2023/04/home1.jpeg" in found
    assert "/wp-content/plugins/elementor/assets/css/frontend.min.css" in found
    assert not any(p.endswith(".php") for p in found)
    assert not any("?" in p for p in found)


def test_find_css_assets_resolves_relative_references():
    css = """
    @font-face { src: url('../fonts/eicons.woff2?ver=5.35.0') format('woff2'), url(../fonts/eicons.ttf); }
    .hero { background: url("https://thehenley.com.au/wp-content/uploads/2023/04/hero.jpg"); }
    .icon { background: url(data:image/svg+xml;base64,AAAA); }
    .ext { background: url(https://fonts.gstatic.com/x.woff2); }
    @import url("/wp-content/plugins/elementor/assets/lib/x.css");
    """
    found = export.find_css_assets(css, "/wp-content/plugins/elementor/assets/lib/eicons/css/elementor-icons.min.css")
    assert found == {
        "/wp-content/plugins/elementor/assets/lib/eicons/fonts/eicons.woff2",
        "/wp-content/plugins/elementor/assets/lib/eicons/fonts/eicons.ttf",
        "/wp-content/uploads/2023/04/hero.jpg",
        "/wp-content/plugins/elementor/assets/lib/x.css",
    }
```

- [ ] **Step 2: Run to verify they fail**

Run: `forms/.venv/bin/python -m pytest replica/tests -q -k find_`
Expected: FAIL with `AttributeError: module 'export' has no attribute 'find_assets'`.

- [ ] **Step 3: Implement** (append to `export.py`):

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `forms/.venv/bin/python -m pytest replica/tests -q`
Expected: `10 passed`. If the home-page test fails on `frontend.min.css`, print `sorted(found)[:20]` and fix the regex character class; do not loosen the assertion.

- [ ] **Step 5: Commit**

```bash
git add replica
git commit -m "replica: find every same-origin asset a page or stylesheet references"
```

---

### Task 3: The post-processing rules — remove WordPress discovery, keep everything else, make references root-relative

**Files:**
- Modify: `replica/export.py`
- Test: `replica/tests/test_export.py`

**Interfaces:**
- Produces: `remove_wordpress_tags(text) -> str`, `normalise_nonces(text) -> str`, `rewrite_origin(text) -> str`, `rewrite_css(text) -> str`, `clean_html(text) -> str` (the three HTML steps in order).

- [ ] **Step 1: Write the failing tests** (append):

```python
# ── What is removed, and what must survive ───────────────────────────────────

REMOVED_MARKERS = [
    'rel="https://api.w.org/"',
    'rel="EditURI"',
    "rel='shortlink'",
    "json+oembed",
    "xml+oembed",
    'title="JSON" type="application/json"',
    "Comments Feed",
    'name="generator"',
    "google-adsense-platform",
    "wp-emoji-styles-inline-css",
    "_wpemojiSettings",
]

KEPT_MARKERS = [
    "GTM-PGSH3HF7",
    "GTM-M3MV9VG",
    "gtag/js?id=GT-TXH3QGV",
    'rel="canonical" href="https://thehenley.com.au/"',
    'class="yoast-schema-graph"',
    '<meta property="og:url" content="https://thehenley.com.au/" />',
    'rel="alternate" type="application/rss+xml" title="The Henley on Broadwater &raquo; Feed"',
    "elementor-frontend-css",
    "use.typekit.net/azk7leu.css",
    "kit.fontawesome.com/6ec9d3cb9f.js",
    "wp-rocket/assets/js/lazyload",  # WP Rocket's lazy-load JS stays; the images depend on it
]


def test_remove_wordpress_tags_on_the_captured_home_page(capture):
    cleaned = export.remove_wordpress_tags(capture("home"))
    for marker in REMOVED_MARKERS:
        assert marker not in cleaned, marker
    for marker in KEPT_MARKERS:
        assert marker in cleaned, marker


def test_remove_wordpress_tags_leaves_the_body_untouched(capture):
    original = capture("dining")
    cleaned = export.remove_wordpress_tags(original)
    body = lambda t: t[t.index("<body"):]
    assert body(cleaned) == body(original)


def test_nonces_are_normalised():
    text = 'a {"nonce":"1066da9f37"} b {"nonce":"26d020178b"} c'
    assert export.normalise_nonces(text) == 'a {"nonce":"0000000000"} b {"nonce":"0000000000"} c'


# ── Root-relative references ─────────────────────────────────────────────────

def test_rewrite_origin_makes_assets_and_links_relative_but_keeps_metadata_absolute():
    text = """<head>
<link rel="canonical" href="https://thehenley.com.au/dining/" />
<meta property="og:image" content="https://thehenley.com.au/wp-content/uploads/2023/04/home1.jpeg" />
<link rel="alternate" type="application/rss+xml" title="Feed" href="https://thehenley.com.au/feed/" />
<script type="application/ld+json">{"@id":"https://thehenley.com.au/#website"}</script>
<link rel='stylesheet' href='https://thehenley.com.au/wp-content/themes/thehenley/style.css?ver=1.0.4' />
<link rel="preload" as="image" href="https://thehenley.com.au/wp-content/uploads/2023/04/home1.jpeg">
</head><body>
<a href="https://thehenley.com.au"><img src="https://thehenley.com.au/wp-content/uploads/logo.svg"></a>
<a href="https://thehenley.com.au/contact/">Contact</a>
<img data-lazy-srcset="https://thehenley.com.au/wp-content/uploads/a-300.jpg 300w, https://thehenley.com.au/wp-content/uploads/a-768.jpg 768w">
<script>var cfg = {"home_url":"https:\\/\\/thehenley.com.au","ajaxurl":"https:\\/\\/thehenley.com.au\\/wp-admin\\/admin-ajax.php"};</script>
<div data-settings='{"background_image":{"url":"https:\\/\\/thehenley.com.au\\/wp-content\\/uploads\\/bg.jpeg"}}'></div>
</body>"""
    out = export.rewrite_origin(text)
    assert '<link rel="canonical" href="https://thehenley.com.au/dining/" />' in out
    assert 'content="https://thehenley.com.au/wp-content/uploads/2023/04/home1.jpeg"' in out
    assert 'href="https://thehenley.com.au/feed/"' in out
    assert '"@id":"https://thehenley.com.au/#website"' in out
    assert "href='/wp-content/themes/thehenley/style.css?ver=1.0.4'" in out
    assert 'href="/wp-content/uploads/2023/04/home1.jpeg"' in out
    assert '<a href="/"><img src="/wp-content/uploads/logo.svg"></a>' in out
    assert '<a href="/contact/">' in out
    assert 'data-lazy-srcset="/wp-content/uploads/a-300.jpg 300w, /wp-content/uploads/a-768.jpg 768w"' in out
    # JSON-escaped *site* URLs in inline configuration are left alone: code
    # concatenates onto them, and their endpoints answer 410 here regardless.
    # JSON-escaped *asset* URLs (Elementor's data-settings backgrounds and its
    # Pro modules) are relativised, or dev would fetch them from production.
    assert '"home_url":"https:\\/\\/thehenley.com.au"' in out
    assert '"ajaxurl":"https:\\/\\/thehenley.com.au\\/wp-admin\\/admin-ajax.php"' in out
    assert '{"url":"\\/wp-content\\/uploads\\/bg.jpeg"}' in out


def test_rewrite_origin_on_the_captured_contact_page_leaves_no_absolute_asset_outside_metadata(capture):
    out = export.rewrite_origin(capture("contact"))
    stripped = export.PROTECTED_RE.sub("", out)
    assert "https://thehenley.com.au/wp-content" not in stripped
    assert "https://thehenley.com.au/wp-includes" not in stripped
    assert "https:\\/\\/thehenley.com.au\\/wp-content" not in stripped


def test_rewrite_css_makes_every_absolute_reference_relative():
    css = ".a{background:url(https://thehenley.com.au/wp-content/uploads/x.jpg)} .b{background:url('https://thehenley.com.au/wp-content/uploads/y.jpg')}"
    assert export.rewrite_css(css) == ".a{background:url(/wp-content/uploads/x.jpg)} .b{background:url('/wp-content/uploads/y.jpg')}"
```

- [ ] **Step 2: Run to verify they fail**

Run: `forms/.venv/bin/python -m pytest replica/tests -q -k "remove or nonce or rewrite"`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement** (append):

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `forms/.venv/bin/python -m pytest replica/tests -q`
Expected: `17 passed`. If `test_remove_wordpress_tags_on_the_captured_home_page` fails on a KEPT marker, a removal regex is too greedy: print which `REMOVALS` entry changes the length of the text and tighten that one pattern.

- [ ] **Step 5: Commit**

```bash
git add replica
git commit -m "replica: strip only what needs WordPress behind it, and make references root-relative"
```

---

### Task 4: The contact form

**Files:**
- Create: `replica/form.html`
- Modify: `replica/export.py`
- Test: `replica/tests/test_export.py`

**Interfaces:**
- Produces: `GFORM_BLOCK_RE`, `replace_form(text: str, form_html: str) -> str` (raises `ExportError` when no Gravity Forms block is present).

- [ ] **Step 1: Write the failing tests** (append):

```python
# ── The contact form ─────────────────────────────────────────────────────────

import re as _re


def _inputs(form: str) -> dict[str, str]:
    """name -> value for every input and textarea in a form."""
    found = {}
    for tag in _re.findall(r"<(?:input|textarea)\b[^>]*>", form):
        name = _re.search(r"\bname=['\"]([^'\"]+)['\"]", tag)
        value = _re.search(r"\bvalue=['\"]([^'\"]*)['\"]", tag)
        if name:
            found[name.group(1)] = value.group(1) if value else ""
    return found


def test_replace_form_swaps_the_gravity_form_for_the_receivers(capture, form_html):
    out = export.clean_html(export.replace_form(capture("contact"), form_html))

    forms = _re.findall(r"<form\b[^>]*>.*?</form>", out, _re.S)
    assert len(forms) == 1
    form = forms[0]
    assert _re.search(r"<form\b[^>]*\baction=['\"]/api/enquiry['\"]", form)
    assert _re.search(r"<form\b[^>]*\bmethod=['\"]post['\"]", form, _re.I)

    inputs = _inputs(form)
    assert set(inputs) == {"name", "email", "phone", "interest_apartment",
                           "interest_aged_care", "enquiry_text", "company", "page_path"}
    assert inputs["interest_apartment"] == "Apartment Living"
    assert inputs["interest_aged_care"] == "Private Aged Care"
    assert inputs["page_path"] == "/contact/"
    assert "referral_source" not in form
    assert "How did you hear about us" not in out

    # Gravity's CSS stays so the form looks the same; its JS and iframe go.
    assert _re.search(r"<link\b[^>]*plugins/gravityforms/[^>]*\.css", out)
    assert "gform_ajax_frame" not in out
    for script in _re.findall(r"<script\b[^>]*>.*?</script>", out, _re.S):
        assert "gform" not in script
    assert "gravityformsrecaptcha" not in out

    # The honeypot is hidden by Gravity's own class, not by anything new.
    assert _re.search(r"gform_validation_container[^>]*>.*?name=['\"]company['\"]", form, _re.S)


def test_replace_form_refuses_a_page_without_a_gravity_form(capture, form_html):
    with pytest.raises(export.ExportError):
        export.replace_form(capture("home"), form_html)


def test_only_the_contact_page_embeds_a_form(capture):
    for slug in ("home", "dining", "location", "thank-you", "news", "privacy-policy"):
        assert not export.GFORM_BLOCK_RE.search(capture(slug)), slug
```

- [ ] **Step 2: Run to verify they fail**

Run: `forms/.venv/bin/python -m pytest replica/tests -q -k form`
Expected: FAIL (`form.html` missing, then `AttributeError`).

- [ ] **Step 3: Write `replica/form.html`.** The classes are Gravity Forms' own so the shipped stylesheet styles it identically. Single quotes and ids match the original so any selector the theme's child CSS uses still applies. The one visible difference is that `required` now uses the browser's validation rather than Gravity's inline messages.

```html
<div class='gform_wrapper gravity-theme gform-theme--no-framework' data-form-theme='gravity-theme' data-form-index='0' id='gform_wrapper_1'><div id='gf_1' class='gform_anchor' tabindex='-1'></div>
                        <div class='gform_heading'>
                            <p class='gform_description'></p>
							<p class='gform_required_legend'></p>
                        </div><form method='post' id='gform_1' action='/api/enquiry'>
                        <div class='gform-body gform_body'><div id='gform_fields_1' class='gform_fields top_label form_sublabel_below description_below validation_below'><div id="field_1_1" class="gfield gfield--type-text gfield_contains_required field_sublabel_below gfield--no-description field_description_below field_validation_below gfield_visibility_visible"><label class='gfield_label gform-field-label' for='input_1_1'>Name<span class="gfield_required"><span class="gfield_required gfield_required_asterisk">*</span></span></label><div class='ginput_container ginput_container_text'><input name='name' id='input_1_1' type='text' value='' class='large' required aria-required="true" autocomplete='name' /></div></div><div id="field_1_4" class="gfield gfield--type-email gfield--width-half gfield_contains_required field_sublabel_below gfield--no-description field_description_below field_validation_below gfield_visibility_visible"><label class='gfield_label gform-field-label' for='input_1_4'>Email<span class="gfield_required"><span class="gfield_required gfield_required_asterisk">*</span></span></label><div class='ginput_container ginput_container_email'>
                            <input name='email' id='input_1_4' type='email' value='' class='large' required aria-required="true" autocomplete='email' />
                        </div></div><div id="field_1_3" class="gfield gfield--type-phone gfield--width-half field_sublabel_below gfield--no-description field_description_below field_validation_below gfield_visibility_visible"><label class='gfield_label gform-field-label' for='input_1_3'>Phone</label><div class='ginput_container ginput_container_phone'><input name='phone' id='input_1_3' type='tel' value='' class='large' autocomplete='tel' /></div></div><fieldset id="field_1_6" class="gfield gfield--type-checkbox gfield--type-choice gfield--width-full field_sublabel_below gfield--no-description field_description_below field_validation_below gfield_visibility_visible"><legend class='gfield_label gform-field-label gfield_label_before_complex' >How can we help?</legend><div class='ginput_container ginput_container_checkbox'><div class='gfield_checkbox ' id='input_1_6'><div class='gchoice gchoice_1_6_1'>
								<input class='gfield-choice-input' name='interest_apartment' type='checkbox'  value='Apartment Living'  id='choice_1_6_1'   />
								<label for='choice_1_6_1' id='label_1_6_1' class='gform-field-label gform-field-label--type-inline'>Apartment Living</label>
							</div><div class='gchoice gchoice_1_6_2'>
								<input class='gfield-choice-input' name='interest_aged_care' type='checkbox'  value='Private Aged Care'  id='choice_1_6_2'   />
								<label for='choice_1_6_2' id='label_1_6_2' class='gform-field-label gform-field-label--type-inline'>Private Aged Care</label>
							</div></div></div></fieldset><div id="field_1_7" class="gfield gfield--type-textarea gfield--width-full field_sublabel_below gfield--no-description field_description_below field_validation_below gfield_visibility_visible"><label class='gfield_label gform-field-label' for='input_1_7'>Your enquiry</label><div class='ginput_container ginput_container_textarea'><textarea name='enquiry_text' id='input_1_7' class='textarea small' rows='10' cols='50'></textarea></div></div><div id="field_1_8" class="gfield gfield--type-honeypot gform_validation_container field_sublabel_below gfield--has-description field_description_below field_validation_below gfield_visibility_visible"><label class='gfield_label gform-field-label' for='input_1_8'>Company</label><div class='ginput_container'><input name='company' id='input_1_8' type='text' value='' autocomplete='off' tabindex='-1'/></div><div class='gfield_description' id='gfield_description_1_8'>This field is for validation purposes and should be left unchanged.</div></div></div></div>
        <div class='gform-footer gform_footer top_label'> <input type='submit' id='gform_submit_button_1' class='gform_button button' value='Submit'  /> <input type='hidden' name='page_path' value='/contact/' />
        </div>
                        </form>
                        </div>
```

- [ ] **Step 4: Implement `replace_form`** (append to `export.py`):

```python
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
```

- [ ] **Step 5: Run to verify they pass**

Run: `forms/.venv/bin/python -m pytest replica/tests -q`
Expected: `20 passed`.

- [ ] **Step 6: Commit**

```bash
git add replica
git commit -m "replica: the contact form, on Gravity's classes, posting to the receiver"
```

---

### Task 5: Sitemap rewriting, fetching, and the orchestration that writes the tree

**Files:**
- Modify: `replica/export.py`
- Test: `replica/tests/test_export.py`

**Interfaces:**
- Produces: `rewrite_sitemap(text) -> str`, `fetch(url, expect) -> bytes`, `run(origin, out, manifest_path, form_path) -> None`, `main(argv) -> int`.

- [ ] **Step 1: Write the failing tests** (append):

```python
# ── Sitemaps ─────────────────────────────────────────────────────────────────

def test_rewrite_sitemap_renames_children_and_localises_the_stylesheet():
    index = ('<?xml version="1.0" encoding="UTF-8"?><?xml-stylesheet type="text/xsl" '
             'href="https://thehenley.com.au/main-sitemap.xsl"?>'
             '<sitemapindex><sitemap><loc>https://thehenley.com.au/post-sitemap.xml</loc></sitemap>'
             '<sitemap><loc>https://thehenley.com.au/page-sitemap.xml</loc></sitemap></sitemapindex>')
    out = export.rewrite_sitemap(index)
    assert 'href="/main-sitemap.xsl"' in out
    assert "<loc>https://thehenley.com.au/sitemap-posts.xml</loc>" in out
    assert "<loc>https://thehenley.com.au/sitemap-pages.xml</loc>" in out
    assert "post-sitemap.xml" not in out and "page-sitemap.xml" not in out


def test_rewrite_sitemap_keeps_page_locations_absolute():
    pages = ('<?xml version="1.0"?><urlset><url><loc>https://thehenley.com.au/dining/</loc></url></urlset>')
    assert export.rewrite_sitemap(pages) == pages


# ── The run, against a fake origin ───────────────────────────────────────────

def test_run_writes_pages_assets_feeds_and_a_manifest(tmp_path, monkeypatch, capture, form_html):
    """Drive run() with a fake fetch so the whole orchestration is exercised
    without the network: page files land where nginx expects, assets are
    followed through CSS, and the manifest hashes what was written."""
    contact = capture("contact")
    home = capture("home")
    responses = {
        "/": (200, home.encode()),
        "/contact/": (200, contact.encode()),
        "/news/page/2/": (200, home.replace('href="https://thehenley.com.au/"', 'href="https://thehenley.com.au/news/page/2/"', 1).encode()),
        export.NOT_FOUND_PROBE: (404, b"<html><head><link rel=\"canonical\" href=\"https://thehenley.com.au/404/\" /></head><body>404</body></html>"),
        "/feed/": (200, b"<?xml version=\"1.0\"?><rss/>"),
        "/news/feed/": (200, b"<?xml version=\"1.0\"?><rss/>"),
        "/sitemap_index.xml": (200, b"<?xml version=\"1.0\"?><sitemapindex><sitemap><loc>https://thehenley.com.au/page-sitemap.xml</loc></sitemap></sitemapindex>"),
        "/page-sitemap.xml": (200, b"<?xml version=\"1.0\"?><urlset/>"),
        "/post-sitemap.xml": (200, b"<?xml version=\"1.0\"?><urlset/>"),
        "/main-sitemap.xsl": (200, b"<xsl/>"),
        "/robots.txt": (200, b"User-agent: *\n"),
    }
    css = b".x{background:url(../img/a.png)}"
    fetched: list[str] = []

    def fake_fetch(url, expect=200):
        path = url[len(export.ORIGIN):]
        fetched.append(path)
        if path in responses:
            status, body = responses[path]
        elif path.endswith(".css"):
            status, body = 200, css
        else:
            status, body = 200, b"binary"
        if status != expect:
            raise export.ExportError(f"{path}: {status}")
        return body

    monkeypatch.setattr(export, "fetch", fake_fetch)
    manifest_source = tmp_path / "manifest-source.json"
    manifest_source.write_text('{"urls":[{"path":"/"},{"path":"/contact/"}]}')
    monkeypatch.setattr(export, "MANIFEST_SOURCE", manifest_source)

    out = tmp_path / "site"
    manifest = tmp_path / "manifest.json"
    export.run(export.ORIGIN, out, manifest, form_html=form_html)

    assert (out / "index.html").exists()
    assert (out / "contact/index.html").exists()
    assert (out / "news/page/2/index.html").exists()
    assert (out / "404.html").exists()
    assert (out / "feed/index.xml").read_bytes() == responses["/feed/"][1]
    assert (out / "sitemap-index.xml").exists() and (out / "sitemap-pages.xml").exists()
    assert (out / "robots.txt").exists()
    assert (out / "wp-content/themes/thehenley/style.css").exists()
    # The CSS's relative image was followed.
    assert (out / "wp-content/themes/img/a.png").exists()
    # Pages went through the whole clean, and the contact page got the form.
    assert "api.w.org" not in (out / "index.html").read_text()
    assert "action='/api/enquiry'" in (out / "contact/index.html").read_text()

    record = json.loads(manifest.read_text())
    files = {entry["file"]: entry for entry in record["files"]}
    assert files["robots.txt"]["sha256"] == hashlib.sha256(b"User-agent: *\n").hexdigest()
    assert files["contact/index.html"]["url"] == "https://thehenley.com.au/contact/"
    assert record["origin"] == export.ORIGIN
    # Every fetch was made once.
    assert len(fetched) == len(set(fetched))
```

Add `import hashlib` and `import json` at the top of the test file.

- [ ] **Step 2: Run to verify they fail**

Run: `forms/.venv/bin/python -m pytest replica/tests -q -k "sitemap or run_writes"`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement** (append to `export.py`):

```python
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
        assets |= find_assets(text)
        write(file, clean_html(text).encode("utf-8"), url_path, "page")
        print(f"  page   {url_path}")

    text = fetch(origin + NOT_FOUND_PROBE, expect=404).decode("utf-8")
    assets |= find_assets(text)
    write("404.html", clean_html(text).encode("utf-8"), NOT_FOUND_PROBE, "404")
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

    pending = sorted(assets)
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
                if extra not in seen:
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `forms/.venv/bin/python -m pytest replica/tests -q`
Expected: `23 passed`.

- [ ] **Step 5: Commit**

```bash
git add replica
git commit -m "replica: fetch the site, follow its stylesheets, write the tree and its manifest"
```

---

### Task 6: Run the export, prove it is deterministic, and commit the site

**Files:**
- Create: `replica/site/**`, `replica/manifest.json`

- [ ] **Step 1: Run the export twice into scratch**

```bash
S=/tmp/claude-1000/-mnt-persistent-git-worktrees-henley-website/dce4057b-ffca-4e5e-b043-55dcab3b5765/scratchpad
forms/.venv/bin/python replica/export.py --out $S/run1 --manifest $S/run1.json
forms/.venv/bin/python replica/export.py --out $S/run2 --manifest $S/run2.json
diff -r $S/run1 $S/run2 && echo "trees identical"
diff <(grep -v fetched_at $S/run1.json) <(grep -v fetched_at $S/run2.json) && echo "manifests identical"
```

Expected: both `identical` lines. If the trees differ, `diff -r` names the file; find the volatile substring, add a normalisation next to `normalise_nonces` with a test, and rerun. Do not proceed with a non-deterministic export.

- [ ] **Step 2: Inspect the run's counts and size**

```bash
python3 -c "import json;m=json.load(open('$S/run1.json'));print(m['counts']);print(sum(f['bytes'] for f in m['files'])//1024//1024,'MB')"
find $S/run1 -name index.html | wc -l      # expect 28 (27 manifest pages + /news/page/2/)
grep -c "action='/api/enquiry'" $S/run1/contact/index.html   # expect 1
grep -l "gform_wrapper" $S/run1/*/index.html $S/run1/index.html   # expect only contact
```

Expected counts: `page` 28, `404` 1, `feed` 2, `sitemap` 4, `robots` 1, assets roughly 180–260. Total under 80 MB. If assets exceed 400 or size exceeds 120 MB, something is being followed that should not be (print the manifest's asset paths grouped by directory) — stop and report rather than commit.

- [ ] **Step 3: Write the real export and commit it**

```bash
forms/.venv/bin/python replica/export.py
git add replica/site replica/manifest.json
git status --short | grep -c '^A' 
git commit -m "replica: the export of thehenley.com.au as served on $(date +%Y-%m-%d)" 
```

The commit body should record the counts from Step 2 and the fact that two consecutive runs were byte-identical.

---

### Task 7: The nginx config, security headers, Dockerfile and compose changes

**Files:**
- Create: `deploy/nginx.replica.conf`, `deploy/security-headers.replica.conf`, `deploy/robots-tag.nonprod.conf`, `deploy/robots-tag.prod.conf`, `deploy/Dockerfile.replica`
- Modify: `deploy/compose.nonprod.yml`, `deploy/compose.prod.yml`

**Interfaces:**
- Produces: image `henley-website:nonprod` / `:prod` built from `Dockerfile.replica` with `--build-arg SITE_ENV`.

- [ ] **Step 1: `deploy/robots-tag.nonprod.conf`**

```nginx
# Nonprod is a full duplicate of production. This header, and the identical
# robots.txt, are what keep it out of the index. Included from
# security-headers.replica.conf so it rides into every location; see F05 in
# docs/plan-2026-09-10-review-remediation.md for why NPM cannot be relied on
# to add it.
add_header X-Robots-Tag "noindex, nofollow" always;
```

`deploy/robots-tag.prod.conf`:

```nginx
# Production is indexable. Deliberately empty; the nonprod variant sets
# X-Robots-Tag. Dockerfile.replica picks this file by SITE_ENV.
```

- [ ] **Step 2: `deploy/security-headers.replica.conf`.** Copy the comment block from `deploy/security-headers.conf` (the nginx inheritance rule is the same), then:

```nginx
# The policy names what the *WordPress-era* pages actually load, which is more
# than the Astro site: Google Fonts (Lato), Adobe Typekit (Quincy CF), the
# Font Awesome Pro kit and its CDN, Elementor's inline scripts and styles,
# WP Rocket's lazy-load placeholders as data: images, and the same Google
# tag, analytics and Ads hosts as before. Verified against every page with
# replica/console-check.mjs; a host missing here fails silently in the
# browser, so that check is the gate, not this comment.
add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data: https://www.googletagmanager.com https://www.google-analytics.com https://www.google.com https://www.google.com.au https://googleads.g.doubleclick.net https://ka-f.fontawesome.com; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://googleads.g.doubleclick.net https://www.googleadservices.com https://kit.fontawesome.com https://ka-f.fontawesome.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://use.typekit.net https://p.typekit.net https://ka-f.fontawesome.com; font-src 'self' data: https://fonts.gstatic.com https://use.typekit.net https://p.typekit.net https://ka-f.fontawesome.com; connect-src 'self' https://www.google-analytics.com https://analytics.google.com https://stats.g.doubleclick.net https://www.googletagmanager.com https://ka-f.fontawesome.com https://p.typekit.net; frame-src https://www.googletagmanager.com https://td.doubleclick.net" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=(), interest-cohort=()" always;
add_header Cross-Origin-Opener-Policy "same-origin" always;

# noindex on nonprod, nothing on prod. Chosen at image build (Dockerfile.replica).
include /etc/nginx/conf.d/robots-tag.conf;
```

- [ ] **Step 3: `deploy/nginx.replica.conf`.** Start from a copy of `deploy/nginx.conf`:

```bash
cp deploy/nginx.conf deploy/nginx.replica.conf
```

Then make exactly these edits:

(a) Replace the opening comment's first line with:

```nginx
#
# thehenley.com.au — the whole server, serving the WordPress-era replica.
#
# The Astro site's config is deploy/nginx.conf; this is its twin for the
# static export in replica/site. Same redirects, same 410s, same headers
# discipline; the differences are that the page assets live under /wp-content/
# and /wp-includes/js/ rather than /_astro/, and there is a sitemap stylesheet.
```

(b) Replace the whole `# ── Static assets` block (the `/_astro/` location and its comment) with:

```nginx
        # ── Static assets ─────────────────────────────────────────────────────
        #
        # Theme, plugin and Elementor files keep their WordPress paths, and
        # their versions are keyed by the ?ver= query string the HTML carries,
        # exactly as before. A year, but not `immutable`: a re-export that
        # changes a file under the same name and version is unusual but not
        # impossible, and a hard refresh should be able to fetch it.
        location ^~ /wp-content/ {
            include /etc/nginx/conf.d/security-headers.conf;
            add_header Cache-Control "public, max-age=31536000";
            try_files $uri =404;
        }

        # jQuery and two WordPress scripts live here. Only the js/ subtree is
        # served; everything else under /wp-includes/ is still 410 below.
        location ^~ /wp-includes/js/ {
            include /etc/nginx/conf.d/security-headers.conf;
            add_header Cache-Control "public, max-age=31536000";
            try_files $uri =404;
        }

        # Yoast's sitemap stylesheet, so a person opening the sitemap sees a
        # table rather than raw XML. Cosmetic; browsers apply it only with an
        # XML content type.
        location = /main-sitemap.xsl {
            include /etc/nginx/conf.d/security-headers.conf;
            types { } default_type text/xml;
            add_header Cache-Control "public, max-age=3600";
        }
```

The `^~ /wp-content/uploads/` and `^~ /documents/` locations above it stay exactly as they are: nginx picks the longest matching prefix, so uploads keep `immutable`.

(c) Under `# ── Bot traffic`, leave every 410 line as it is. The `~* ^/(wp-admin|wp-includes|…)` regex still fires for `/wp-includes/` paths outside `js/`, because a `^~` prefix match stops the regex search only for the paths it matches.

Nothing else changes. `diff deploy/nginx.conf deploy/nginx.replica.conf` should show only the comment and the block replaced in (b).

- [ ] **Step 4: `deploy/Dockerfile.replica`**

```dockerfile
# thehenley.com.au — serve the replica.
#
# No build stage: replica/site is the site, committed, produced by
# replica/export.py. The image is nginx and a directory of files. Nothing in
# it can execute, and nothing in it needs Node, Python or the brand kit.
#
#   docker build -f deploy/Dockerfile.replica --build-arg SITE_ENV=nonprod -t henley-website:nonprod .

FROM nginx:alpine

# nonprod serves X-Robots-Tag: noindex; prod serves nothing extra. Chosen
# here, at build, because the runtime user cannot write /etc/nginx/conf.d
# and an envsubst that fails does so silently.
ARG SITE_ENV=prod

# Runs unprivileged. nginx:alpine ships an `nginx` user; the config listens on
# 8080 rather than 80 so no capability is needed to bind it.
RUN rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /var/cache/nginx/client_body /var/cache/nginx/proxy \
             /var/cache/nginx/fastcgi /var/cache/nginx/uwsgi /var/cache/nginx/scgi \
 && chown -R nginx:nginx /var/cache/nginx

COPY deploy/nginx.replica.conf /etc/nginx/nginx.conf
COPY deploy/redirects.conf deploy/redirects-map.conf /etc/nginx/conf.d/
COPY deploy/security-headers.replica.conf /etc/nginx/conf.d/security-headers.conf
COPY deploy/robots-tag.${SITE_ENV}.conf /etc/nginx/conf.d/robots-tag.conf
COPY replica/site /usr/share/nginx/html

# Fail the build rather than the deploy if the config is malformed. `nginx -t`
# creates the pid file as root; left behind, the runtime user cannot open it.
RUN nginx -t -c /etc/nginx/nginx.conf \
 && rm -f /var/cache/nginx/nginx.pid

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/nginx-health || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 5: Build and run it locally, and run the strict gate against it**

```bash
docker build -f deploy/Dockerfile.replica --build-arg SITE_ENV=nonprod -t henley-replica-local:test .
docker run -d --rm --name henley-replica-local -p 127.0.0.1:8090:8080 henley-replica-local:test
sleep 2
curl -sI http://127.0.0.1:8090/ | grep -i -E 'x-robots-tag|content-security-policy' | cut -c1-80
scripts/check-urls.sh --strict http://127.0.0.1:8090
```

Expected: `X-Robots-Tag: noindex, nofollow` present, and the gate ends `STRICT: every address in the manifest answers correctly` with 0 failed and 0 outstanding. Likely first-run failures and their fixes:
- `/feed/ … not XML`: the feed file is not at `feed/index.xml`, or `index index.html index.xml;` was lost in the copy.
- `/sitemap_index.xml … arrives at the wrong thing`: `sitemap-index.xml` does not begin `<?xml` within 400 bytes; check the Yoast output was written verbatim.
- `/wp-login.php — expected 410`: the `^~ /wp-includes/js/` block was placed above the 410 lines with a broader prefix; narrow it.

Leave the container running for Tasks 8 and 9. Stop it at the end of Task 9 with `docker stop henley-replica-local`.

- [ ] **Step 6: Compose files.** In both `deploy/compose.nonprod.yml` and `deploy/compose.prod.yml`, change the `site` service's `build:` to:

```yaml
    build:
      context: ..
      dockerfile: deploy/Dockerfile.replica
      args:
        SITE_ENV: nonprod      # `prod` in compose.prod.yml
```

and in each header comment delete the two lines `scripts/with-node.sh npm ci` and `scripts/with-node.sh npm run tokens` and the paragraph beginning "`npm run tokens` first, always:", replacing them with:

```
# The site image needs no build step: replica/site is committed. Refresh it
# with `forms/.venv/bin/python replica/export.py` and commit before deploying
# (replica/README.md).
```

- [ ] **Step 7: Verify compose still parses and builds the right thing**

```bash
docker compose --env-file deploy/.env.example -f deploy/compose.nonprod.yml config | grep -A4 'dockerfile'
```

Expected: `dockerfile: deploy/Dockerfile.replica` and `SITE_ENV: nonprod`.

- [ ] **Step 8: Commit**

```bash
git add deploy/nginx.replica.conf deploy/security-headers.replica.conf deploy/robots-tag.*.conf deploy/Dockerfile.replica deploy/compose.nonprod.yml deploy/compose.prod.yml
git commit -m "deploy: a build-less image for the replica, with noindex baked in on nonprod"
```

---

### Task 8: The URL gate asserts the robots header

**Files:**
- Modify: `scripts/check-urls.sh`, `scripts/check-urls-fixture.sh`

- [ ] **Step 1: Add the flags to `check-urls.sh`.** In the option loop add:

```bash
    --noindex) ROBOTS="noindex"; shift ;;
    --indexable) ROBOTS="indexable"; shift ;;
```

initialise `ROBOTS=""` next to `MODE`, pass it through (`ROBOTS="$ROBOTS"` on the `python3 -` line), update the usage comment:

```
#   --noindex    Also require X-Robots-Tag: noindex on every checked page —
#                nonprod is a full duplicate of production and this header is
#                what keeps it out of the index. --indexable requires its
#                absence. Neither: the header is not checked.
```

and after the `# ── Security headers` block, before `# ── Verdict`, add:

```python
# ── Robots header ───────────────────────────────────────────────────────────
#
# Checked on two pages and an asset, because the header is added inside the
# security-headers include and the F05 lesson is that a location declaring
# any add_header of its own silently drops the inherited ones.
robots = os.environ.get("ROBOTS")
if robots:
    print(f"\nrobots header ({robots}):")
    for path in ("/", "/contact/", "/robots.txt"):
        raw = subprocess.run(
            ["curl", "-sSI", "--max-time", TIMEOUT, f"{base}{path}"],
            capture_output=True, text=True,
        ).stdout.lower()
        present = "x-robots-tag: noindex" in raw
        if robots == "noindex":
            record(present, f"{path} carries X-Robots-Tag: noindex")
        else:
            record(not present, f"{path} carries no X-Robots-Tag", "x-robots-tag present")
```

- [ ] **Step 2: Run against the local container from Task 7**

```bash
scripts/check-urls.sh --strict --noindex http://127.0.0.1:8090 | tail -8
scripts/check-urls.sh --strict --indexable http://127.0.0.1:8090 | grep -E 'FAIL|NOT READY'
```

Expected: the first passes with three more green checks; the second reports three `FAIL … x-robots-tag present` lines and `STRICT: NOT READY`.

- [ ] **Step 3: Teach the fixture.** In `scripts/check-urls-fixture.sh`, inside the Python fixture: add `"X-Robots-Tag": "noindex, nofollow",` to `SECURITY_HEADERS`, and a new case:

```python
elif BREAK == "indexable-nonprod":
    SECURITY_HEADERS.pop("X-Robots-Tag")
```

In the shell part, after the `expect_failure wordpress-path-404 …` line, add:

```bash
# ── The robots header, both ways ────────────────────────────────────────────
echo
echo "the robots header:"
start_fixture ""
if scripts/check-urls.sh --strict --noindex "http://127.0.0.1:$PORT" >"$WORK/noindex.log" 2>&1; then
  check ok "--noindex passes when the header is there"
else
  check no "--noindex failed against a site that sends the header"
fi
start_fixture "indexable-nonprod"
if scripts/check-urls.sh --strict --noindex "http://127.0.0.1:$PORT" >"$WORK/indexable.log" 2>&1; then
  check no "--noindex passed a site without the header"
elif grep -q "X-Robots-Tag: noindex" "$WORK/indexable.log"; then
  check ok "--noindex fails when the header is missing"
else
  check no "--noindex failed, but not for the header"
fi
start_fixture ""
if scripts/check-urls.sh --strict --indexable "http://127.0.0.1:$PORT" >"$WORK/prod-noindex.log" 2>&1; then
  check no "--indexable passed a site that sends noindex"
else
  grep -q "x-robots-tag present" "$WORK/prod-noindex.log" \
    && check ok "--indexable fails when noindex leaks into production" \
    || check no "--indexable failed, but not for the header"
fi
```

- [ ] **Step 4: Run the fixture**

Run: `scripts/check-urls-fixture.sh 2>&1 | tail -12`
Expected: three new `ok` lines and the closing `url gate: strict fails on every defect it is supposed to catch, and passes a complete site`.

- [ ] **Step 5: Commit**

```bash
git add scripts/check-urls.sh scripts/check-urls-fixture.sh
git commit -m "check-urls: assert the robots header, and prove the assertion fails when it should"
```

---

### Task 9: The enquiry flow check reads the replica's contact page

**Files:**
- Modify: `scripts/check-enquiry-flow.sh`

- [ ] **Step 1: Add `SITE_DIR`.** After `PORT="${PORT:-8099}"` add:

```bash
# Which built site to read the form from. `dist` is the Astro build (built on
# demand); `replica/site` is the committed export, never built here.
SITE_DIR="${SITE_DIR:-dist}"
```

Replace the build guard with:

```bash
[[ -f "$SITE_DIR/contact/index.html" ]] || {
  [[ "$SITE_DIR" == "dist" ]] || { echo "$SITE_DIR/contact/index.html is missing" >&2; exit 1; }
  echo "building the site ..."
  scripts/with-node.sh npm run build >/dev/null
}
```

Pass `SITE_DIR="$SITE_DIR"` on the `python -` line, and in the Python change the two `dist/contact/index.html` references to `os.environ["SITE_DIR"] + "/contact/index.html"`. `form.html` uses single quotes, as Gravity does, and puts `type=` between `name=` and `value=`, so replace these four regexes exactly:

```python
form = re.search(r"<form[^>]*action=[\"']/api/enquiry[\"'][^>]*>(.*?)</form>", page, re.S)
fields = re.findall(r"<(?:input|textarea)[^>]*\bname=[\"']([^\"']+)[\"']", form.group(1))
action = re.search(r"<form[^>]*action=[\"']([^\"']+)[\"']", page).group(1)
method = re.search(r"<form[^>]*method=[\"']([^\"']+)[\"']", page).group(1)
values = dict(re.findall(r"name=[\"'](interest_[a-z_]+)[\"'][^>]*\bvalue=[\"']([^\"']+)[\"']", form.group(1)))
```

Update the usage line to `# Usage: scripts/check-enquiry-flow.sh   (SITE_DIR=replica/site for the replica; builds dist/ if missing otherwise)`.

- [ ] **Step 2: Run it against the replica, and against the Astro build to prove nothing regressed**

```bash
SITE_DIR=replica/site scripts/check-enquiry-flow.sh | grep -E 'FAIL|fields in|passed|failed'
scripts/check-enquiry-flow.sh | grep -E 'FAIL|passed|failed'    # builds dist/ (a quarter hour cold)
docker stop henley-replica-local
```

Expected: no `FAIL` lines from either; the first prints `fields in the built form: ['company', 'email', 'enquiry_text', 'interest_aged_care', 'interest_apartment', 'name', 'page_path', 'phone']`.

- [ ] **Step 3: Commit**

```bash
git add scripts/check-enquiry-flow.sh
git commit -m "check-enquiry-flow: read the form from the replica when asked"
```

---

### Task 10: Fidelity — screenshot every page on live and candidate and diff them

**Files:**
- Create: `replica/compare.mjs`
- Modify: `package.json`, `package-lock.json` (adds `playwright` as a devDependency)

- [ ] **Step 1: Install Playwright into the repo**

```bash
scripts/with-node.sh npm install --save-dev --save-exact playwright@1.63.0
scripts/with-node.sh npx playwright install chromium
```

The second line is a no-op if `~/.cache/ms-playwright` already holds the matching build.

- [ ] **Step 2: Write `replica/compare.mjs`**

```javascript
#!/usr/bin/env node
/**
 * compare.mjs — is the candidate indistinguishable from the live site?
 *
 * Screenshots every page in the migration manifest on two origins at two
 * widths, diffs the pixels, and reports the share that differ. Expected
 * differences are dynamic: the lazy-load placeholders mid-fade, the year in
 * the footer once it rolls, and the contact form (four fields, not seven).
 * Everything else is a defect until explained.
 *
 *   scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au https://dev.thehenley.com.au
 *   scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au http://127.0.0.1:8090 --threshold 0.5
 *
 * Writes replica/screenshots/<slug>-<width>-{live,candidate,diff}.png (gitignored)
 * and prints a table. Exits 1 if any page exceeds the threshold.
 */
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright';
import sharp from 'sharp';

const [liveBase, candidateBase, ...rest] = process.argv.slice(2);
if (!liveBase || !candidateBase) {
  console.error('usage: compare.mjs <live-origin> <candidate-origin> [--threshold pct] [--only /path/]');
  process.exit(2);
}
const flag = (name, fallback) => { const i = rest.indexOf(name); return i >= 0 ? rest[i + 1] : fallback; };
const threshold = Number(flag('--threshold', '0.5'));
const only = flag('--only', null);

const manifest = JSON.parse(readFileSync('source/migration-manifest.json', 'utf8'));
const paths = [...manifest.urls.map((u) => u.path), '/news/page/2/'].filter((p) => !only || p === only);
const widths = [390, 1280];
mkdirSync('replica/screenshots', { recursive: true });

const slug = (p) => (p === '/' ? 'home' : p.replace(/^\/|\/$/g, '').replace(/\//g, '_'));

async function shoot(browser, base, path, width) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(base + path, { waitUntil: 'networkidle', timeout: 60000 });
  // Freeze what moves, and trigger every lazy-loaded image by walking the page.
  await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }' });
  const height = await page.evaluate(() => document.body.scrollHeight);
  for (let y = 0; y < height; y += 600) {
    await page.evaluate((y) => window.scrollTo(0, y), y);
    await page.waitForTimeout(120);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  const png = await page.screenshot({ fullPage: true });
  await context.close();
  return png;
}

async function diff(a, b) {
  const [ia, ib] = await Promise.all([a, b].map((buf) => sharp(buf).ensureAlpha().raw().toBuffer({ resolveWithObject: true })));
  const width = Math.max(ia.info.width, ib.info.width);
  const height = Math.max(ia.info.height, ib.info.height);
  const pad = (img) => sharp(img.data, { raw: { width: img.info.width, height: img.info.height, channels: 4 } }).extend({
    right: width - img.info.width, bottom: height - img.info.height, background: { r: 255, g: 0, b: 255, alpha: 1 },
  }).raw().toBuffer();
  const [pa, pb] = await Promise.all([pad(ia), pad(ib)]);
  const out = Buffer.alloc(width * height * 4);
  let differing = 0;
  for (let i = 0; i < width * height; i += 1) {
    const o = i * 4;
    const delta = Math.max(Math.abs(pa[o] - pb[o]), Math.abs(pa[o + 1] - pb[o + 1]), Math.abs(pa[o + 2] - pb[o + 2]));
    if (delta > 32) {
      differing += 1;
      out[o] = 255; out[o + 1] = 0; out[o + 2] = 0; out[o + 3] = 255;
    } else {
      const grey = Math.round(200 + pa[o] * 0.2);
      out[o] = grey; out[o + 1] = grey; out[o + 2] = grey; out[o + 3] = 255;
    }
  }
  const diffPng = await sharp(out, { raw: { width, height, channels: 4 } }).png().toBuffer();
  return { pct: (100 * differing) / (width * height), heightA: ia.info.height, heightB: ib.info.height, diffPng };
}

const browser = await chromium.launch();
const rows = [];
let failed = 0;
for (const path of paths) {
  for (const width of widths) {
    const [live, candidate] = await Promise.all([shoot(browser, liveBase, path, width), shoot(browser, candidateBase, path, width)]);
    const result = await diff(live, candidate);
    const name = `${slug(path)}-${width}`;
    writeFileSync(`replica/screenshots/${name}-live.png`, live);
    writeFileSync(`replica/screenshots/${name}-candidate.png`, candidate);
    writeFileSync(`replica/screenshots/${name}-diff.png`, result.diffPng);
    const verdict = result.pct <= threshold ? 'ok' : 'REVIEW';
    if (verdict === 'REVIEW') failed += 1;
    rows.push({ path, width, pct: result.pct.toFixed(2), heights: `${result.heightA}/${result.heightB}`, verdict });
    console.log(`${verdict.padEnd(7)} ${String(width).padStart(4)}  ${result.pct.toFixed(2).padStart(6)}%  ${result.heightA}/${result.heightB}  ${path}`);
  }
}
await browser.close();
console.log(`\n${rows.length - failed} within ${threshold}%, ${failed} to review. Screenshots in replica/screenshots/.`);
process.exit(failed ? 1 : 0);
```

- [ ] **Step 3: Run it against the local container**

```bash
docker run -d --rm --name henley-replica-local -p 127.0.0.1:8090:8080 henley-replica-local:test
scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au http://127.0.0.1:8090 2>&1 | tee replica/screenshots/report-local.txt
```

Expected: most pages `ok`. `/contact/` will read `REVIEW` at both widths because the form is shorter; open `replica/screenshots/contact-1280-diff.png` and confirm the red region is only the form. Any other `REVIEW`: open its diff image, identify the cause, and either fix the export (a missed asset shows as a missing image; a missed CSS `url()` as a missing icon or font) with a regression test in `test_export.py`, or, if the cause is genuinely dynamic, note it. Record the final table and every explained difference in the "Evidence" section at the end of this plan.

- [ ] **Step 4: Commit**

```bash
git add replica/compare.mjs package.json package-lock.json
git commit -m "replica: screenshot every page on live and candidate and diff them"
```

---

### Task 11: Console — zero CSP violations, zero failed requests, on every page

**Files:**
- Create: `replica/console-check.mjs`
- Modify (probably): `deploy/security-headers.replica.conf`

- [ ] **Step 1: Write `replica/console-check.mjs`**

```javascript
#!/usr/bin/env node
/**
 * console-check.mjs — what the browser complains about on each page.
 *
 * Loads every manifest page on one origin at phone and desktop width and
 * collects: Content-Security-Policy violations (via the securitypolicyviolation
 * event, which the console does not always show), requests that failed or
 * came back 4xx/5xx, and console errors. A CSP directive missing a host fails
 * silently for the visitor — a font quietly falls back — so this is the gate
 * for security-headers.replica.conf, not a nicety.
 *
 *   scripts/with-node.sh node replica/console-check.mjs http://127.0.0.1:8090
 *   scripts/with-node.sh node replica/console-check.mjs https://dev.thehenley.com.au
 *
 * Exits 1 on any finding.
 */
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const base = process.argv[2];
if (!base) { console.error('usage: console-check.mjs <origin>'); process.exit(2); }

const manifest = JSON.parse(readFileSync('source/migration-manifest.json', 'utf8'));
const paths = [...manifest.urls.map((u) => u.path), '/news/page/2/', '/no-such-page-console-check/'];

const browser = await chromium.launch();
let findings = 0;
for (const width of [390, 1280]) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  await context.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error(`CSP ${e.violatedDirective} blocked ${e.blockedURI}`);
    });
  });
  for (const path of paths) {
    const page = await context.newPage();
    const problems = [];
    page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
    page.on('requestfailed', (r) => problems.push(`failed: ${r.url()} (${r.failure()?.errorText})`));
    page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('/no-such-page-console-check/')) problems.push(`${r.status()}: ${r.url()}`); });
    try {
      await page.goto(base + path, { waitUntil: 'networkidle', timeout: 60000 });
      const height = await page.evaluate(() => document.body.scrollHeight);
      for (let y = 0; y < height; y += 600) { await page.evaluate((y) => window.scrollTo(0, y), y); await page.waitForTimeout(100); }
      await page.waitForLoadState('networkidle');
    } catch (error) {
      problems.push(`navigation: ${error.message}`);
    }
    await page.close();
    const unique = [...new Set(problems)];
    console.log(`${unique.length ? 'FAIL' : 'ok  '} ${String(width).padStart(4)}  ${path}`);
    for (const p of unique) console.log(`         ${p}`);
    findings += unique.length;
  }
  await context.close();
}
await browser.close();
console.log(`\n${findings} finding(s).`);
process.exit(findings ? 1 : 0);
```

- [ ] **Step 2: Run it against the local container and fix the CSP until clean**

```bash
scripts/with-node.sh node replica/console-check.mjs http://127.0.0.1:8090 2>&1 | tee replica/screenshots/console-local.txt
```

For each `CSP <directive> blocked <host>` line, add the host to that directive in `deploy/security-headers.replica.conf`, rebuild the image (Task 7 Step 5's `docker build` and `docker run`), and rerun. Expected end state: `0 finding(s)`. Hosts that GTM pulls in at runtime (for example `https://www.google.com.au/pagead/…`, `https://td.doubleclick.net`, `https://region1.google-analytics.com`) belong in the directive the browser names; do not add `*` or drop a directive. A `failed:` line for a same-origin URL means the export missed an asset: add it to `find_assets` or `find_css_assets` with a test, re-export, and rebuild.

The 404 probe path is expected to return 404 and is excluded from the 4xx rule; the 404 page itself must load with no other finding.

- [ ] **Step 3: Rerun the strict gate on the final image, then stop the container**

```bash
scripts/check-urls.sh --strict --noindex http://127.0.0.1:8090 | tail -3
docker stop henley-replica-local
```

- [ ] **Step 4: Commit**

```bash
git add replica/console-check.mjs deploy/security-headers.replica.conf replica
git commit -m "replica: a console gate for the policy, and the hosts it found"
```

---

### Task 12: Documentation — README, decisions, runbook, and the redesign plan's note

**Files:**
- Modify: `replica/README.md`, `docs/decisions.md`, `docs/runbook-cutover.md`, `docs/plan-2026-09-09-website-rebuild.md`

- [ ] **Step 1: Finish `replica/README.md`**

```markdown
# Replica of thehenley.com.au

A static copy of the WordPress site, served by nginx in place of WordPress so
the public sees no change. It exists so the site can leave WordPress now while
the redesign (`stream/website-rebuild`) takes its time. Spec:
`docs/superpowers/specs/2026-09-16-legacy-replica-design.md`.

## What is here

| Path | What |
|---|---|
| `export.py` | Fetches the live site and writes `site/` and `manifest.json`. Standard library only. |
| `form.html` | The contact form: name, email, phone, the two interest checkboxes, enquiry. Posts to the receiver in `../forms/`. |
| `site/` | The site. Generated. 28 pages, the 404 page, two feeds, the sitemaps, robots.txt and every same-origin asset those reference. |
| `manifest.json` | Every file in `site/`, its source URL and sha256. |
| `compare.mjs` | Screenshot diff, live against a candidate, every page at 390 and 1280 px. |
| `console-check.mjs` | CSP violations, failed requests and console errors per page. |
| `tests/` | One test per post-processing rule, run against the 2026-09-09 capture. |

## Refresh the export

Do this the evening before cutover, and whenever the live site changes.

    forms/.venv/bin/python replica/export.py
    git diff --stat replica/
    forms/.venv/bin/python -m pytest replica/tests -q

Read the diff. Two runs against an unchanged site are byte-identical apart
from `fetched_at` in the manifest, so every changed file is a change on the
live site (or a rule that needs attention). Commit, then deploy.

## Verify a deployment

    scripts/check-urls.sh --strict --noindex https://dev.thehenley.com.au        # --indexable for prod
    scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au https://dev.thehenley.com.au
    scripts/with-node.sh node replica/console-check.mjs https://dev.thehenley.com.au
    SITE_DIR=replica/site scripts/check-enquiry-flow.sh

The screenshot diff reports `/contact/` as a difference at both widths: the
form is shorter. Anything else is a defect.

## Editing content (rare)

Edit the HTML under `site/` directly, commit, deploy. The next `export.py` run
will overwrite it with whatever WordPress serves — so an edit here that must
survive a refresh has to be made on WordPress first, while it still exists,
or the refresh skipped. After cutover there is no WordPress to refresh from;
`site/` is then the only source.

## What was changed from what WordPress served

Only this. `tests/test_export.py` pins each item.

- Removed: REST, oEmbed, RSD, shortlink, pingback and comments-feed discovery
  links; the emoji script and style; generator and Site Kit meta tags; the
  Gravity Forms JavaScript and its AJAX iframe.
- Replaced: the Gravity Form on `/contact/` with `form.html`.
- Rewritten: same-origin references made root-relative (so dev serves its own
  copy); the two rotating WordPress nonces zeroed; Yoast's child sitemaps
  renamed `sitemap-pages.xml` and `sitemap-posts.xml`.
- Kept: everything else, byte for byte — Elementor, jQuery, WP Rocket's
  lazy-load, both GTM containers, gtag, Yoast metadata, Typekit, Google Fonts
  and the Font Awesome kit.
```

- [ ] **Step 2: `docs/decisions.md`.** Append a section:

```markdown
## Two streams: leave WordPress first, redesign second (2026-09-16)

**The rebuild is split.** Feedback was that the redesign needs its own design
project. Scott's decision: `stream/replica` replaces WordPress with a static
export of the current site that the public cannot tell apart from today's,
and goes live at thehenley.com.au; `stream/website-rebuild` continues as the
redesign, with no review URL until the replica is live and frees
dev.thehenley.com.au. Spec: `docs/superpowers/specs/2026-09-16-legacy-replica-design.md`.

What that means for decisions recorded above: the enquiry receiver, the id
floor, the timestamp format, the bot protection, the proxy trust and the URL
gate all apply to the replica unchanged. The brief, the two paths, the
photography and the four-field form's *design* apply to the redesign only.
The replica's form is the old one minus "How did you hear about us?" —
Scott's choice on 2026-09-16 — on Gravity's own CSS classes.

The replica is a stopgap: weeks to months, rare edits made in git. No staff
editing tool. It carries the live site's dependencies on Typekit, the Font
Awesome kit and two GTM containers exactly as they are; consolidating those
is the redesign's decision.
```

- [ ] **Step 3: `docs/runbook-cutover.md`.** Under "Before the day", replace the first bullet (`Stage 3 complete: …`) with:

```markdown
- [ ] The replica export is fresh: `forms/.venv/bin/python replica/export.py`
      run the evening before, its diff reviewed and committed, and nonprod
      rebuilt from it. This is the last time anything is copied from
      WordPress; an edit made on WordPress after this is lost.
- [ ] `scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au https://dev.thehenley.com.au`
      reports only `/contact/` to review, at both widths.
- [ ] `scripts/with-node.sh node replica/console-check.mjs https://dev.thehenley.com.au`
      reports zero findings.
```

Change the `check-urls.sh --strict` bullet's command to `scripts/check-urls.sh --strict --noindex https://dev.thehenley.com.au`. Delete the bullets "The Village Comparison Document is linked prominently from every page…", "The design sample signed off by the GM…" and "Scott adds the GTM trigger for the `enquiry_submitted` event…" — the replica publishes exactly what the live site does today and has no such event. Keep the Search Console, test-enquiry and drain-rehearsal bullets.

In "Cutover" step 2, replace the code block with:

```bash
docker network create henley-website-prod-net   # once
cd /mnt/persistent/dev/henley-website
cp deploy/.env.example deploy/.env              # then set TRUSTED_PROXY_IPS
docker compose --env-file deploy/.env -f deploy/compose.prod.yml up -d --build
```

and after `check-urls.sh --strict` in step 5 add `--indexable` (production must not carry the noindex header) and a bullet: "`replica/compare.mjs https://dev.thehenley.com.au https://thehenley.com.au` — the new production against nonprod, which is the same export; expect every page `ok`."

In "After", add a bullet: "`docs/superpowers/specs/2026-09-16-legacy-replica-design.md` §"Why this exists": once production is stable, retarget NPM host 4 (dev.thehenley.com.au) at the redesign's container so `stream/website-rebuild` has its review URL back."

- [ ] **Step 4: `docs/plan-2026-09-09-website-rebuild.md`.** Insert after the title:

```markdown
> **2026-09-16 — this is now the redesign's plan.** The work was split (see
> `docs/superpowers/specs/2026-09-16-legacy-replica-design.md`): leaving
> WordPress is `stream/replica`, which ships a like-for-like export first;
> the pages, brief approvals and Stage 3 items below belong to the redesign
> in `stream/website-rebuild`, which has no review URL until the replica is
> live. Nothing below is a cutover blocker any more.
```

- [ ] **Step 5: Commit**

```bash
git add replica/README.md docs/decisions.md docs/runbook-cutover.md docs/plan-2026-09-09-website-rebuild.md
git commit -m "docs: the replica is the cutover candidate; the rebuild plan is the redesign's"
```

---

### Task 13: Land, deploy to nonprod, and verify through NPM

This task touches the shared checkout and a live nonprod stack. Follow the order exactly.

- [ ] **Step 1: Everything green in the worktree**

```bash
forms/.venv/bin/python -m pytest replica/tests forms/tests -q
scripts/check-urls-fixture.sh | tail -1
scripts/with-node.sh npm test
git status --short     # must be empty
```

- [ ] **Step 2: Land**

```bash
git merge main            # nothing to merge unless the redesign moved; resolve if it did
stream land replica       # from this worktree; add --repo henley-website if it cannot infer the repo
```

`stream land` runs the repo checks, fast-forwards `main` in `/mnt/persistent/dev/henley-website`, pushes, and stamps the register. Landing on henley-website is announced because it decides what the next nonprod build ships; if the command asks for `--yes` to confirm that announcement, add it — Step 3 of this task is that rebuild. If it refuses for any other reason, read what it printed; do not force anything.

- [ ] **Step 3: Rebuild the nonprod site container only**

```bash
cd /mnt/persistent/dev/henley-website
git log --oneline -1                     # the landing commit
docker compose --env-file deploy/.env -f deploy/compose.nonprod.yml up -d --build site
docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep henley-website
```

Only `site` is rebuilt; the receiver keeps running with its verified `TRUSTED_PROXY_IPS`. Then return to the worktree: `cd /mnt/persistent/git/worktrees/henley-website/replica`.

- [ ] **Step 4: The gates, through NPM**

```bash
scripts/check-urls.sh --strict --noindex https://dev.thehenley.com.au | tail -4
scripts/with-node.sh node replica/console-check.mjs https://dev.thehenley.com.au | tail -3
scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au https://dev.thehenley.com.au | tee replica/screenshots/report-dev.txt | tail -6
```

Expected: strict green with 0 failed; 0 console findings; compare reports only `/contact/` at 390 and 1280 to review.

- [ ] **Step 5: The enquiry sequence through NPM.** The per-IP limit is three an hour and a rejected submission spends a slot (F02), so the order matters and the sequence can be run once an hour from one address. Use a marker email so the rows can be removed.

```bash
E=https://dev.thehenley.com.au/api/enquiry
# 1. A 20 KB chunked body with no Content-Length: refused at the body limit, spends no slot.
head -c 20000 /dev/zero | tr '\0' 'a' | curl -s -o /dev/null -w '%{http_code}\n' -H 'Transfer-Encoding: chunked' -H 'Content-Type: application/x-www-form-urlencoded' --data-binary @- $E
# 2. A script element in the email field: 400, escaped. Spends slot 1.
curl -s -w '\n%{http_code}\n' --data-urlencode 'name=Replica Check' --data-urlencode 'email=<script>window.__x=1</script>' $E | grep -o -E '&lt;script|<script>window' | head -1
# 3, 4. Two valid submissions with an invented first hop: 303 to the thank-you page. Slots 2 and 3.
for i in 1 2; do curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' -H "X-Forwarded-For: 10.99.0.$i" --data-urlencode 'name=Replica Check' --data-urlencode "email=replica-check-$i@example.com" --data-urlencode 'enquiry_text=replica nonprod check' --data-urlencode 'page_path=/contact/' $E; done
# 5. The fourth attempt this hour: 429, and the page still carries the phone number.
curl -s -w '\n%{http_code}\n' -H 'X-Forwarded-For: 10.99.0.3' --data-urlencode 'name=Replica Check' --data-urlencode 'email=replica-check-3@example.com' $E | grep -o -E '5591 2111|^429$'
# 6. A bot filling the honeypot: 303, nothing stored, regardless of the limit.
curl -s -o /dev/null -w '%{http_code}\n' --data-urlencode 'name=Bot' --data-urlencode 'email=replica-check-bot@example.com' --data-urlencode 'company=Acme' $E
```

Expected, in order: `413`; `&lt;script`; `303 https://dev.thehenley.com.au/thank-you/?sent=1` twice; `5591 2111` and `429`; `303`.

Then the rows, read-only, and their removal:

The host has no `sqlite3` binary, so use Python:

```bash
DB=/mnt/persistent/stor/henley-website-nonprod/intake.sqlite
forms/.venv/bin/python -c "
import sqlite3; c = sqlite3.connect('file:$DB?mode=ro', uri=True)
for row in c.execute(\"SELECT id, email, remote_ip, page_path FROM enquiries WHERE email LIKE 'replica-check-%'\"): print(row)"
```

Expected: exactly two rows (`replica-check-1`, `replica-check-2`), both with the same `remote_ip` — the address NPM observed, not `10.99.0.x` — and `page_path` `/contact/`. Then:

```bash
forms/.venv/bin/python -c "
import sqlite3; c = sqlite3.connect('$DB'); n = c.execute(\"DELETE FROM enquiries WHERE email LIKE 'replica-check-%'\").rowcount; c.commit(); print(n, 'removed')"
```

The id sequence is deliberately left advanced, as on 2026-09-10.

- [ ] **Step 6: A browser-shaped submission lands on the old thank-you page.** From a *different* client address (the per-IP slots for this host are spent), or after an hour: open `https://dev.thehenley.com.au/contact/` in Playwright, fill name, email `replica-check-browser@example.com` and a message, submit, and assert the URL is `/thank-you/?sent=1` and the page shows the thank-you heading the live site shows. Then remove that row as in Step 5.

```bash
scripts/with-node.sh node -e '
import("playwright").then(async ({ chromium }) => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto("https://dev.thehenley.com.au/contact/");
  await p.fill("#input_1_1", "Replica Check"); await p.fill("#input_1_4", "replica-check-browser@example.com");
  await p.fill("#input_1_7", "browser check"); await p.click("#gform_submit_button_1");
  await p.waitForURL(/thank-you/); console.log(p.url()); console.log(await p.locator("h1, h2").first().innerText());
  await b.close();
});'
```

- [ ] **Step 7: Record the evidence.** Fill in the table below in this plan file, commit it on the stream, and land again (`git merge main && stream land henley-website replica`). Update the register's description for `replica` in `/mnt/persistent/git/keystone/docs/streams.md` (commit with `git commit --only -- docs/streams.md` in the keystone checkout and push) with: landed commits, "nonprod serves the replica from <date>", the fidelity result, and what remains before cutover — the pre-cutover export refresh, Scott's review, and the runbook's "Before the day" list.

---

## Evidence

Fill in as tasks complete. Test results and artefact locations only; never enquiry contents.

| Task | Commit | Local evidence | Nonprod evidence | Outstanding |
|---|---|---|---|---|
| 1–5 export rules | `6d7331f` | 30 exporter tests pass | Deployed files match manifest | — |
| 6 export | `6d7331f` | 339 files, 301 assets, 62MB; repeat export identical apart from timestamp | All 339 hashes verified | Refresh before production |
| 7 image + config | `eebf832`, `8ded512` | Strict URL gate 87/0/0 | 87/0/0, including noindex | — |
| 8 robots gate | `b52f54f`, `32b6c2c` | Fixtures pass | Dev noindex verified | Production indexability at cutover |
| 9 enquiry flow | `1339d2e` | Receiver 77 tests pass | Seven checks pass; two synthetic rows removed | Nightly reader dry run, live drain |
| 10 fidelity | `3b5d54d`, `6d7331f` | All 56 comparisons reviewed | All 56 reviewed; intended form difference and intermittent loading documented | Scott visual review |
| 11 / 11b console | `eebf832` | Regression fixtures pass; 58 combinations covered | 58 covered with zero fatal after two timeout rechecks | Inherited tracking warnings remain |
| 12 docs | `195a941`, `eebf832` | README, decisions, spec and cutover aligned | Verification report records deployed evidence | Production prerequisites in report |
| 13 nonprod | `8ded512` | Landing checks and 29-page build pass | Site-only deployment 17 Sep; strict gate, console, screenshots and enquiry checks complete | Production cutover pending |

Explained screenshot differences (path, width, cause):

- `/contact/`, both widths — the form has five fields, not seven, and no "How did you hear about us?". Decided 2026-09-16.
