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
