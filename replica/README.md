# Replica of thehenley.com.au

A static copy of the WordPress site, served by nginx in place of WordPress so
the public sees no change. It lets the site leave WordPress while the redesign
in `stream/website-rebuild` takes its time. The binding design is
`docs/superpowers/specs/2026-09-16-legacy-replica-design.md`.

## What is here

| Path | What |
|---|---|
| `export.py` | Fetches the live site and writes `site/` and `manifest.json`. It uses the standard library only. |
| `form.html` | The contact form: name, email, phone, two interest checkboxes and enquiry. It posts to the receiver in `../forms/`. |
| `site/` | The generated site: 28 pages, 404 page, two feeds, sitemaps, `robots.txt`, and the same-origin assets they use. |
| `manifest.json` | Every file in `site/`, its source URL and SHA-256. |
| `compare.mjs` | Screenshot comparison of live and a candidate at 390 and 1280 px. |
| `console-check.mjs` | Per-page CSP violations, runtime errors and external-request failures. CSP and local-resource/runtime errors are the gate; external tracking failures are reported separately. |
| `tests/` | Post-processing-rule tests against the 2026-09-09 capture. |

## Refresh the export

Do this the evening before cutover and whenever the live site changes.

    forms/.venv/bin/python replica/export.py
    git diff --stat replica/
    forms/.venv/bin/python -m pytest replica/tests -q

Read the diff before committing. Two runs against an unchanged site differ only
in `fetched_at` in the manifest, so a changed generated file needs an
explanation. After Task 11b, references to retired
`dev.thehenley.com.au/wp-content/uploads/` are fetched from the production
origin and made local: restored images are an intentional screenshot difference
from the broken live page, not a fidelity failure.

When removing assets, do not audit an in-place refresh: the exporter writes the
current output but does not remove stale files already in its output directory.
Export to a fresh directory and manifest, then review that complete candidate
before replacing `site/`:

    audit_dir=$(mktemp -d)
    forms/.venv/bin/python replica/export.py --out "$audit_dir/site" --manifest "$audit_dir/manifest.json"
    git diff --no-index --stat replica/site "$audit_dir/site" || true
    git diff --no-index --stat replica/manifest.json "$audit_dir/manifest.json" || true

The fresh manifest audits files emitted in that run; it does not prove that an
in-place `site/` directory contains no stale files. Review the candidate and
its manifest before deliberately replacing the committed export.

## Verify a deployment

    scripts/check-urls.sh --strict --noindex https://dev.thehenley.com.au        # --indexable for prod
    scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au https://dev.thehenley.com.au
    scripts/with-node.sh node replica/console-check.mjs https://dev.thehenley.com.au
    SITE_DIR=replica/site scripts/check-enquiry-flow.sh

The comparison normally reports `/contact/` at both widths because the
replacement form is shorter. After Task 11b it can also report pages where the
retired dev-host image URLs have been restored. Review those restored-image
differences; any other difference needs investigation.

`console-check.mjs` must report zero CSP violations and zero local-resource or
runtime errors. It reports external network failures separately and does not
fail the gate for the known dead `GTM-M3MV9VG` container or its aborted beacons;
that tag remains preserved unless Scott decides otherwise.

## Editing content (rare)

Edit HTML under `site/` directly, commit, and deploy. The next `export.py` run
will overwrite it with what WordPress serves, so an edit that must survive a
refresh needs to be made in WordPress while it exists, or the refresh skipped.
After cutover `site/` is the only source.

## What was changed from what WordPress served

Only these changes are intended; `tests/test_export.py` pins them.

- Removed: REST, oEmbed, RSD, shortlink, pingback and comments-feed discovery
  links; emoji script and style; generator and Site Kit meta tags; Gravity Forms
  JavaScript and its AJAX iframe.
- Replaced: the Gravity Form on `/contact/` with `form.html`.
- Rewritten: same-origin references root-relative; retired dev-host upload URLs
  are treated as production assets and made local; two rotating WordPress nonces
  are zeroed; Yoast child sitemaps are named `sitemap-pages.xml` and
  `sitemap-posts.xml`.
- Kept: Elementor, jQuery, WP Rocket lazy-load, both GTM containers, gtag, Yoast
  metadata, Typekit, Google Fonts and the Font Awesome kit.
