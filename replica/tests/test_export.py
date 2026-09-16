"""Tests for replica/export.py — every rule that changes what WordPress served."""
from __future__ import annotations

import hashlib
import json

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
