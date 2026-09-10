# The Henley website rebuild — assessment of the GPT review and plan to start building

Repo: `/mnt/persistent/dev/henley-website` (remote `scottsheppeard/henley-website`). Date: 2026-09-09.

**Follow-up, 2026-09-10:** The [review remediation plan](plan-2026-09-10-review-remediation.md)
records the findings from reviewing the built design sample, with implementation
steps and acceptance checks for a later session. That remediation has not started;
this document remains the overall rebuild plan.

## Changes from Codex review (one pass, all eight findings verified against the code)

1. **Intake IDs**: table is `id INTEGER PRIMARY KEY AUTOINCREMENT`, `sqlite_sequence` seeded to 99999, test asserts first row is 100000. (Plain `INTEGER PRIMARY KEY` ignores `sqlite_sequence`.)
2. **Timestamps**: receiver stores `created_at` as naive UTC `YYYY-MM-DD HH:MM:SS` (SQLite `datetime('now')`), which is exactly what `_convert_date_to_brisbane()` already parses. Codex suggested ISO-Z plus a mapper change; I keep the existing contract instead because it needs no henley-utils date changes, and add a test pinning it. The retired receiver's `localtime` default is explicitly not copied.
3. **WAL and read-only reader**: pragmas, `busy_timeout`, container UID = host `admin` so the `-wal`/`-shm` sidecars are readable, reader opens `mode=ro`; one-writer-plus-read-only-reader test added.
4. **henley-utils scope**: `SQLITE_DB_PATH` stays `data/forms.db` (state); new `INTAKE_DB_PATH` is source-only; end-to-end dry-run test of the nightly pair covering a sales row and a non-sales row.
5. **Stream tooling**: the keystone commit also updates `scripts/git/tests/test_stream.py` (three-repo assertion), `docs/stream-command.md` table and `docs/streams.md` wording.
6. **Migration manifest**: Stage 0 commits one regenerated `source/migration-manifest.json` (sitemap URLs, `/news/page/2/`, `/feed/`, shortlink id map, legacy redirects, titles and descriptions) produced by a committed script. The scratchpad list Codex found was URLs only; the shortlink map was printed but never saved.
7. **Stage gates**: the minimal receiver moves into Stage 1 before the nonprod deploy; nonprod loads the same GTM snippet and CSP with `environment=nonprod` in the dataLayer, and GTM stays disabled there until a blocking trigger for the two Ads tags exists.
8. **Tokens**: generator uses the source names (`colors`, `typography`, `spacing`, `rounded`) and emits only the component aliases the site consumes; Cortex and Henley Care tokens are skipped.

Also from Scott mid-review: **fonts** — proceed on the basis that a web licence for Avenir Next was bought with the design package. Self-host WOFF2 subsets built from the kit's TTFs. The fallback stack remains for robustness.

## Context

Two documents exist: Claude's technical baseline (`docs/2026-09-09-rebuild-baseline-and-proposal.md`, **still untracked**) and the GPT review with a revised brief (`docs/2026-09-09-rebuild-review.md`, committed as 0972537). The GM's ask, verbatim: "scope the project for the rebuild so that the language, branding and UI is assisting lead generation and reflecting our market position." Scott has confirmed: enquiry volume is a handful a week, no historical migration, and the reviewer's smaller scope is the one to build.

This plan (1) records which review findings I verified and where I disagree, and (2) sets out the first build sessions concretely enough to execute.

## 1. Assessment of the GPT review

I checked every factual claim I could reach read-only. Verdict: **accept the review's scope and sequence**, with the corrections and one push-back below.

**Verified (adopt as requirements):**
- GTM `GTM-PGSH3HF7` contains a Conversion Linker and two Google Ads click conversions (`880243114`, labels `ELcdCNaJ-psZEKrj3aMD` tel: and `GkCWCPi785sZEKrj3aMD` mailto:). No form or thank-you conversion. `GTM-M3MV9VG` returns 404. → Keep this container and gtag `GT-TXH3QGV`; drop the agency container.
- `/news/page/2/` is 200; `/news/page/3/` is 404; `/feed/` is 200; `www` and non-trailing-slash 301 to the apex canonical. Shortlinks `/?p=<id>` 301 to slugs (26 ids).
- The contact page exposes no reCAPTCHA script today; the effective protection is the honeypot.
- henley-utils: all MariaDB access is three inline functions in `scripts/update/update_salesforce_leads.py` (`_get_wp_connection` 108–121, `_get_form_id` 124–133, `fetch_entries` 136–167, `fetch_extra_fields_for_ids` 170–198). Records are **9-position tuples** `(id, name, email, phone, enquiry_text, date_created, referral_source, interest_type_1, interest_type_2)` indexed positionally by five call sites. Dedup is `processed_ids()` = full id set from `data/forms.db` (`modules/forms_database.py:68-71`), not a high-water mark as the review implied. Live forms.db holds ids 1674–5229. The collision consequence is worse than the review says: a reused id is silently skipped, or on the Salesforce side `WebFormID_c__c` upsert **overwrites an unrelated Lead**. → New store starts ids at **100000**.
- Astro current stable is **7.3.2**, requiring Node ≥ 22.12; host has Node 20.20 and no version manager.
- Brand kit: `DESIGN.md` front-matter (lines 1–396) is valid YAML with `{colors.x}`/`{typography.y}` placeholder references in `components`; 14 logo SVG variants; four 1920px photos; Avenir Next TTFs (Regular, Demi) in `05_Fonts/`.
- The prior session's live-site capture (27 pages as HTML + text, 2.3 MB) exists only in `/tmp/claude-1000/-mnt-persistent-dev-henley-website/9558bfc0-c43a-4842-bab2-e9b103f8df04/scratchpad/` and will be lost on tmp cleanup.
- A retired receiver exists at `henley-utils/containers/enquiry_capture/` (RETIRED.md, absorbed into Keystone 2026-08-12). Its `db.py` is a useful pattern reference for WAL + AUTOINCREMENT but must not be revived; its `localtime` timestamps are the trap noted above.

**Corrections to the review:**
- Its henley-utils line references (forms_database.py:79, :134) point at the wrong functions; the substance stands.
- "Google retired FAQ rich results" — accepted; FAQs stay as accessible `<details>` content without `FAQPage` markup as a launch item.

**One push-back — bot check.** The review asks us to resolve the CAPTCHA-vs-no-JS contradiction by keeping CAPTCHA and offering an alternative contact route. I recommend **no CAPTCHA at launch**: honeypot, minimum fill-time check, per-IP and daily submission caps, request-size limit. Reasons: today's site effectively runs honeypot-only; the downstream Codex classifier already exists to separate spam from the six categories; volume is a handful a week; this removes the receiver's only outbound credential and makes plain-POST submission real. If spam load becomes a Codex-cost problem, add Turnstile later behind the same endpoint. Scott can override at plan approval.

**Defaults taken (review §6):** favicon = provisional SVG from the wordmark's "H" glyph, kept in this repo (not the kit), flagged as a brand decision. Dev preview public with `noindex`.

## 2. Decisions from Scott (this session)

| Decision | Choice |
|---|---|
| Enquiry delivery for launch | henley-utils processor via a new SQLite intake store; classifier, Salesforce, reception digest unchanged |
| GM feedback source | Quoted verbatim above; brief drafted from it plus brand kit and existing content |
| Node 22 | fnm in user space, `.node-version` pinned |
| Sequencing | Draft brief, build design sample in parallel, GM confirms against the sample |
| Fonts | Licence held (purchased with the design package); self-host Avenir Next WOFF2 subsets from the kit TTFs |

## 3. Architecture (what gets built)

- **Site**: Astro 7.3.x (pinned, lockfile), TypeScript strict, static output, content collections `pages`, `posts`, `faqs`, `documents`. Hand-written CSS with `tokens.css` generated from `DESIGN.md`. Vanilla JS only for nav toggle and form enhancement. `@astrojs/sitemap`, `@astrojs/rss` (keeps `/feed/`), `astro:assets` for images. Fonts: `src/fonts/*.woff2` (Latin subset via fonttools `pyftsubset --flavor=woff2`), `font-display: swap`, brand fallback stack.
- **Prod container** `henley-website-prod`: multi-stage Dockerfile (`node:22-bookworm-slim` build → `nginx:alpine`), tagged `henley-website:v2026.MM.DD.n`. nginx: redirects, headers/CSP, 404, 410 for WordPress paths, `/legacy` audited-asset copy (not the WP root).
- **Form receiver** `henley-website-forms-<env>`: Python 3.12 FastAPI, ~200 lines, runs as UID 1000 (host `admin`), writes `/mnt/persistent/stor/henley-website-<env>/intake.sqlite` with `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`, one short transaction per submission; 303 → `/thank-you/?sent=1`. No Salesforce or DB credentials. NPM `location /api/enquiry` → receiver.
- **Networks**: `henley-website-<env>-net` (external, NPM attached, per `keystone/docs/network-segmentation.md`). `henley-webhooks` stays on `my_shared_network`; NPM keeps `location /webhooks` on hosts 5/11.
- **henley-utils**: `fetch_entries`/`fetch_extra_fields_for_ids` read the intake SQLite via `file:...?mode=ro` (new `INTAKE_DB_PATH`) and return the same 9-tuples; `_get_form_id` and pymysql go. `SQLITE_DB_PATH` (`data/forms.db`, processing state, catch-up, non-sales digest) is untouched.
  - **As built (2026-09-10), this is a dual source, not a replacement.** The WordPress reader stayed: `fetch_entries()` reads Gravity Forms while `DB_HOST` is set *and* the intake store while `INTAKE_DB_PATH` is set and the file exists, so cutover is configuration rather than a flag day. pymysql and `_get_form_id` are still there and `DB_*` is cleared at the end of the drain, not before it. The consequence the runbook turns on: a `DB_HOST` pointing at a stopped database raises out of `fetch_entries()` and fails the whole nightly task, intake enquiries included. See `docs/runbook-cutover.md`, "How the nightly reader actually works".

## 4. Repo layout (target)

```
henley-website/
  docs/                      brief, decisions, runbooks (existing two docs stay)
  source/live-capture-2026-09-09/   HTML + text rescued from /tmp (migration source)
  source/migration-manifest.json    generated: URLs, redirects, shortlinks, meta
  scripts/build-tokens.ts    DESIGN.md → src/styles/tokens.css
  scripts/build-manifest.sh  live site → source/migration-manifest.json
  scripts/export-content.ts  capture + manifest → src/content/* markdown (one-off, kept)
  scripts/check-urls.sh      manifest → status/redirect assertions against an env
  src/{layouts,components,pages,content,styles,fonts}
  public/                    favicon, robots.txt
  forms/                     receiver: app.py, schema.sql, tests/, Dockerfile
  deploy/                    Dockerfile, nginx.conf, compose.nonprod.yml, compose.prod.yml, legacy-assets.txt
  .node-version              22
```

## 5. Stages and tasks

### Stage 0 — Setup (first build session, ~1 sitting)
1. Commit the untracked baseline doc (direct on `main`).
2. Copy the /tmp capture into `source/live-capture-2026-09-09/` and commit; add a `README` naming its origin and date.
3. `scripts/build-manifest.sh`: from the live site, collect page/post sitemap URLs plus `/news/page/2/` and `/feed/`, each page's `<title>`, meta description, canonical and `rel=shortlink` id, and the two Redirection rules; write `source/migration-manifest.json`. Commit script and output.
4. Register the repo with the stream tooling in one keystone commit (direct on `main` after `git pull`; the xero-connector landing today touches other paths): add `henley-website` to `scripts/git/stream-repos.json` (`root` `/mnt/persistent/dev/henley-website`, `live: true`, checks `npm run check` and `npm run build`, `setup_note` "run npm ci in the worktree"); update `test_real_config_has_three_repos_and_two_deploy_checkouts` in `scripts/git/tests/test_stream.py:414` to four repos and assert the new entry; update the repo table in `docs/stream-command.md:107` and the "three repos" wording in `docs/streams.md`; run the stream test suite.
5. `stream start henley-website website-rebuild --no-launch --why "..."`, then `EnterWorktree` into `/mnt/persistent/git/worktrees/henley-website/website-rebuild`. All build work happens there; land fast-forward to `main` at each green slice.
6. Install fnm (`~/.local/share/fnm`), `fnm install 22`, write `.node-version`, add shell init to `~/.bashrc`.
7. Scaffold Astro (`npm create astro@latest`, minimal, TypeScript strict), pin versions, add `@astrojs/sitemap`, `@astrojs/rss`, `sharp`, `js-yaml`. `npm run check` = `astro check`. Commit.
8. `scripts/build-tokens.ts`: parse DESIGN.md front-matter, resolve `{colors.x}`/`{typography.y}` references, emit `src/styles/tokens.css` custom properties from `colors`, `typography`, `spacing`, `rounded`, plus only the component aliases the site uses (`page`, `page-dark`, `button-primary`, `button-secondary`, `input`, `card`, `nav-top`, `footer` if present); skip `cortex-*`, `henley-care-*`, `product-icon*`, `chart-*`. Wire into `prebuild`. Tests: snapshot of generated CSS; unresolved reference throws.
9. Fonts: `pyftsubset` the two TTFs to Latin WOFF2 into `src/fonts/`; `@font-face` in `src/styles/fonts.css`; record the licence basis in `docs/decisions.md`.
10. `scripts/export-content.ts`: from the capture and manifest, extract title, description, canonical, date, body HTML → Markdown per page/post into `src/content/`; emit `src/content/redirects.json` from the manifest. Commit output.

### Stage 1 — Brief, minimal receiver, design sample (sessions 2–3)
1. `docs/brief.md` (one page): the GM's objective verbatim; audiences (prospective residents 70+, adult children researching for a parent, existing residents/families); the two paths (apartment living, private aged care) and their relative prominence (default equal, GM decides); three or four differentiators drawn from existing copy and the style guide, each marked **evidence held / evidence needed**; primary CTA "Book a visit" and secondary "Call" with one consistent label set; definition of a useful lead; page matrix keep / rewrite / archive with URL disposition from the manifest (the home-care-package article → rewrite for Support at Home or archive with a dated note; the five 2023 resident posts → keep with honest dates unless GM retires them).
2. Base layout, header (logo, grouped nav, phone, "Book a visit"), footer, skip link, focus styles, reduced-motion, 404.
3. Home, `/luxury-retirement-living/` (representative service page), `/contact/` with the enquiry form, `/thank-you/`. Real copy from the brief; brand photography; the 25-question FAQ moved off the home hero into a "Questions" section lower on the page.
4. Minimal receiver (`forms/`): `schema.sql` with `enquiries(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), name, email, phone, referral_source, interest_apartment INTEGER, interest_aged_care INTEGER, enquiry_text, remote_ip, user_agent, page_path)` and `INSERT INTO sqlite_sequence(name, seq) VALUES ('enquiries', 99999)` on first init; `app.py` validating the seven fields, honeypot, fill-time floor, per-IP and daily caps, 16 KB body limit, `X-Forwarded-For` trusted only from the NPM address, insert, 303 to `/thank-you/?sent=1`; on write failure an error page that shows phone and email; `/healthz`. Tests (`TestClient`, temp DB): first id is 100000; `created_at` matches `%Y-%m-%d %H:%M:%S` and is UTC; a second connection opened `mode=ro` sees the row while the writer holds the file open; honeypot and caps.
5. Nonprod deploy: `deploy/compose.nonprod.yml` (site + receiver, UID 1000, bind mount `/mnt/persistent/stor/henley-website-nonprod`), network `henley-website-nonprod-net` (create, connect `npm-attachment`, update `/home/admin/henley-aws/docker-compose.yml`), retarget NPM host 4 (`dev.thehenley.com.au`) with `X-Robots-Tag: noindex` and `location /api/enquiry`. Build flag `PUBLIC_GTM_ENABLED` off for nonprod until Scott adds a GTM blocking trigger on the two Ads tags for `environment=nonprod`; the CSP is identical in both environments.
6. Review with Scott, then the GM and Giselle, against the brief's questions: can a visitor understand the offer, find their path, and know what happens next.

### Stage 2 — henley-utils integration (parallel with Stage 1 steps 2–3)
1. Direct commits on henley-utils `main`, per its CLAUDE.md (venv, `DRY_RUN` from `.env`, region dividers preserved): add `INTAKE_DB_PATH` to `scripts/.env`; replace `_get_wp_connection`/`_get_form_id`/`fetch_entries`/`fetch_extra_fields_for_ids` with SQLite readers opening `file:{INTAKE_DB_PATH}?mode=ro` (URI), `busy_timeout` set, 7-day window on `created_at`, same 9-tuple order (`interest_type_1`/`_2` derived from the two integer flags as the strings the classifier and Salesforce mapping expect today); remove pymysql and `DB_*`; mark `update_sales_forms.py` retired.
   - **As built:** the SQLite reader was *added alongside* the WordPress one rather than replacing it, so both can run during the drain; pymysql and `DB_*` stay until reconciliation is clean. `update_sales_forms.py` is marked retired and is not scheduled, as planned.
2. Tests: field mapping and tuple order against a temp intake DB; `fetch_extra_fields_for_ids`; `_convert_date_to_brisbane` on a receiver-format string; end-to-end dry run of `update_salesforce_leads.main()` then `non_sales_enquiry_notifications.process_pending()` with one prospective-resident row and one other-legitimate row, classifier stubbed, asserting the Salesforce payload (`WebFormID_c__c` ≥ 100000) and the digest content.
3. Live dry run: `DRY_RUN=true` nightly step against the nonprod intake DB containing one synthetic submission from the preview; confirm the Codex classifier call and logged payload.
4. Thank-you page pushes `enquiry_submitted` to `dataLayer` only when `sent=1` is present, then strips the parameter; Scott adds the GTM trigger. No conversion counted on plain revisits.

### Stage 3 — Full build (after sample sign-off)
**Two figures the captured content gets wrong** and every post carrying them must
be corrected as it is built (sales team, 2026-09-10; see `docs/brief.md`,
"Claims confirmed by the business"): the aged care household has **21 suites**,
not twelve — `whatever-care-you-need-we-can-provide-it.md`,
`the-henley-private-aged-care-its-our-approach-that-sets-us-apart.md` and
`private-aged-care.md` all say twelve — and apartments are for people **over
70**, not over 65. The built pages are already corrected; the captured source is
deliberately not, because it is the record of what the old site published.

Remaining service pages, legal pages, news index with `/news/page/2/` kept as a real second page, 15 posts with prev/next, documents at legacy paths plus `/documents/*.pdf` aliases (`Cache-Control: no-cache` on aliases, long max-age on dated files), redirects from `redirects.json`, per-page meta and JSON-LD (`Organization`, `Article`), sitemap, robots, RSS, GTM + gtag snippet, CSP verified with GTM/Ads under it on nonprod once the blocking trigger exists, legacy asset list (`branding/`, `2025/09/lightspeed.png` and `sharepoint.png`, dated PDFs, referenced images) copied into `deploy/legacy-assets`, image pipeline (AVIF/WebP, hero ≤ 200 KB), keyboard/zoom/screen-reader pass, Lighthouse.

### Stage 4 — Preview and acceptance, Stage 5 — Release
As in review §7: private preview checks, then rollback material (`mysqldump` + files tarball to `/mnt/persistent/stor/henley-archives/`), NPM switch on hosts 5/11 keeping `/webhooks`, live checks incl. a controlled test enquiry, stop WordPress containers, confirm Search Console ownership via DNS TXT **before** Site Kit goes away.

## 6. Verification

- Stage 0: `npm run check` and `npm run build` green in the worktree; keystone stream test suite green; `stream list` shows `website-rebuild`; `build-tokens` snapshot test passes; `migration-manifest.json` has 27 page/post URLs plus `/news/page/2/` and `/feed/` and 26 shortlink ids; `export-content` produces 27 content files.
- Stage 1: `dev.thehenley.com.au` serves the sample with `noindex`; 360px and desktop layouts reviewed; axe/keyboard pass on the four pages; the form submits to the nonprod receiver and the row (id ≥ 100000, UTC timestamp) is visible from a read-only host connection; receiver tests green.
- Stage 2: henley-utils `pytest` green including the new tests; `DRY_RUN=true` nightly run logs a classified synthetic entry with the correct Salesforce payload and digest; failure path returns the contact-details error page.
- Stage 3+: `scripts/check-urls.sh` asserts every manifest URL returns 200 or its intended 301 on nonprod; GTM preview shows tel/mailto conversions firing under the CSP.

## 7. Open items for Scott (not blocking Stage 0–2)

Favicon mark; phone number (5591 2111 vs 5557 0000); stock and resident photo permissions; privacy-policy wording against the actual data flow; who maintains content and the annual fee PDFs after launch; whether to retire the 2023 resident posts; the CAPTCHA push-back above; adding the GTM blocking trigger and the `enquiry_submitted` trigger.
