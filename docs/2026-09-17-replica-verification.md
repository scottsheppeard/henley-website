# Replica verification — 17 September 2026

The replica replaces the WordPress runtime while preserving its appearance.
The redesign remains a separate stream. This record covers the dev candidate;
production cutover requires the remaining checks in `runbook-cutover.md`.

## Changes since the 16 September pause

- `6d7331f`: recognise old dev-host asset references in HTML, inline JSON and
  CSS, fetch their production copies and serve them locally. Refresh contains
  339 files, including 301 assets (24 additional images). No retired-dev asset
  references remain in exported HTML/CSS.
- `195a941`: document replica acceptance and keep the live drain safeguards,
  Search Console ownership and externally linked email assets as production
  requirements. Scott's September 10 deferral of the drain rehearsal stands.
- `eebf832`: permit the observed Google Australia audience request in
  `connect-src`; separate production `.env.prod` from nonprod `.env`; explain
  the exporter's in-place stale-file limitation.

The console gate fails CSP violations, local network/HTTP failures and runtime
errors. External request failures are reported separately. The deliberate
404 exemption applies only to that probe's main-document HTTP 404, not a
server error or failed request. Both inherited GTM tags remain present.

## Local evidence

| Check | Result |
| --- | --- |
| Export regression tests | 30 passed |
| Enquiry receiver tests | 77 passed |
| Standard Node tests after adding browser fixtures | 15 passed |
| Console browser fixture | Local missing asset and CSP fail; external failure warns; probe 404 passes and probe 500 fails |
| Astro check before the follow-ups | 0 errors, 0 warnings |
| URL checker defect fixture | Passed, including both robots-header modes |
| Replica form → temporary receiver → temporary SQLite | Passed |
| Fresh export twice | All files and manifest identical except `fetched_at` |
| Export hashes | All 339 match their manifest entries |
| Local nginx image | Built; corrected policy passes `nginx -t` |
| Local strict URL/noindex gate | 87 passed, 0 failed, 0 outstanding |
| Corrected local console gate | All 58 page/width combinations pass; zero fatal findings |

The export refresh also changed live WP Rocket cache timestamps and an
Elementor floating-button nonce. Those are source changes, not content edits.
The fresh export contains no obsolete files; future in-place refreshes do not
automatically remove stale files, so removals require the README's fresh-tree
audit procedure.

The first console run exposed an observed `www.google.com.au` connection
and transient `ERR_NETWORK_CHANGED` failures. After the policy correction,
57 combinations passed before the long-running process was terminated; the
remaining desktop 404 probe was run separately and passed with zero fatal
findings. The combined logs cover every expected combination. External
Google tracking failures remain reported, not hidden.

### Screenshot assessment

All 28 pages were compared at 390 and 1280 pixels. The initial run reported
37 within the unchanged 0.5% threshold and 19 requiring review.

- Fourteen comparisons restore missing photographs: dining, health club,
  location, private aged care, luxury retirement living, news and news page 2,
  each at both widths. The page heights remain the same. Reviewed diff images
  localise the changes to the previously empty photo regions.
- Two comparisons are the intentionally shorter contact form. The omitted
  referral-source question moves subsequent content upward; the replacement
  retains the existing styling and interest checkboxes.
- Both thank-you comparisons initially showed a font-loading difference.
  An isolated rerun was 0.00% at both widths.
- The International Women's Day article initially matched at 390 and showed
  a small font/layout difference at 1280. Its isolated rerun matched at 1280;
  the rerun's mobile difference was the live origin failing to render its
  hero image, confirmed by inspecting both screenshots and the diff. Each
  width has a 0.00% match; the remote origin's loading is intermittent.

No thresholds were raised. Screenshots and raw reports are retained locally
under `replica/screenshots/` and the plan's `.superpowers/sdd/` workspace.

## Deployment and final gates

Pending at the time this record was started. Complete this section with the
landed commit, image, public URL/header/browser checks and enquiry cleanup
evidence before declaring the dev candidate verified.

## Production prerequisites

Dev acceptance does not complete the production cutover. Remaining work:
Scott's visual review; preserve and verify legacy staff-signature/notification
image URLs absent from the page-driven export; verify Search Console DNS
ownership; prove the nightly enquiry reader's dry run; refresh/review the
export immediately before cutover; and execute the runbook's backup, proxy,
webhook and live drain/reconciliation sequence. The inherited dead
`GTM-M3MV9VG` tag remains a separate decision for Scott.
