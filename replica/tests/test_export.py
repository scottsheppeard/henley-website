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
