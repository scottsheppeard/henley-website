# Website review remediation plan

**Date:** 2026-09-10, Australia/Brisbane  
**Status:** Planned; implementation has not started.  
**Project:** `henley-website`, stream `website-rebuild`  
**Reviewed revision:** `294521b` — home: refurbished Level 4 lunch photo on the care tile  
**Purpose:** Preserve the findings from the 10 September review and provide a complete implementation handover for a later session.

Creating this plan does not implement the fixes or authorise a production cutover. Scott asked to save the plan so implementation can resume when he is ready.

## 1. Scope and current position

The review covered the existing design sample: home, apartment living, private aged care, contact, thank-you, the shared components, the enquiry receiver, and deployment configuration and instructions. It included code inspection, local reproductions and browser checks of the built site.

The remaining service pages, legal pages, news, feeds and legacy assets are already part of the full rebuild. Their absence is not a newly discovered regression. Completing this remediation plan does not by itself make the website ready to replace WordPress.

Read alongside:

- [Original rebuild plan](plan-2026-09-09-website-rebuild.md): overall stages and scope.
- [Website brief](brief.md): audiences, claims requiring confirmation and design acceptance questions.
- [Decisions](decisions.md): brand, form fields, intake identity and bot protection.
- [Cutover runbook](runbook-cutover.md): must be corrected under R03 and updated under R09 before use.
- [Receiver documentation](../forms/README.md): configuration and the contract with henley-utils.
- [Earlier scope review](2026-09-09-rebuild-review.md): this is the 9 September scoping document, not the 10 September code review.

At review time, the stream and `main` both pointed to `294521b` and the worktree was clean. Re-check this when resuming; it is a dated observation, not a guarantee about the next session.

### Evidence already obtained

| Check | Result at the reviewed revision |
|---|---|
| `scripts/with-node.sh npm run check` | Passed; Astro reported zero errors, warnings or hints; existing token tests passed |
| `scripts/with-node.sh npm run build` | Passed; six HTML pages including the 404 page |
| `forms/.venv/bin/python -m pytest forms/tests -q` | 30 passed; one third-party deprecation warning |
| Chromium layout checks | Five main pages at widths 320, 360, 390, 768, 1280 and 1440; no horizontal overflow observed |
| Invalid email containing a script element | HTTP 400 error response contained the unescaped script element |
| Container-equivalent proxy middleware | Four submissions from one actual client address, with different spoofed first hops, all returned 303 and stored the spoofed addresses |
| Device clock five minutes ahead; 45-second form fill | HTTP 303 to `/thank-you/?sent=1`, but zero stored rows |
| Chunked body of 20,050 bytes, without `Content-Length` | HTTP 303 and a stored row despite the 16 KB limit |
| Mobile service-page booking links | Destination heading at approximately 48px; sticky header covered the top 109px |
| Desktop home at 1440 × 900 | Main hero booking button began at approximately 983px, below the first screen |

These were local checks against source and built files. They did not establish the current deployed NPM header configuration, exercise the real Salesforce/digest pipeline, or perform a full accessibility audit. Local receiver tests used Python 3.11; the receiver image specifies Python 3.12, so include the container in later verification.

Temporary scripts and screenshots were saved under `/tmp` during the review. They are disposable and are not required to resume: the reproductions and expected outcomes are recorded below.

## 2. Work register

P1 means resolve before production cutover and prioritise for any exposed receiver. P2 means a concrete correction to complete before accepting the affected journey or launch gate. UX items are review recommendations. F01 is an additional bounded follow-up observed during the same review, separate from the nine main findings.

| ID | Priority | Work item | Completion evidence | Status |
|---|---|---|---|---|
| R01 | P1 | Escape error-page content | HTML-injection regression tests and rendered response check | Done |
| R02 | P1 | Make proxy trust consistent | Tests with runtime middleware plus container/proxy verification | Implemented; nonprod verification pending |
| R03 | P1 | Preserve final WordPress enquiries through cutover | Corrected runbook and demonstrated final-enquiry reconciliation | Implemented; rehearsal pending |
| R04 | P2 | Remove clock-dependent silent enquiry loss | Skewed-clock and no-JavaScript submissions are stored | Done |
| R05 | P2 | Restore and centralise the maintenance form URL | Both resident entry points reach the correct form | Pending |
| R06 | P2 | Enforce the body limit on received bytes | Oversized streamed requests return 413 before parsing | Done |
| R07 | P2 | Offset enquiry anchor scrolling below the sticky header | Service-page headings remain visible after clicks and direct fragment navigation | Pending |
| R08 | P2 | Reduce the homepage hero height | Initial-screen offer and booking action visible at agreed viewport sizes | Pending |
| R09 | P2 | Add strict launch URL verification | Missing required pages, feeds and redirect destinations fail the strict gate | Pending |
| UX01 | UX | Put the resident route before the sales form | Correct reading order and mobile placement | Pending |
| UX02 | UX | Replace copy explaining the website with useful visitor information | Copy reviewed against the brief without new unsupported claims | Pending |
| F01 | Follow-up | Expire inactive rate-limit buckets | Deterministic time-based regression test | Done |

## 3. Resume instructions and working constraints

The actual repository is one directory below the initial session workspace:

```bash
cd /mnt/persistent/git/worktrees/henley-website/website-rebuild
git status --short --branch
git log -6 --oneline
stream status
```

Before editing, read applicable `AGENTS.md`/`CLAUDE.md` instructions, check the `website-rebuild` row in `/mnt/persistent/git/keystone/docs/streams.md`, and compare the current files with this plan. Use repository evidence rather than unrelated files in the shared `~/.claude/plans/` directory.

Continue in the existing stream if it remains active. If it has been retired, follow the user's current stream-start procedure; do not switch branches in the shared checkout. Land coherent green slices through the stream tooling, keep the register current, and leave stream finishing to Scott. No PR is required.

Preserve these existing decisions unless later instructions explicitly change them:

- Static Astro pages and a small receiver; no new application framework.
- Ordinary form POSTs and working no-JavaScript submissions; no CAPTCHA added by this plan.
- Intake IDs starting at 100000, AUTOINCREMENT, naive UTC timestamps, WAL and the current field/interest mapping consumed by henley-utils.
- Name and email required; phone and message optional; service-page interests preselected and editable.
- Current page slugs, canonical origin, document aliases and preserved legacy URLs.
- Readable body text, visible focus indicators, dark-ground button contrast and the chosen photography.
- NPM `/webhooks` forwarding throughout eventual cutover and rollback.

Use `scripts/with-node.sh` for Node commands. The build reads the brand kit at `/mnt/persistent/git/branding/henley/DESIGN.md`, or the explicitly configured `HENLEY_DESIGN_MD` override. Do not change the machine's default Node version to make this repo build.

Use disposable local intake databases for reproductions. A test of the actual public enquiry endpoint may create a downstream record; conduct that later as a controlled nonprod rehearsal with the processor in its documented dry-run mode.

## 4. Implementation detail

### R01 — Escape error-page content

**Files:** [forms/app.py](../forms/app.py), [forms/tests/test_app.py](../forms/tests/test_app.py).

**Problem and reproduction:** `enquiry()` formats an invalid email into a message passed to `problem()`, which interpolates that message into HTML. Submit a name and an email value such as `<script>window.__henleyReview=1</script>` through the local test client, bypassing browser email validation. The response is HTTP 400 and contains an actual script element. Browser input validation does not protect the server endpoint.

**Implementation:**

1. Treat messages supplied to `problem()` as plain text and escape them at the HTML rendering boundary, preferably in that one shared helper.
2. Escape configured contact labels and attribute values where they enter the template as well. Keep the template's intended markup separate from message data.
3. Preserve the visible explanation, phone/email alternatives, response status and noindex metadata. A CSP change alone is not the fix.

**Acceptance:**

- Invalid values containing tags, quotes, ampersands and event-handler syntax render as text; none creates an injected element or executable attribute.
- Validation still returns 400, and body-limit/rate-limit/storage failures keep their expected statuses.
- Normal contact links remain usable and no enquiry content is added to logs.
- Existing successful-submission tests continue to pass.

### R02 — Make proxy trust consistent

**Files:** [forms/Dockerfile](../forms/Dockerfile), [forms/app.py](../forms/app.py), both [nonprod](../deploy/compose.nonprod.yml) and [production](../deploy/compose.prod.yml) Compose files, receiver tests/docs and the runbook.

**Problem and reproduction:** The Docker command enables Uvicorn proxy headers with `--forwarded-allow-ips '*'`. That middleware changes `request.client` before the receiver's own `TRUSTED_PROXY_IPS` logic sees it. With `ProxyHeadersMiddleware(app, trusted_hosts='*')`, post four valid forms carrying `X-Forwarded-For: <different spoofed address>, 203.0.113.9`. All four currently succeed and the stored addresses are the spoofed first hops.

This proves a configuration defect under an appended header chain; the live NPM chain must still be inspected before asserting deployed exploitability.

**Preferred implementation:**

1. Make the receiver's existing trust logic the single owner: disable Uvicorn's proxy-header rewriting with `--no-proxy-headers`, preserving the transport peer for `client_ip()`.
2. Inspect how the NPM custom enquiry location sets forwarded headers. For the documented single trusted proxy, it must append the address it observed or overwrite the header with that address. Document any additional proxy hop instead of assuming it away.
3. Configure the exact trusted NPM peer for each environment. Define how the value is refreshed after container recreation; an empty value must not be mistaken for a correctly configured deployment.
4. Validate/normalise candidate address values and ignore forwarded input from untrusted peers. Choose a documented fallback for malformed headers.
5. Keep health checks working and verify any URL/scheme behaviour affected by disabling Uvicorn's rewriting. Current successful redirects are relative paths.
6. Extend tests beyond direct `TestClient(app)` calls to cover the runtime middleware/configuration. The existing tests passed because they did not reproduce the Docker layer.

**Acceptance:**

- Changing spoofed leading hops cannot change the stored client address or evade the limit behind the trusted proxy.
- The fourth valid submission within an hour from one actual address returns 429, with three stored rows.
- Independent legitimate client addresses are counted independently.
- An untrusted direct peer cannot select its identity with forwarded headers.
- The same behaviour is demonstrated through a disposable container/proxy setup before nonprod verification.

### R03 — Preserve final WordPress enquiries during cutover

**Files:** [docs/runbook-cutover.md](runbook-cutover.md), relevant integration notes in [the rebuild plan](plan-2026-09-09-website-rebuild.md); henley-utils changes only if inspection shows they are needed, under that repository's own instructions.

**Problem:** The runbook stops `wp-prod-henley` and `db-prod-henley` immediately after switching traffic. It also says the nightly processor must keep reading WordPress for eight days. Retaining `DB_*` settings cannot make a stopped database readable. The older plan describes replacing the WordPress reader, while the newer runbook assumes dual-source intake; neither document alone establishes the reader's implemented behaviour.

**Implementation:**

1. Correct the runbook's immediate database-stop instruction before it can be used. Separate stopping the WordPress web application from stopping its database.
2. Inspect the current henley-utils `fetch_entries`, extra-field lookup, processing state, retries and source-failure handling. Confirm whether both sources are actually supported and what happens if one is unavailable.
3. Specify a drain procedure around the traffic switch: establish that WordPress receives no further submissions, record the final relevant enquiry IDs/timestamp, and reconcile them against terminal processing outcomes for both sales and non-sales routes.
4. Keep the old database available through the documented transition window and until that reconciliation has no unexplained pending legitimate enquiries. Eight days elapsed is not proof of successful processing.
5. Address the reader's rolling seven-day window explicitly: retain a recoverable final-source snapshot and define how an unprocessed row can be replayed if it ages out. Replays must preserve original IDs and existing deduplication behaviour.
6. Remove/disable the WordPress source configuration only after reconciliation; demonstrate that the new source still runs successfully, then stop the old database. Retain rollback material as the runbook requires.
7. Replace the placeholder `/webhooks/…` check with a known, safe read-only probe and its expected result. An arbitrary 404 cannot prove the correct upstream is reachable.
8. Use `scripts/with-node.sh npm run tokens` in runbook commands and reconcile the older integration description with the confirmed implementation.

**Acceptance:**

- A rehearsal includes a synthetic enquiry submitted just before the simulated WordPress switch and another just after it to the new source; both reach the expected processing outcome exactly once.
- Include one sales and one non-sales case across the rehearsal, plus a retry/failure case. A row existing in SQLite is only receipt evidence, not downstream delivery evidence.
- The database shutdown gate is based on reconciled IDs and outcomes, with a recovery procedure for aged-out rows.
- Website rollback preserves access to enquiries already received through the new source and retains `/webhooks` routing.
- The runbook contains one consistent sequence and remains marked not ready for production until the wider rebuild launch gates are met.

### R04 — Remove clock-dependent silent enquiry loss

**Files:** [forms/app.py](../forms/app.py), [EnquiryForm.astro](../src/components/EnquiryForm.astro), receiver tests, enquiry-flow script if necessary, receiver documentation and the bot-protection decision.

**Problem and reproduction:** `started_at` comes from the visitor's `Date.now()` but is subtracted from the server's wall clock. A clock five minutes ahead and a 45-second fill yields a negative elapsed time. The receiver returns the success redirect without saving the enquiry. The visitor is told it reached the team, and the thank-you page also queues a conversion event.

**Recommended implementation:** Remove client wall-clock timing as an admission/rejection condition. It is already optional and client-controlled, so it provides weak protection at a substantial cost when it is wrong. Keep the honeypot and corrected IP, daily and body-size limits.

Remove the unused `started_at` field/script and `MIN_FILL_SECONDS` configuration if timing is retired completely. Update tests and documentation deliberately, including the existing test that expects a fast submission to be silently discarded. If timing is retained for diagnostics, measure elapsed duration on the client using a monotonic timer and do not use it alone to discard a valid enquiry; autofill and assistive tools can also submit quickly.

**Acceptance:**

- Valid submissions are stored with clocks five minutes ahead, five minutes behind, and substantially wrong in either direction.
- Valid fast/autofilled submissions and JavaScript-disabled submissions are stored.
- Legacy or malformed timing values cannot turn an otherwise valid submission into a false success.
- Success for a legitimate accepted form corresponds to a saved row and the existing 303 redirect.
- Honeypot and rate-limit behaviour remain explicitly tested; update comments that overstate what a `sent=1` URL alone proves.

### R05 — Restore and centralise the maintenance form URL

**Files:** [src/site.ts](../src/site.ts), [contact.astro](../src/pages/contact.astro); reference: [captured contact page](../source/live-capture-2026-09-09/pages/contact.html).

**Problem:** The footer and contact page both link to `https://forms.office.com/r/maintenance`, a placeholder substituted for the captured form address.

**Implementation:**

1. Recover the real link from the captured contact page and verify that it still opens the intended Henley maintenance form. The captured value is:

   ```text
   https://forms.office.com/pages/responsepage.aspx?id=juKGyJ_MokG0gjcr_cUkcGG7XWGR5wtMgypQqRG4KFVUN1pGSExIVVI2MzlVUU9VMkNEU1RHWkZMNy4u
   ```

2. Export a single descriptive constant from `src/site.ts` and use it for both footer navigation and the contact-page action.
3. Preserve the accessible new-tab announcement and existing external-link treatment.

**Acceptance:** Open both links and confirm the intended form title and fields without submitting a maintenance request. Search the current `src` tree for the placeholder and confirm no occurrence remains. If the captured form has been retired, obtain the replacement from the form owner rather than inventing a shortlink.

### R06 — Enforce the body limit on bytes actually received

**Files:** [forms/app.py](../forms/app.py), receiver tests/docs; actual NPM enquiry-location settings during deployment rehearsal.

**Problem and reproduction:** `limit_body_size()` only checks `Content-Length`. A form-encoded body of 20,050 bytes sent in chunks without that header is parsed and accepted. Truncating the message after parsing does not bound the incoming work.

**Implementation:**

1. Keep the declared-length rejection as an early shortcut, then enforce the configured limit on actual body bytes before form parsing.
2. Prefer a small, explicit ASGI boundary or equivalent bounded reader that stops at the limit, returns the existing HTML 413 response, and correctly replays an accepted body to the application. Avoid an unlimited `request.body()` call followed by a size check.
3. Ensure only one response is sent, disconnects are handled, and oversized bodies cannot reach the insert path.
4. Check the NPM route's body limit as defence in depth. This route goes directly to the forms container, so changing only the static site's nginx configuration does not protect it.
5. Document that the budget applies to the encoded request, not just the message character count. Verify normal non-ASCII input as well as ASCII.

**Acceptance:** Known-length and unknown-length/chunked requests over the configured limit return 413 and store no rows. Under-limit requests, an exactly-at-limit body and chunk boundaries crossing the limit behave correctly. Include malformed length declarations at the ASGI boundary and ensure normal no-JavaScript forms continue to work. Add a real HTTP/container streamed-request check alongside in-process tests.

### R07 — Keep enquiry destinations visible below the header

**Files:** [global.css](../src/styles/global.css), [SiteHeader.astro](../src/components/SiteHeader.astro), [EnquiryBand.astro](../src/components/EnquiryBand.astro).

**Problem and reproduction:** On apartment and care pages at mobile widths, activate the hero booking button. `#enquire` scrolls to the viewport top; its heading starts around 48px below that, beneath a 109px sticky header.

**Implementation:** Apply an appropriate `scroll-margin-block-start` to the enquiry target or `scroll-padding-block-start` to the scrolling root. Account for the header's responsive height and wrapping instead of applying the desktop height everywhere. Use a CSS-first solution and retain immediate scrolling; review skip-link and keyboard-focus behaviour as well.

**Acceptance:**

- Both service-page buttons and direct URLs ending in `#enquire` leave the destination heading visible.
- Test widths 320, 360, 390, 768, 1280 and 1440, plus browser zoom/text enlargement and portrait/landscape changes.
- Keyboard navigation and focus indicators remain visible; there is no new horizontal overflow or unnecessary animated scrolling.
- Do not claim full accessibility conformance from this one correction.

### R08 — Bring the homepage offer and action into the first screen

**Files:** [Hero.astro](../src/components/Hero.astro), [index.astro](../src/pages/index.astro); [decisions.md](decisions.md) for the final rationale.

**Problem and reproduction:** The home image uses an uncapped 16:7 aspect ratio. At 1440 × 900 it occupies 630px below the header; the hero booking button starts around y=983. At 768 × 780, the 4:3 image pushes the heading to approximately y=733. The initial screen fails the brief's test of explaining the offer and presenting a useful next action.

**Implementation:**

1. Cap the hero image height responsively, using the real viewport and content requirements to choose a limit. Check the tablet breakpoint as well as desktop.
2. Keep the photograph above the text and retain readable type, contrast and action sizes. Do not solve the problem by shrinking text or placing it over a photograph.
3. Review the resulting crop and adjust object positioning if necessary so the useful location content remains visible.
4. Test full and inner hero variants to avoid making service-page photography unusably shallow.

**Acceptance:** At normal zoom, the homepage's factual description and complete primary booking button fit in the first screen at 1280 × 800 and 1440 × 900; review 768 × 780 as an explicit tablet case. At 360 × 780, preserve the existing readable layout and visible primary action. At smaller/zoomed viewports, prioritise readable reflow over forcing everything above the fold. Save representative before/after screenshots with viewport dimensions for Scott's design review.

### R09 — Add a strict launch URL gate

**Files:** [scripts/check-urls.sh](../scripts/check-urls.sh), [package.json](../package.json) if adding command aliases, [runbook-cutover.md](runbook-cutover.md); inputs: [migration manifest](../source/migration-manifest.json) and [redirects](../src/content/redirects.json).

**Problem:** Missing pages outside the hard-coded `BUILT` set are merely reported as outstanding. `/feed/`, `/news/feed/` and `/news/page/2/` are skipped entirely. The script can exit successfully when required content is missing, and a correct redirect header is accepted even if its destination is broken.

**Implementation:**

1. Introduce explicit `--sample` and `--strict` modes. Prefer strict as the default for a deployment gate; update sample-stage callers to request sample behaviour deliberately. The following command syntax is a proposed interface, not yet implemented.
2. In strict mode, require every manifest URL and required extra URL to satisfy its declared status or deliberate redirect disposition. No silent skip for feeds or pagination; unknown expectations must fail clearly.
3. Verify both the initial redirect status/target and a bounded traversal to the final intended resource. Report loops, unexpected origins and missing destinations.
4. Check enough content to avoid treating the homepage or an HTML error page as a successful feed/PDF/page response: content type, a minimal format signature or suitable page identity as appropriate.
5. Retain retired WordPress path and security-header assertions. Include stable document aliases and other launch assets specified by the runbook where the current manifest does not cover them.
6. Treat curl failures/timeouts and required missing resources as a nonzero exit. Sample mode should continue to expose its pending count and must not be described as launch acceptance.
7. Update all cutover commands to invoke strict mode explicitly. Use a small local fixture server to verify the checker's failure behaviour without depending on production.

**Acceptance:** A missing ordinary page, either feed, news page 2, required document, failed connection or broken redirect destination makes strict mode fail. A known partial sample can pass in sample mode while clearly reporting outstanding work. A complete fixture/deployment passes strict mode with zero unexplained exceptions. The current partial site is expected to fail strict mode until the original Stage 3 work is complete; do not weaken the gate to obtain a green result.

### UX01 — Put the existing-resident route before the sales form

**Files:** [contact.astro](../src/pages/contact.astro), and shared contact/navigation constants if useful.

The current contact page places “Already live here?” after the entire form, especially far down on mobile. Move a concise reception/maintenance route before the form in document order. Combine this with R05 so the route is functional. Keep the main enquiry form easy for prospective residents to find; a short resident callout or jump link is sufficient, without another large panel ahead of it.

**Acceptance:** Existing residents can reach reception or maintenance before encountering the sales form in both mobile visual order and screen-reader reading order. Desktop placement remains clear. Use manual browser/keyboard checks rather than brittle markup snapshots for this simple layout edit.

### UX02 — Replace copy about the website with useful information

**Files:** [index.astro](../src/pages/index.astro), other built page copy only where the same problem occurs; reference [brief.md](brief.md).

Replace the “Two ways to live here” explanation about having “their own pages, their own photographs and their own people to talk to” with a short explanation of what the two options offer the visitor. For example, distinguish independent apartment living with support available from the private aged-care household, then let the existing links do their job.

Review nearby copy for promises that imply immediate replies, guaranteed availability or a seamless care transition beyond the evidence held. Keep the edit grounded in confirmed facts; it is not an invitation to invent current staffing, fees, hours or resident outcomes.

**Acceptance:** The paragraph helps a visitor choose a route without discussing how the website was built. It remains readable at mobile widths and introduces no new claim requiring business sign-off. Scott/GM can review the final wording with the sample.

### F01 — Expire inactive rate-limit buckets

**Files:** [forms/app.py](../forms/app.py), receiver tests.

This additional observation was reproduced during the review but was not one of the nine main findings in its final summary. `within_ip_limit()` expires entries only for the currently visiting IP. Its global cleanup removes empty queues, but inactive queues never become empty. Insert one IP at time 0 and another at time 7200; the first remains in `_recent`.

While editing the limiter for R02, add bounded periodic expiry of inactive addresses, or an equivalent small data structure with explicit expiry. Preserve active windows; avoid an O(total historical addresses) operation on every request. Do not introduce Redis or another service for this workload.

**Acceptance:** A deterministic simulated-time test shows inactive windows being removed without requiring a return visit from that IP. Active addresses retain their counters, and the fourth-submission rule still holds.

## 5. Recommended delivery order

Land each coherent slice after the relevant checks pass. These are sequential implementation slices; they do not require multiple agents.

| Slice | Work | Exit condition |
|---|---|---|
| A — Correct the operational instructions | R03 runbook correction and reader inspection; record any remaining rehearsal dependency | No instruction to stop a still-required database; one explicit drain/reconciliation procedure |
| B — Make enquiry handling reliable | R01, R02, R04, R06; F01 while touching the limiter | Existing and new regressions green; actual runtime configuration covered; disposable enquiry flow passes |
| C — Repair the visitor journeys | R05, R07, R08, UX01, UX02 | Built pages reviewed across mobile/tablet/desktop; functional resident links; visible anchor targets and revised hero |
| D — Establish the release gate | R09 and associated runbook updates | Fixture tests prove strict failures; sample check remains useful; full-build gaps explicitly recorded |
| E — Rehearse deployment and hand over | Nonprod receiver/proxy checks, R03 reconciliation rehearsal, full-site strict check when Stage 3 is ready | Evidence recorded against deployed revisions; remaining business approvals and launch work named |

R01–R09 should not be marked complete based only on code changes. Where nonprod or downstream evidence is pending, record “implemented; verification pending” and the specific remaining gate. Slice E may wait for the original rebuild's Stage 3 and business inputs while the local remediation is already landed.

## 6. Verification commands and evidence

Run from the repository root. These commands already exist:

```bash
scripts/with-node.sh npm run check
scripts/with-node.sh npm run build
forms/.venv/bin/python -m pytest forms/tests -q
scripts/check-enquiry-flow.sh
git diff --check
```

Create the receiver virtualenv from `forms/requirements-dev.txt` if missing, following its README. Rebuild immediately before `check-enquiry-flow.sh`: the script only builds automatically when `dist` is absent, so an existing stale build would otherwise be tested. Its temporary database is suitable for local verification, but its default Uvicorn command does not prove the Docker proxy configuration; that requires the R02 check as well.

The review's restricted sandbox stalled the synchronous test client's event loop; the same 30 tests passed outside that sandbox. If this recurs, distinguish the execution-environment issue from an application failure and use an authorised local test environment. Never point a workaround at the live intake database.

After R09 is implemented, the proposed deployment checks are:

```bash
scripts/check-urls.sh --sample https://dev.thehenley.com.au
# Only after the full rebuild's required URLs and assets exist:
scripts/check-urls.sh --strict https://dev.thehenley.com.au
```

Browser evidence should cover the three hero pages, contact, thank-you, keyboard navigation, direct enquiry fragments, text enlargement, and 320/360/390/768/1280/1440px widths. Include the shorter desktop heights in R08. Supplement the focused checks with the broader accessibility pass already required by the rebuild plan.

Record completion evidence in this table when implementation starts. Use test results and artifact locations without copying real enquiry contents into the repo.

| Slice / IDs | Commit(s) | Local checks | Nonprod / rehearsal evidence | Remaining work |
|---|---|---|---|---|
| A / R03 | (slice A) | Reader inspected in henley-utils; `/webhooks/health` probe verified 200 against production 2026-09-10 | — | Drain rehearsal on nonprod (needs a WordPress-side synthetic enquiry and a `DRY_RUN` nightly run) |
| B / receiver | (slice B) | 75 receiver tests green; all new regressions verified failing against the pre-fix receiver; `check-enquiry-flow.sh` green; `check-proxy-trust.sh` green (and 8 failures against the pre-fix image) | NPM's append behaviour and the absence of a hop in front of it confirmed on host 4 | Nonprod end-to-end: NPM host 4 has no `/api/enquiry` location yet, so the receiver has never been reached through NPM |
| C / visitor journeys | — | — | — | Not started |
| D / R09 | — | — | — | Not started |
| E / deployment rehearsal | — | — | — | Not started |

## 7. Completion and launch boundaries

Remediation is complete when:

- [ ] Each R01–R09 item has implementation and acceptance evidence, with no unresolved P1 finding.
- [ ] UX01 and UX02 are reviewed, and F01 is resolved or explicitly recorded as deferred with a reason.
- [ ] The receiver's existing intake contract remains intact and both runtime/proxy and streamed-body checks pass.
- [ ] Mobile enquiry headings are visible; the revised hero and resident route pass the documented browser checks.
- [ ] The URL checker distinguishes a partial sample from a release-ready site, and the runbook uses strict mode.
- [ ] The old-source drain procedure has been reconciled with the real henley-utils implementation and rehearsed.
- [ ] Changes are landed, relevant documentation agrees with the code, and the stream/register records the next step.

The original launch dependencies still apply: remaining pages and assets, privacy wording, held care/fee claims, resident photography permissions, business review of the sample, analytics configuration, ownership/maintenance arrangements, backups and the production cutover procedure. Refer to the existing brief and runbook for their current status rather than treating this plan as their approval.

At handover, state whether the work is locally implemented, verified on nonprod, or ready for cutover. Those are different milestones. Leave the stream in place; Scott decides when to finish it.

## 8. Suggested prompt for the next implementation session

> Implement `docs/plan-2026-09-10-review-remediation.md` in the Henley website repo. First check the current branch, stream register and applicable project instructions, and reconcile this dated plan against current code. Work through the proposed slices, beginning with the runbook correction and enquiry receiver fixes. Preserve the intake contract and no-JavaScript form support, add focused regression coverage for the reproduced failures, and land coherent green slices. Record exact verification evidence and any downstream/nonprod gate still pending. Follow the existing deployment rules and keep the production cutover as a separate later step.
