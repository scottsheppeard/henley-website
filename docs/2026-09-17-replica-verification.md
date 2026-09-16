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

`stream land replica --repo henley-website --yes` landed and registered
`8ded51264441` on main. Its required checks passed: Astro 0 errors/0 warnings,
15 Node tests and a complete 29-page Astro build. The first build attempt was
interrupted before any main update to restore the prior worktree's image
cache: Astro sources were unchanged and all 84 overlapping cache files were
byte-identical. The normal landing checks and build were then rerun; none
were skipped.

At 09:05 Brisbane, the `site` service alone was rebuilt using the nonprod
Compose file and `deploy/.env`. Deployed image:
`sha256:3df129a8fef4500c86b889c5c781666af75b93e2c122761f2ac1bd5705d0bb6f`.
The site is healthy; the forms receiver's image/start time remain unchanged.
WordPress production continues running.

| Public dev check | Result |
| --- | --- |
| Strict URL and noindex checks through NPM | 87 passed, 0 failed, 0 outstanding |
| Deployed artifact integrity | All 339 file hashes match the export; nginx and policy bytes match source |
| Chunked 20KB POST | Receiver's helpful 413 response |
| Browser form submission | Stored, redirected to `/thank-you/?sent=1`, thank-you heading visible |
| Invalid email containing a script element | Escaped 400 response |
| Valid POST with invented forwarding address | Stored, 303 redirect |
| Fourth request with a different invented address | Helpful 429; no extra row |
| Honeypot after the rate limit | 303; no row |
| Stored data and cleanup | Exactly two synthetic rows, IDs 100011/100012, same actual client address and `/contact/`; both deleted; zero marker rows remain |

The browser submission used the first hourly test slot, then invalid-email
and forged-header valid requests used the other two. This exercised all the
planned behaviours without restarting the receiver or waiting for another
hourly slot. No real enquiry was removed.

Public console coverage is 58 page/width combinations with zero fatal findings
across the full run and exact isolated rechecks. Desktop passed 29/29 on the
first run. Mobile initially had two 30-second network-idle timeouts
(`/internationalwomensday/` and `/how-it-works-the-costs-of-retirement-living/`);
both passed isolated rechecks. External tracking/network warnings remain
visible and nonfatal; no CSP or local-asset failures were suppressed.

Public screenshot coverage is all 28 pages at 390 and 1280: initially 48/56
within 0.5%, with eight comparisons reviewed:

| Page / width | Evidence and disposition |
| --- | --- |
| Contact, both | Intentional shorter form, as agreed in the spec |
| Privacy policy, 390 | Fallback font on live initially; rerun reversed which origin used the fallback. External font loading remains intermittent |
| Location, 1280 | Isolated rerun matched 0.00% at both widths |
| Private aged care, 390 | Isolated rerun matched 0.00% at both widths |
| Supported living, 1280 | Inspected live screenshot lacked styles and logo while candidate rendered correctly; rerun timed out waiting for network idle |
| Private aged care approach article, 1280 | Isolated desktop rerun matched 0.00%; initial mobile matched. Rerun mobile showed incomplete stylesheet loading on both origins, confirmed in both screenshots |
| Amazing artists, 1280 | Inspected live screenshot had a blank grey hero; candidate displayed the correct photo. Rest of layout and page heights matched |

These are explained comparisons, not a claim that every raw screenshot run
exited successfully. No thresholds were raised. Intermittent external font
and page-loading behaviour remains a limitation for Scott's visual review.
Restoring dev-host images also makes those URLs available to the still-running
WordPress site; its appearance can therefore improve without a production
container deployment.

Raw public logs are retained in the local SDD workspace alongside the local
evidence. Dev verification is complete; production approval is still pending.

## Production prerequisites

Dev acceptance does not complete the production cutover. Remaining work:
Scott's visual review; preserve and verify legacy staff-signature/notification
image URLs absent from the page-driven export; verify Search Console DNS
ownership; prove the nightly enquiry reader's dry run; refresh/review the
export immediately before cutover; and execute the runbook's backup, proxy,
webhook and live drain/reconciliation sequence. The inherited dead
`GTM-M3MV9VG` tag remains a separate decision for Scott.
