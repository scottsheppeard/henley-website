# Like-for-like replica of thehenley.com.au — design

Date: 2026-09-16. Stream: `stream/replica`, worktree
`/mnt/persistent/git/worktrees/henley-website/replica`. Owner: Scott.

## Why this exists

The rebuild so far bundled two problems into one deliverable: getting the
website off WordPress (a security and operational risk — see the bot pressure,
admin-account and plugin-fatal findings in
[the baseline](../../2026-09-09-rebuild-baseline-and-proposal.md)), and
redesigning the site's look and feel. Feedback on 2026-09-16 was that the
redesign needs its own project with its own design work. Scott's decision the
same day: split them.

1. **This stream** replaces WordPress with a static site that the public
   cannot tell apart from today's. It goes live at `thehenley.com.au` in place
   of WordPress, and the enquiry pipeline keeps working. It is a stopgap:
   weeks to a few months, with rare content edits made in git by Scott or an
   agent, and no staff editing.
2. **`stream/website-rebuild`** continues as the redesign. Its Astro site on
   `main` is untouched by this stream. It has no public or review URL while
   the replica is being built; once the replica is live, `dev.thehenley.com.au`
   is freed for the redesign's review.

`dev.thehenley.com.au` (NPM host 4 → `henley-website-nonprod`) serves the
replica from the first deploy of this stream onward.

## What is reused

Everything from the remediation slices that is not about the new design
transfers unchanged:

- the enquiry receiver in `forms/` (contract, honeypot, per-IP and daily
  caps, body limit, proxy trust) and its tests;
- `deploy/nginx.conf`, `redirects.conf`, `redirects-map.conf` (shortlinks,
  Redirection rules, Yoast sitemap alias, canonical host/scheme/slash);
- `scripts/check-urls.sh --strict` and its fixture, `check-enquiry-flow.sh`,
  `check-proxy-trust.sh`;
- `docs/runbook-cutover.md` and the henley-utils dual-source reader;
- the `www` → apex NPM redirection host and the 16 KB body limit on the
  `/api/enquiry` location.

## What is built

### 1. Layout in the repo

```
replica/
  export.py            # fetch + post-process; deterministic, committed
  site/                # the exported tree, committed (~65 MB, mostly media)
  manifest.json        # every URL and asset fetched, with sha256 and source URL
  form.html            # the replacement contact form fragment
  README.md            # how to refresh, how to verify, what is deliberately removed
deploy/
  Dockerfile.replica   # nginx:alpine serving replica/site — no build stage
  nginx.replica.conf
  robots-tag.nonprod.conf
  robots-tag.prod.conf
  security-headers.replica.conf
  compose.*.yml        # `site` builds Dockerfile.replica; the Astro image is renamed
```

The Astro site (`src/`, `astro.config.mjs`, `deploy/Dockerfile`) stays where it
is. The compose `site` service points at the replica; the redesign's image is
not built by either compose file until the redesign stream takes `dev` back.

### 2. The export

`replica/export.py` (Python 3.11, standard library only — a parser would
re-serialise markup it must not touch, so the rules are regexes over the
served text; tests run with `forms/.venv`, which already has pytest) fetches
from the live origin `https://thehenley.com.au`:

- the 27 sitemap URLs from `source/migration-manifest.json`;
- `/news/page/2/`, `/feed/`, `/news/feed/`, `/sitemap-index.xml` and the
  sitemaps it lists, `/robots.txt`;
- Yoast's child sitemaps are written as `sitemap-pages.xml` and
  `sitemap-posts.xml` and the index rewritten to name them, because the
  existing redirects send the old names to the index;
- a 404 page, fetched from a path that does not exist, saved as `404.html`.

For each HTML and CSS document it collects same-origin asset references —
`link[href]`, `script[src]`, `img[src]`, `img[srcset]`, `source[srcset]`,
inline `style` attributes, `<style>` blocks, and `url()` inside fetched CSS
recursively — and downloads each asset once to its original path under
`replica/site/`, query string stripped for the file name but left in the HTML
reference. nginx ignores the query string when resolving the file, so
`style.css?ver=3.27` still serves `style.css` and browser caching behaves as
it does today.

Cross-origin references (Google Fonts, Typekit kit `azk7leu`, Font Awesome kit
`6ec9d3cb9f`, both GTM containers, gtag, Facebook, Instagram, the Microsoft
Forms maintenance form) are left exactly as they are. They are dependencies
the live site already has; the replica neither adds nor removes any.

**2026-09-17 correction:** asset references under `dev.thehenley.com.au`
are treated as local assets, fetched from the production origin and made
root-relative in HTML, inline configuration and CSS. These old references
are broken on the live site; restoring the intended images is a documented
exception to visual fidelity, not a new external dependency.

The export is rerun the evening before cutover and the diff of
`replica/site/` and `manifest.json` reviewed, so any WordPress edit made after
this stream's first export is carried across. `manifest.json` records the
fetch time and the `lastmod` of each page so the diff is explainable.

### 3. HTML post-processing

Applied by `export.py` to every HTML document, in this order, each rule with a
unit test against a fixture:

Removed:
- `<link rel="https://api.w.org/">`, `rel="EditURI"`, `rel="wlwmanifest"`,
  `rel="shortlink"`, `rel="alternate" type="application/json+oembed"` and
  `text/xml+oembed`, `rel="pingback"`;
- the emoji detection `<script>` and its `<style>`;
- `<meta name="generator">` for WordPress, Elementor and WP Rocket;
- the Site Kit and WPCode HTML comments that name the plugins;
- the Gravity Forms scripts and inline initialisers (contact page only — see §4);
- the `Comments Feed` alternate link; Site Kit's `google-adsense-platform-*`
  meta tags; the two rotating `"nonce"` values in inline configuration,
  normalised to zeros.

Kept verbatim: Elementor markup, its CSS and JS, jQuery, the theme's child
CSS and JS, Yoast title/meta/canonical/OG/Twitter/JSON-LD, both GTM containers
(`GTM-PGSH3HF7`, `GTM-M3MV9VG`) and the gtag snippet, the RSS `<link
rel="alternate">` tags, `<link rel="preconnect">` hints.

Nothing is minified, reformatted or re-encoded. Fidelity beats tidiness.

### 4. The contact form

The contact page is the only page that embeds the form. The exported
`gform_wrapper` element is replaced by `replica/form.html`, a plain form that
reuses Gravity Forms' own classes (`gform_wrapper`, `gform_fields`,
`gfield`, `gfield_label`, `ginput_container`, `gform_footer`, `gform_button`)
so the shipped Gravity CSS styles it identically. Fields, in this order:

| Field | Receiver name | Required | Old GF key |
|---|---|---|---|
| Name | `name` | yes | 1 |
| Email | `email` | yes | 4 |
| Phone | `phone` | no | 3 |
| How can we help? — Apartment Living | `interest_apartment` | no | 6.1 |
| How can we help? — Private Aged Care | `interest_aged_care` | no | 6.2 |
| Your enquiry | `enquiry_text` | no | 7 |

"How did you hear about us?" (GF key 5) is dropped. This is Scott's decision
of 2026-09-16 ("new four fields, old styling"); the interest checkboxes stay
because they populate `InterestType_c__c` in Salesforce and were part of the
visible form. `page_path` is a hidden field set to `/contact/`. The honeypot
field `company` is present and visually hidden as the receiver expects.

The form `action` is `/api/enquiry`, method POST, no JavaScript. The receiver
already answers a stored row with a 303 to `/thank-you/?sent=1`; the exported
thank-you page is what the visitor sees, as today. Validation failures return
the receiver's escaped 400 page (R01), unchanged.

Gravity's own CSS and the `gform_wrapper` class remain so the layout matches;
the Gravity JS bundle, its AJAX submit and the reCAPTCHA add-on markup are
removed from the page. The live site serves no reCAPTCHA script today, so
this changes nothing visible.

### 5. Deployment

`deploy/Dockerfile.replica` is the runtime stage of the existing Dockerfile
with no build stage: `COPY replica/site /usr/share/nginx/html`. Same
unprivileged nginx, same port 8080, same health check, same `nginx -t` at
build.

`deploy/nginx.replica.conf` is a copy of `deploy/nginx.conf` with these
changes (the Astro site keeps its own file):
- the `/_astro/` location is removed;
- a `^~ /wp-content/` location serves theme, plugin and Elementor assets with
  `Cache-Control: public, max-age=31536000` (not `immutable`: versions are
  keyed by the `?ver=` query string, as today);
- the `/wp-content/uploads/` and `/documents/` locations stay as they are;
- the WordPress 410 locations stay — `/wp-json`, `/wp-admin`, `/wp-includes`,
  `/xmlrpc.php`, `/wp-login.php`, any `.php` — which is the point of the
  exercise. The Elementor and plugin assets under `/wp-content/plugins/` and
  `/wp-content/themes/` are static files and are served; nothing under
  `/wp-content/` is executable.
- `/wp-includes/js/` is served as static files, since jQuery and two
  WordPress scripts live there; the rest of `/wp-includes/` stays 410.

`deploy/security-headers.replica.conf` replaces the CSP for the replica. The
Astro CSP names self-hosted fonts and no third-party script hosts; the
replica must allow Google Fonts, Typekit, the Font Awesome kit and its CDN,
inline scripts and styles (Elementor uses both) and the same Google hosts.
The policy is written from what a browser actually requests on each of the 27
pages, verified with the console showing zero CSP violations, and includes
`frame-ancestors 'none'`, `object-src 'none'` and `base-uri 'self'` as now.
The other four headers are unchanged.

**F05 is fixed here.** Nonprod becomes a full duplicate of production, so the
`X-Robots-Tag: noindex, nofollow` header must actually be served. It comes
from the container, not NPM: `Dockerfile.replica` takes `ARG SITE_ENV` and
copies `deploy/robots-tag.${SITE_ENV}.conf` to `/etc/nginx/conf.d/robots-tag.conf`,
which `security-headers.replica.conf` includes — so the header rides with the
other security headers into every location. The nonprod compose file passes
`SITE_ENV: nonprod`; prod passes `prod`, whose file is empty.
`check-urls.sh --noindex` asserts the header is present and `--indexable`
that it is absent.

### 6. Verification

All of these are gates for landing the deploy slice, and again at cutover:

1. **Export determinism.** Two consecutive runs of `export.py` against the
   same origin produce identical `replica/site/` and `manifest.json`.
2. **Post-processing tests.** pytest over fixture HTML for every rule in §3
   and for the form replacement in §4, including "the contact page contains
   exactly one form, posting to `/api/enquiry`, with these six named fields
   and the honeypot".
3. **Strict URL gate.** `scripts/check-urls.sh --strict https://dev.thehenley.com.au`
   green: every manifest URL 200 or its intended 301, shortlinks resolve,
   feeds and sitemaps served, `/news/page/3/` 404, WordPress paths 410.
4. **Fidelity.** A committed script drives Playwright to screenshot each of
   the 27 pages on `https://thehenley.com.au` and on
   `https://dev.thehenley.com.au` at 390 px and 1280 px widths, and diffs
   them. Differences are expected only where the live site is dynamic
   (`[year]` shortcode output, lazy-load placeholders, the form). Every
   remaining difference is listed in the plan with a reason or fixed.
5. **Enquiry flow.** `check-enquiry-flow.sh` locally, then the R02 sequence
   through NPM on dev: a valid submission stores a row and lands on the
   thank-you page, the honeypot discards, the fourth submission from one
   address is 429, a script element in the email field comes back escaped.
   Rows are removed afterwards.
6. **Console.** Zero CSP violations, local resource failures and runtime
   errors on every page at both widths. External network failures are
   reported separately for review: the inherited `GTM-M3MV9VG` container
   returned 404 on production during the September 16 check. Keep the tag
   pending Scott's decision; do not relax the CSP or hide local failures to
   make that external failure disappear. The deliberate 404 page probe is
   expected to return 404.
7. **Headers.** `X-Robots-Tag` present on dev, and the strict gate proves it.

### 7. Cutover

`docs/runbook-cutover.md` applies as written. Its edits in this stream:
remove the token-generation and `npm ci` steps from the deploy sequence
(the replica has no build), point the image at `Dockerfile.replica`, and add
the pre-cutover export refresh (§2) and screenshot pass (§6.4) as the first
two steps. The drain procedure, the `/webhooks` exception, the NPM host
5/11 switch, the rollback material and the henley-utils `DB_HOST` handling are
unchanged. The R03 drain rehearsal remains deferred by Scott's decision of
2026-09-10.

### 8. Out of scope

- Any content, copy, photography, accessibility or performance change. The
  replica inherits the live site's flaws; fixing them is the redesign's job.
- Removing the Elementor, jQuery or third-party font dependencies.
- A content editing workflow. Edits are made to the exported HTML in git and
  redeployed; `README.md` documents the two-command path.
- The redesign stream's open items (brief approvals, GTM/CSP under the new
  design, accessibility pass,
  Lighthouse). They stay in `docs/plan-2026-09-09-website-rebuild.md`.

Existing email-image URLs are a production migration dependency even when
no website page references them. Before cutover, inventory and preserve
the `branding/` assets used by staff signatures and the notification images
`2025/09/lightspeed.png` and `2025/09/sharepoint.png`. They are not yet
covered by the page-driven exporter or its strict URL gate; dev review can
proceed, but production must not retire their current host without proof
that the replacement serves them.

### 9. Risks carried knowingly

- The Typekit and Font Awesome kits may be owned by the agency (Rouken) rather
  than The Henley. The live site has this exposure today; the replica does
  not add to it, but if a kit is disabled the headings and icons degrade on
  both. Ownership should be confirmed before the redesign chooses fonts, not
  as a condition of this stream.
- Two GTM containers keep firing, as today. Consolidation is a redesign-stream
  decision (review §3).
- 65 MB of media in git is accepted for a stopgap. It is not repeated for the
  redesign, which keeps its own optimised images.
