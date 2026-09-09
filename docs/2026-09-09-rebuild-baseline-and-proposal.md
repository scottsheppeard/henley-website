# thehenley.com.au rebuild — baseline review and proposal

Date: 2026-09-09. Status: **proposal, awaiting Scott's approval** (no code written yet).

This document records what the current WordPress site does (so nothing is lost in a
like-for-like replacement), what surrounds it (proxy, analytics, enquiry pipeline,
brand kit), and a recommended platform, feature checklist and migration plan.

---

## 1. Current site — inventory

### 1.1 Hosting and plumbing

| Item | Value |
|---|---|
| Container | `wp-prod-henley` (php:8.2-fpm + nginx, custom image) and `db-prod-henley` (MariaDB 10.6, host port 6306) |
| Compose | `/home/admin/henley-aws/websites/prod_henleycomau/docker-compose.yml` (DB passwords in plaintext in the compose file and `init.sql`) |
| Files | `/mnt/persistent/prod/www_henleycomau` (WordPress 7.1, 174 MB uploads) |
| Dev copy | `/mnt/persistent/dev/www_henleycomau` + `/home/admin/henley-aws/websites/dev_henleycomau` (`wp-dev-henley`, **not running**; `sync_from_prod.sh` clones prod) |
| Proxy (NPM) | host 5 `thehenley.com.au` → `wp-prod-henley:80`, **plus `location /webhooks` → `henley-webhooks:8000`** (must be preserved); host 11 `www.thehenley.com.au` → same; host 4 `dev.thehenley.com.au` → `wp-dev-henley:80` (dead upstream) |
| DNS | `thehenley.com.au`, `www`, `dev` all → 52.63.244.217 (this host). No DNS change needed for cutover |
| Network | `my_shared_network` (legacy shared network, not the per-tenant keystone pattern) |
| Outage evidence | WP core auto-updated to 7.1 on 2026-08-20, WP Rocket fatalled; 55 form submissions 20 Aug–9 Sep never reached `wp_gf_entry` (unrecoverable). A root-owned PHP `core` dump dated 2026-09-07 sits in the web root. Container restarted 2026-09-06 |
| Bot pressure | Of the last 20,000 access-log lines, ~8,000 are `POST /xmlrpc.php` (6,813) and `POST /wp-login.php` (1,013) plus probes for `wp-config.php`, `setup-config.php`, etc. |
| Admin accounts | 5 administrators, including two agency logins (`admin_max` / Rouken, `alex@pupdigital.com.au`) |

### 1.2 WordPress stack

Theme: `thehenley` (child of Hello Elementor, by Rouken). Pages are built in **Elementor Pro**
(header, footer, single-post and archive templates are Elementor "theme builder" templates).
Child theme adds: sticky header, a curtain-style mobile menu (jQuery), `[year]` shortcode,
FAQ slide toggle, Gravity Forms tweaks.

Active plugins and what each does for us:

| Plugin | Role | Replacement in new site |
|---|---|---|
| Elementor + Elementor Pro 3.27 | Page builder, header/footer, post templates | Hand-built templates |
| Gravity Forms 2.9 + reCAPTCHA add-on + Zero Spam | Contact form, stores entries in DB, reCAPTCHA v3 score, honeypot | Own form endpoint (§3.4) |
| Yoast SEO 24.4 | Titles, meta descriptions, canonical, OG/Twitter, JSON-LD schema, XML sitemap, robots.txt | Built into templates + generated sitemap |
| Google Site Kit 1.146 | Injects gtag `GT-TXH3QGV` (GA4 `G-YRX87W827V`) and GTM `GTM-PGSH3HF7`; Search Console verification | Static tag snippet (§3.6) |
| Insert Headers and Footers (WPCode) | Injects a **second** GTM container `GTM-M3MV9VG` | One GTM container (decision needed) |
| Redirection 5.5 | 2 rules: `/luxury-resort-living/` → `/luxury-retirement-living/` (737 hits); `/latest-articles/(.*)` → `/$1` (3,072 hits) | nginx redirects |
| WP Rocket | Caching, lazy-load, the plugin that fatalled | Not needed for static HTML |
| WP Mail SMTP (Brevo/Sendinblue) | Configured, but Gravity Forms has **no notifications** — nothing is emailed from the site | Not needed |
| Safe SVG, Classic Editor/Widgets, Duplicate Post | Editing conveniences | Not needed |

Third-party runtime dependencies on every page: Google Fonts (Lato, 18 weights), Adobe
Typekit kit `azk7leu` (Quincy CF headings), Font Awesome Pro kit `6ec9d3cb9f` (icons used:
angle-down/left/right, plus, minus, facebook-f, instagram), two GTM containers, gtag.

Design tokens in the live site (old brand, to be replaced): primary `#507CAB`, secondary
`#ACC5D3`, accent `#BA8F58`, headings Quincy CF, body Lato 300. H1 49px → H6 16px.

### 1.3 Pages and posts (all URLs to preserve)

Pages (12): `/` Home, `/luxury-retirement-living/`, `/location/`, `/the-henley-health-club/`,
`/dining/`, `/supported-living/` (edited Jul 2026), `/private-aged-care/`, `/news/` (post index),
`/contact/`, `/thank-you/` (form confirmation target), `/privacy-policy/`, `/disclaimer/`.

Posts (15, all at root level, not under `/news/`, all "Uncategorized", author shown as
`admin_max` in schema only). Ten evergreen articles (Jan–Apr 2023: costs of retirement living,
top 10 questions, downsizing, health, connections, Henley advantage, private aged care approach,
whatever care you need, homecare package) and five resident-life posts (art classes, fashionistas,
amazing artists, International Women's Day 2023, dietitian visit). Posts have prev/next links.

Word counts: Home ≈1,200 (of which the 25-question FAQ is most), Private Aged Care ≈1,000
(includes an 8-question FAQ), the long articles 700–1,200 each, service pages 300–450.

Navigation: Primary menu (9 items, order above). Footer main menu (same 9). Footer minor menu:
Privacy Policy, Disclaimer, **Maintenance Request** (external Microsoft Forms link). Socials:
Facebook `thehenleyonbroadwater`, Instagram `the_henley_on_broadwater`. Footer copyright
"© {year} The Henley on Broadwater Pty Ltd".

Contact details on the site: 70 Marine Parade, Southport QLD 4215; `info@thehenley.com.au`;
**07 5591 2111** (the brand kit email signature says 07 5557 0000 — confirm which to publish).

Calls to action: "Enquire Today" / "Contact Us" / "Book a Tour" / "Find out more" → `/contact/`;
"Village Comparison Document" → `/wp-content/uploads/2026/08/Henley-Form-3-VCD-1-July-2026.pdf`;
Schedule of Fees → `/wp-content/uploads/2026/07/SCHEDULE-OF-FEES-Henley-Care-1-July-2026.pdf`.
Older dated versions of both PDFs exist back to 2023 and may be bookmarked or indexed.

### 1.4 Media in use

254 original uploads (the rest are WordPress-generated size variants). Actually referenced by
pages/templates: ~45 images, all 2023 stock or agency shots (`home1/home2.jpeg`, `beach`,
`bowls`, `dining`, `group`, `hairdresser`, `living1`, `map`, `entertainment`, `food-wine`,
`shopping`, `standup`, `swimming`, `wide`, `workout`, `iStock-*`, `AdobeStock-*`,
`shutterstock-*`, `Scroll-Group-*`, `Private_Aged_Care_0[1-4]`, `Supported_Living_01`,
`Dining_From_Existing`), the resident-post photo sets (`High-Tea-*`, `IMG_0290..0394`,
`Image-1..6`, `Dietician-1..3`; originals 3–5 MB each), and `map.jpg` (a static map image, no
Google Maps embed anywhere). No video embeds.

Paths that **other systems hot-link** and must keep resolving after cutover:

- `/wp-content/uploads/branding/…` — the 2026 brand kit mirror (210 files) used by every
  staff email signature (`Logo.png`, `Facebook.png`, wide/email logo PNGs).
- `/wp-content/uploads/2025/09/lightspeed.png` and `sharepoint.png` — used by
  henley-utils `sync_notifications.py` emails.
- The dated PDFs above.

### 1.5 Contact form and downstream pipeline (must not break)

Gravity Forms "Contact Form" (id 1), ~5,200 entries since May 2023, 50–230 per month
(declining since Jan 2026). Fields:

| GF key | Field | Required |
|---|---|---|
| 1 | Name | yes |
| 4 | Email | yes |
| 3 | Phone | no |
| 5 | How did you hear about us? (free text) | no |
| 6.1 / 6.2 | How can we help? checkboxes: Apartment Living / Private Aged Care | no |
| 7 | Your enquiry (textarea) | no |
| — | reCAPTCHA v3 score, honeypot (abort on hit) | — |

Confirmation: redirect to `/thank-you/`. No email notifications. Entries are only read by
henley-utils:

- `scripts/daily_update.py` (host cron `30 0 * * *`) → `scripts/update/update_salesforce_leads.py`
  connects to MariaDB on `127.0.0.1:6306`, pulls the last 7 days of active entries, de-dupes,
  classifies with the Codex-CLI LLM classifier (`modules/spam_classifier.py`, six categories),
  stores state in `data/forms.db`, upserts `prospective_resident` (confidence ≥ 70) as Salesforce
  **Lead** (external id `WebFormID_c__c` = GF entry id; fields Email, Phone, Description,
  LeadSource=Website, InterestType, ReferralSource, WebEnquiryDate, NonSpamConfidence; owner
  hard-coded). Duplicates become a Task on the existing Lead/Contact.
- `modules/non_sales_enquiry_notifications.py` emails `existing_resident_or_family` and
  `other_legitimate` submissions as a digest to `reception@thehenley.com.au` via Microsoft Graph.
- `scripts/update/update_sales_forms.py` (SharePoint list `Sales/WebEnquiries`) is orphaned —
  not scheduled since Aug 2026.

The only coupling to WordPress is `fetch_entries()` / `_get_form_id()` in
`update_salesforce_leads.py` (lines ~108–196) reading `wp_gf_form`, `wp_gf_entry`,
`wp_gf_entry_meta`. Everything downstream keys off a stable integer entry id plus the seven
fields above.

Keystone already has `sales.enquiries` (staff-entered enquiries, `POST /api/enquiries`,
`source_system` + `source_record_id` unique index) and a **retained-but-deferred design** for
public ingress: `keystone/docs/webhook-ingress-design.md` (sandboxed `henley-hooks-<env>`
container, capability-URL tokens, no DB credentials in the internet-facing container). The
website form is the concrete sender that design was waiting for.

### 1.6 Analytics, search, ads

- GA4 property `398547918`, stream `5873509418`, measurement id `G-YRX87W827V`, delivered via
  Google tag `GT-TXH3QGV` (Site Kit gtag snippet, logged-in users excluded).
- Two GTM containers load on every page: `GTM-PGSH3HF7` (Site Kit) and `GTM-M3MV9VG` (agency,
  via WPCode). Contents unknown from here — check in GTM which is live and what tags/triggers
  it holds (a form-submit or `/thank-you/` pageview conversion is likely).
- Google Ads: no conversion id configured in Site Kit; AdSense not set up. Any Ads conversion
  tracking, if present, lives inside GTM.
- Search Console: property `https://thehenley.com.au/` verified through Site Kit's OAuth.
  After cutover re-verify (DNS TXT for a domain property is the cleanest; nothing depends on WP).
- Sitemap `sitemap_index.xml` → `page-sitemap.xml`, `post-sitemap.xml`; `robots.txt` allows all.
- Meta: home title "The Henley on Broadwater | Time to rediscover you." and a custom description;
  other pages use "{Title} | The Henley on Broadwater"; four resident posts have custom
  descriptions; OG image `home1.jpeg`; Yoast JSON-LD graph (WebSite, Organization, WebPage,
  Article). `og:locale` is `en_US`.

### 1.7 Brand kit (`/mnt/persistent/git/branding/henley`)

Canonical tokens: `DESIGN.md` (YAML front-matter, 73 colours, 13 type scales, spacing, radius,
37 component recipes). Human guide: `01_Style_Guide/The Henley - Brand Style Guide.docx`
(Edition 2026.1). Key points for the site:

- Palette: Henley Teal `#0E5B70` (accent, never flood), Text Slate `#4B5458`, Broadwater Deep
  `#083B4A` (footers, overlays), Coastal Mist `#6FA3B2` (focus ring), Linen `#F5F1EA`, Warm Sand
  `#D9CFC0`, Stone `#B8AE9D`, Driftwood `#8A7E6C`, Paper `#FAF9F6` (page background), Line Grey
  `#E5E7E8`, Charcoal `#1E2427`. Dark-mode ladder defined. No gradients, glows, glass or heavy
  shadows; 4px spacing grid; radius 4px buttons / 8px cards; 44px touch targets; visible focus.
- Type: Avenir Next LT Pro (Regular, Demi) with fallback Avenir → Calibri → system sans. The
  supplied TTFs are **desktop-licensed Linotype files with no web licence and no WOFF2** — they
  cannot be self-hosted as webfonts as-is. Vanitas Stencil is logo-only.
- Logo: horizontal wordmark only (`Vector_SVG/logo-vector-fill-currentcolor.svg` for inline
  CSS-coloured use; fixed-colour variants incl. white/paper for dark grounds). Minimum 120px
  wide digital. **No compact/stacked mark or favicon exists.**
- Imagery: four web-ready property photos (1920px) in `06_Imagery/Photography/`, 4K masters in
  `Wallpapers/`, renovation renders. Guidance: lifestyle over building, calm space for type,
  optional 5–8% teal duotone on heroes, no tall portrait crops.
- Voice: "a confident, well-travelled host"; tagline **"A lifestyle resort like no other."**;
  Australian spelling; use "lifestyle resort / residence / apartment", avoid "facility / unit /
  retirement home / nursing home" and marketing-speak. Note the tension with SEO: the current
  page names, slugs and search terms are "Luxury Retirement Living", "Private Aged Care".
  Recommendation: keep slugs, H1 keywords and nav labels for search continuity; apply the brand
  voice to body copy and the hero.

---

## 2. Platform decision

Three candidates were weighed for a 12-page marketing site with a blog and one form:

| Option | Summary | Verdict |
|---|---|---|
| **A. Static site (Astro) + nginx, separate tiny form service** | Pages, posts and FAQs as Markdown/JSON content collections; Astro builds plain HTML/CSS with near-zero JS and generates responsive AVIF/WebP images, sitemap, RSS. Served by `nginx:alpine`. Form POSTs go to a small sandboxed service. | **Recommended.** Smallest attack surface (prod serves files only), fastest pages, content editable as files in git, no runtime CMS, no PHP, no database on the public path. |
| B. Node server app (Next.js / SvelteKit SSR) | Full framework with server rendering and API routes in one container. | Over-powered for this content; a Node runtime on the public edge with dependencies to patch; no benefit for 27 URLs. |
| C. FastAPI + Jinja (match keystone) | Python templates rendered per request, form endpoint in the same app. | Matches team stack, but again a live app server for static content; image pipeline and tooling weaker than Astro's. Python stays where it belongs: the form receiver and henley-utils. |

Recommendation details (option A):

- **Astro 5** (Node 22 at build time only), TypeScript, content collections for `pages`,
  `posts`, `faqs`, `documents`. Zero client-side framework; the only JavaScript is ~3 small
  vanilla modules: mobile nav toggle, FAQ accordion enhancement (native `<details>` works with
  JS off), form submit (progressive enhancement over a normal POST).
- **CSS**: hand-written, design tokens generated from `branding/henley/DESIGN.md` front-matter
  into `tokens.css` (custom properties), mobile-first, single-column collapse below 768px per the
  guide. No Tailwind, no Bootstrap, no Font Awesome (7 icons → inline SVG).
- **Prod container**: multi-stage Dockerfile, build stage `node:22-bookworm-slim`, runtime
  `nginx:alpine` serving `/usr/share/nginx/html` plus the archived `/wp-content/uploads/` tree
  (read-only bind mount) so legacy links, PDFs and email-signature logos keep resolving.
  nginx handles redirects, 404 page, cache headers, security headers, and returns 410 for
  `*.php`, `/xmlrpc.php`, `/wp-admin` so bot traffic is answered without a backend.
- **Form service** `henley-website-forms` (Python 3.12 FastAPI, ~200 lines): validates fields,
  honeypot, rate limit per IP, reCAPTCHA v3 (reuse existing keys) or Turnstile, then appends the
  submission to a SQLite table on a bind mount under `/mnt/persistent/stor/henley-website-<env>/`.
  Returns 303 to `/thank-you/`. No outbound credentials, no DB credentials, own network.
  henley-utils `update_salesforce_leads.py` gets a ~40-line change to read this table instead of
  MariaDB (same seven fields, same integer id semantics, so Salesforce upserts and the reception
  digest are untouched). This is the like-for-like step. Phase 2 (after cutover) is to move the
  receiver to the keystone `henley-hooks` design and write into `sales.enquiries` with
  `source_system='website'`, which also lets the LLM classifier run inside keystone.
- **Environments**: `henley-website-nonprod` on `dev.thehenley.com.au` (NPM host 4 retargeted;
  add `noindex` header and optionally Authentik forward-auth for the team preview);
  `henley-website-prod` on hosts 5 and 11 at cutover with the `/webhooks` location kept.
  Compose lives in this repo (`deploy/compose.<env>.yml`), networks follow the keystone
  per-tenant pattern (`henley-website-<env>-net`, NPM attached), images tagged
  `henley-website:v2026.MM.DD.n` like Race Images.

---

## 3. Feature checklist (like-for-like)

### 3.1 Site chrome
- [ ] Sticky header: white/paper logo on Broadwater Deep (or teal) band, 9-item primary nav,
      phone number visible, "Enquire" button.
- [ ] Mobile menu: slide-in panel, 44px targets, focus trap, closes on Esc.
- [ ] Footer: main nav, social links, minor nav (Privacy, Disclaimer, Maintenance Request →
      Microsoft Forms), address/phone/email, © year (computed at build).
- [ ] Skip link, visible focus ring, `prefers-reduced-motion` honoured, WCAG AA contrast.

### 3.2 Pages (same URLs)
- [ ] Home: hero (brand tagline), "Do what you like" feature list, location teaser, CTA row
      (Enquire, Village Comparison Document), FAQ (25 Q&A) as accordion.
- [ ] Luxury Retirement Living, Location (map image + surroundings list), Health Club, Dining,
      Supported Living, Private Aged Care (with 8-Q FAQ + Schedule of Fees link) — each: hero,
      intro, feature lists, one CTA, testimonial where present.
- [ ] News index (cards, newest first) and 15 posts with prev/next, featured image, date.
- [ ] Contact: details, socials, enquiry form.
- [ ] Thank You (form confirmation; keep URL for analytics), Privacy Policy, Disclaimer, 404.

### 3.3 Documents
- [ ] Village Comparison Document (Form 3 VCD) and Schedule of Fees kept at their current
      `/wp-content/uploads/...` paths **and** given stable aliases
      (`/documents/village-comparison-document.pdf`, `/documents/schedule-of-fees.pdf`)
      that always point at the latest revision.

### 3.4 Enquiry form
- [ ] Fields identical to §1.5, labels always visible, HTML5 + server validation, honeypot,
      rate limit, reCAPTCHA v3 score stored, submissions persisted with an increasing integer id.
- [ ] Redirect to `/thank-you/`; graceful error page if the service is down (and the form
      degrades to a plain POST with JS disabled).
- [ ] henley-utils reader switched to the new store; nightly run verified end-to-end into
      Salesforce sandbox/`DRY_RUN` before cutover. Old GF entries archived to CSV.

### 3.5 SEO
- [ ] Per-page `<title>`, meta description, canonical, OG/Twitter (locale `en_AU`), JSON-LD
      (`Organization`/`LocalBusiness` with address+phone, `Article` for posts, `FAQPage` for the
      two FAQs).
- [ ] `sitemap.xml`, `robots.txt`, 301s: the two Redirection rules, `/sitemap_index.xml` →
      `/sitemap.xml`, `/post-sitemap.xml` and `/page-sitemap.xml` → `/sitemap.xml`,
      `/?p=<id>`-style shortlinks not required.
- [ ] Search Console re-verification, resubmit sitemap after cutover.

### 3.6 Analytics
- [ ] One GTM container snippet (decide which) in `<head>` + `<noscript>` iframe; GA4 configured
      inside GTM, or gtag `GT-TXH3QGV` directly if GTM is not actually used. Consent handling
      unchanged from today (none).
- [ ] Verify any conversion (form submit / thank-you pageview) still fires on dev before cutover.

### 3.7 Performance and security
- [ ] Images: AVIF/WebP with `srcset`, lazy-loaded below the fold, hero ≤ 200 KB; Lighthouse
      ≥ 95 mobile.
- [ ] Headers: HSTS (NPM), CSP (self + GTM/GA + fonts host), X-Content-Type-Options,
      Referrer-Policy, Permissions-Policy.
- [ ] No admin surface on the public site at all; content changes go through git + rebuild.

### 3.8 Cutover
- [ ] Retarget NPM hosts 5/11 to `henley-website-prod`, keep `/webhooks` → `henley-webhooks`.
- [ ] Stop `wp-prod-henley` / `db-prod-henley`; keep a final `mysqldump` + files tarball under
      `/mnt/persistent/stor/henley-website-archive/`; leave containers stopped for 30 days before
      removal. Remove the WP admin agency accounts from any remaining systems.
- [ ] Update henley-utils `.env` (`DB_*` no longer needed), delete the orphaned SharePoint leg.

---

## 4. Content migration proposals

| Content | Proposal |
|---|---|
| Privacy Policy, Disclaimer | Copy verbatim. (Privacy policy mentions the contact form and marketing updates — still accurate.) |
| Home FAQ (25) and Private Aged Care FAQ (8) | Copy verbatim into `faqs` collection; **flag the weekly-fee figures and "Retirement Villages Act" wording for the team to confirm** before publish. |
| Ten evergreen articles | Copy verbatim (light copy-edit for Australian spelling and brand vocabulary); keep slugs and dates. |
| Five 2023 resident-life posts | Copy as-is for like-for-like, but recommend the team decides whether to keep, refresh, or retire them; they date the site. |
| Service pages (Retirement Living, Location, Health Club, Dining, Supported Living, Private Aged Care) | Transfer the substance (lists, claims, testimonials) into new templates; re-style with brand tokens; re-write hero lines in brand voice; keep H1 keywords. |
| Home hero | New: brand tagline "A lifestyle resort like no other." over a brand-kit property photo; keep "Time to rediscover you" as the page title/meta for search continuity (or swap — decision). |
| Contact | Same details; confirm the phone number (§1.3). |
| Images | Heroes from `06_Imagery/Photography` (new) + selected existing lifestyle shots (bowls, dining, hairdresser, swimming, group, map) re-encoded. Stock images (`iStock`, `AdobeStock`, `shutterstock`) reused only if the licence is known; otherwise replace with the renovation renders / property photos. Resident-post photo sets re-encoded from the 3–5 MB originals to ≤ 300 KB. |
| Logos | Inline `logo-vector-fill-currentcolor.svg`; white variant on dark bands; PNG fallbacks not needed. Favicon/app icon: none exists in the kit — needs a decision (see §5). |
| Fonts | See decision in §5. |
| Old `/wp-content/uploads` tree | Serve read-only from the new nginx for at least 12 months so bookmarks, indexed PDFs, email signatures and henley-utils notification images keep working. |

---

## 5. Decisions needed from Scott

1. **Web font.** (a) Adobe Fonts web project (the site already loads a Typekit kit; Avenir Next
   is in the Adobe library if The Henley has a Creative Cloud licence), (b) buy a Monotype web
   licence for Avenir Next, or (c) use a free look-alike self-hosted (Nunito Sans, SIL OFL) with
   the brand fallback chain. Default if no answer: (c), swap later without template changes.
2. **Favicon / compact mark.** The kit has only the wide wordmark. Options: a teal-square
   monogram "H" derived from the wordmark, or commission a stacked mark. Default: monogram from
   the wordmark's "H" glyph, added to the brand repo.
3. **GTM.** Which container is live, `GTM-M3MV9VG` or `GTM-PGSH3HF7`? Default: load only
   `GTM-PGSH3HF7` and gtag `GT-TXH3QGV` (what Site Kit does), drop the agency container.
4. **Bot check on the form.** Reuse reCAPTCHA v3 keys from the WP options (default) or move to
   Cloudflare Turnstile (needs a Cloudflare account).
5. **Dev preview access.** Public but `noindex` (default), or behind Authentik forward-auth.
6. **Phone number** and the 2023 resident posts (keep / retire).
7. **Streams.** `henley-website` is not in `stream-repos.json`. Proposal: add it (root
   `/mnt/persistent/dev/henley-website`, checks `npm run check` + `npm run build`), run this as
   stream `website-rebuild`, register it in `keystone/docs/streams.md`, and treat the shared
   checkout on `main` as the nonprod deploy source. Default if no answer: proceed that way.

---

## 6. Proposed build order

1. Scaffold Astro project, token generation from `DESIGN.md`, base layout, header/footer, 404.
2. Content collections and a migration script that pulls page/post text from the live HTML
   (already captured this session) into Markdown for editing; images copied and re-encoded.
3. Service pages, home, FAQ component, news index + posts, legal pages.
4. Form service + SQLite store + henley-utils reader change + end-to-end dry run.
5. SEO layer (meta, JSON-LD, sitemap, redirects), analytics snippet, security headers.
6. Compose + Dockerfile, deploy `henley-website-nonprod`, retarget `dev.thehenley.com.au`.
7. Team review on dev; fixes; Lighthouse and accessibility pass.
8. Cutover checklist (§3.8).
