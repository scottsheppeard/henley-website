# Cutover record — thehenley.com.au off WordPress

Date: 2026-09-23 (preparation) and 2026-09-24 (switch). Stream:
`stream/replica`. Procedure: [runbook-cutover.md](runbook-cutover.md). Times
are AEST; Gravity Forms `date_created` values are UTC.

**Outcome.** Since about 09:25 on 2026-09-24 `thehenley.com.au` is served by
the replica (`henley-website-prod`) from export `57c96d6`, and enquiries go to
`henley-website-forms-prod`. `wp-prod-henley` was stopped at 09:38.
`db-prod-henley` is still running and `DB_*` is still set, because the drain is
not finished. `dev.thehenley.com.au` still serves the nonprod replica until the
redesign needs it.

## Preparation, 2026-09-23

| Step | Evidence |
|---|---|
| Rollback material | `wordpress-20260923.sql` and `www_henleycomau-20260923.tar.gz` in `/mnt/persistent/stor/henley-website-archive/`. Restored into a scratch `mariadb:10.6`: 74 tables, 5,285 Gravity Forms entries, latest id 5285 at 03:15:41 UTC, identical to the live database |
| Final export | `57c96d6`. No content change since 2026-09-16: WP Rocket cache stamps, a different lazy-load/location-hash variant on four pages, and WordPress 7.1 → 7.1.2 in font and feed URLs. Same file set; 227 preserved files unchanged. `replica/tests` 34 passed. Landed and nonprod rebuilt from it |
| Dev URL gate | `check-urls.sh --strict --noindex https://dev.thehenley.com.au`: 97 passed, 0 failed, 0 outstanding. `check-urls-fixture.sh` green |
| Dev console | 58/58 page-width combinations `ok`, 0 fatal. 130 external warnings, the same classes as on 2026-09-17: the dead `GTM-M3MV9VG` (58) and tracking beacons aborted by navigation |
| Screenshot compare, live vs dev | Not re-run: the refresh changed no content, so the 2026-09-17 review stands |

## Switch, 2026-09-24

| Step | Evidence |
|---|---|
| Production network | `henley-website-prod-net` created and attached to `npm-attachment` with `docker network connect` at 08:12. NPM was not restarted (StartedAt unchanged, 2026-09-10); its nonprod address stayed `192.168.160.4`; production address `192.168.176.2` |
| Production containers | Both healthy. Receiver log: `X-Forwarded-For is believed from 192.168.176.2`, `intake database ready at /data/intake.sqlite`. Store directory created as `admin` first. From NPM: site 200 with the full CSP and no `X-Robots-Tag` |
| Intake source | Scott set `INTAKE_DB_PATH=/mnt/persistent/stor/henley-website-prod/intake.sqlite` in `henley-utils/scripts/.env` (`DB_*` unchanged). `DRY_RUN=true` run at 09:20: exit 0, no `INTAKE_DB_PATH is set but missing`, one WordPress submission read and filtered out |
| NPM | Scott retargeted `thehenley.com.au`. Generated `5.conf`: upstream `henley-website-prod:8080`; `/webhooks` → `henley-webhooks:8000` kept; `/api/enquiry` → `henley-website-forms-prod:8000` with `client_max_body_size 64k` |
| Immediate checks | `/webhooks/health` 200 `healthy`. `www` `/contact/` 301 to the apex. `check-urls.sh --strict --indexable https://thehenley.com.au`: 97 passed, 0 failed, 0 outstanding |
| Enquiry | One marked test through the live form: 303 to `/thank-you/?sent=1`, stored as id 100000 from the real client address `52.63.244.217`. Deleted afterwards; `sqlite_sequence` stays at 100000, so the first real enquiry is 100001 |
| Compare, dev vs production | 56/56 at 0.00% in the end. The first run aborted on `net::ERR_NETWORK_CHANGED` at `/location/` (a host network change, not the site) after flagging `/dining/` 390 (page heights 3381 vs 3453). The full re-run flagged only one article at 1280 (2334 vs 2382). Both isolated rechecks: 0.00%, equal heights. Both were one-off loading differences |
| Traffic | `wp-prod-henley` logged no request in the 10 minutes after the switch; the new site logged about 1,100 lines |
| WordPress stopped | 09:38: `docker stop wp-prod-henley`, then `docker update --restart=no` |
| Final-source snapshot | `wordpress-20260924-final.sql`, restored into a scratch database: 74 tables, 5,286 entries, latest id **5286** at 2026-09-23 20:52:33 UTC. Keep until reconciliation is clean |
| Drain boundary | `drain-boundary-20260924.tsv` (same directory): 54 active Contact Form entries from the last 14 days, ids 5233–5286 |

## First reconciliation, 2026-09-24 ~09:45

Against `henley-utils/data/forms.db` (read-only): 53 of the 54 drain ids are
present and classified. Nothing is owed to Salesforce or to reception. The
categories were 27 spam/scam, 17 business solicitation, 4 uncertain, 4
prospective resident (all pushed) and 1 other legitimate (notified). The only
id not yet read is 5286, which arrived at 06:52 AEST, after that morning's 00:30
run. The dry run read it and filtered it out, and the 2026-09-25 00:30 run is due
to read it for real.
Once it is present and classified, the gate in "Draining WordPress" step 3 is
met, and step 5 (clear `DB_HOST`, one intake-only dry run, one live intake-only
night, then stop `db-prod-henley`) can go ahead.

## End-to-end test and drain gate, 2026-09-24 09:51

Scott submitted a test enquiry through the live form ("Mike Frederickson",
resort-style living for a parent). It was stored as id **100001** from his own
address. `update_salesforce_leads.py` was run live on request, outside the
nightly schedule. It read two submissions, the intake row and WordPress's 5286,
in one Codex batch:

| Id | Category | Spam rating | Outcome |
|---|---|---|---|
| 100001 | `prospective_resident` | 98 | Pushed 09:51:21, Salesforce Lead `00QOl00000Ui1aDMAR` (a test, for Scott to remove from Salesforce) |
| 5286 | `business_solicitation` | 1 | Filtered; nothing owed |

All 54 drain ids are now terminal, so the gate in "Draining WordPress" step 3 is
met. Only `update_salesforce_leads.py` (and the retired
`update_sales_forms.py`) reads `DB_*`, so step 5 can start as soon as Scott
clears `DB_HOST`.

## Drain step 5b, checked 2026-09-27

Read-only, from the host. `DB_HOST` is empty in `henley-utils/scripts/.env`
and `INTAKE_DB_PATH` is set, as Scott left them on 2026-09-24.

| Night (00:30 AEST) | `update_salesforce_leads.log` |
|---|---|
| 2026-09-25 | **Failed**: `Codex spam classification batch 1 exited with status 1` — "Selected model is at capacity". The intake read had already succeeded; this is the classifier, not the source |
| 2026-09-26 | `[LIVE]: 9 submissions \| 2 pushed, 7 filtered out` (100002–100010) |
| 2026-09-27 | `[LIVE]: 5 submissions \| 0 pushed, 5 filtered out` (100011–100015) |

No night logged a WordPress or `DB_*` error. The intake store holds ids
100001–100015 (`sqlite_sequence` 100015) and every one is in
`henley-utils/data/forms.db` with `classification_at` set. The three
prospective residents are pushed: 100001 (the test, 24 Sep 09:51), 100002 and
100008 (both 26 Sep 00:31). The rest are spam or business solicitation; no row
is on the non-sales route, so nothing is owed to reception. **Step 5b is met.**

The failed night had a cost: 100002, submitted 2026-09-24 13:46 AEST, reached
Salesforce about 35 hours later, and 100008 about 16 hours later. The rows were
not lost, because the next night re-read the 7-day window, but one classifier
outage delays every enquiry of that day by a day. That is a henley-utils
question, not a website one.

**Host reboot, 2026-09-27 07:26.** `wp-prod-henley` stayed stopped (policy
`no`), which is the step 6 correction proving itself. `db-prod-henley` came
back up by itself (policy `always`), so step 5c is `docker stop` **and**
`docker update --restart=no`; the runbook now says so.

**Google Ads event on production.** `https://thehenley.com.au/thank-you/`
returns 200 and its body is byte-identical (sha256 `ba723e53…7292`) to
`replica/site/thank-you/index.html` at `a6ee04f`, with the
`enquiry_submitted` push present once; `replica/tests/thank-you-event.test.mjs`
passes against that file. It was deliberately not loaded with `?sent=1` in a
browser, which would record a real conversion. The page still carries
`GTM-M3MV9VG` alongside `GTM-PGSH3HF7`.

## Proxy address drift, found 2026-10-06

The 2026-09-27 07:26 reboot (above) also reassigned addresses on
`henley-website-prod-net`. Docker gives them out in start order and remembers
nothing: `henley-website-prod` took `.2`, `henley-website-forms-prod` `.3` and
`npm-attachment` `.4`. The receiver still believed `X-Forwarded-For` only from
`192.168.176.2`, NPM's address at the switch (above) and now the static site's,
so NPM was an untrusted peer and the receiver took NPM itself to be the
visitor. Nonprod drifted the same way: NPM's address on
`henley-website-nonprod-net` moved from `192.168.160.4` to `.3`.

| What | Evidence |
|---|---|
| From | 2026-09-27 10:46: every visitor attributed to `192.168.176.4` (NPM). The three-an-hour per-visitor cap acted as a site-wide cap |
| Refused | 758 POSTs answered 429, all in four bot-flood hours: 27 Sep 10:00, 3 Oct 19:00, 3 Oct 23:00 and 6 Oct 07:00. Outside those hours nobody was refused |
| Stored | Intake rows 100016 onward (through at least 100057) carry `192.168.176.4` as `remote_ip`. The visitors' real addresses are not recoverable. No downstream system reads that column |

**Fix.** The receiver now accepts CIDR networks (`829f6b7`), and the value it
is given becomes the website network's subnet, which survives reboots and NPM
recreations: `192.168.176.0/20` for production, `192.168.160.0/20` for nonprod.
It refuses to start on an entry it cannot parse, and logs an untrusted peer
that forwards an address, so a repeat is no longer silent.
`scripts/check-proxy-trust.sh` covers the network case (`cbe4660`). The
runbook's step 2 and "Trusted proxy address", `deploy/.env.example`, both
Compose files and `forms/README.md` now say subnet; the reasoning is in
[decisions.md](decisions.md), "The trusted proxy is a network, not an address
(2026-10-06)".

- Drain step 5c was executed 2026-10-06 10:36:
  `docker stop db-prod-henley && docker update --restart=no db-prod-henley`.
  `db-prod-henley` is stopped with restart policy `no`. Tonight's 00:30 run
  (2026-10-07) is the check that nothing still needed it.
- Deployed: (to be recorded)

## Where the runbook was wrong (corrected in place)

1. **NPM did not need recreating.** `docker network connect` attaches the
   network live. Recreating NPM would have interrupted every site it fronts,
   and could have reassigned its other network addresses. The compose file must
   still name the network so the next recreation keeps it.
2. **The production store directory must exist before `up`.** Otherwise Docker
   creates the bind-mount source as root, and the receiver runs as uid 1000.
3. **`docker stop` alone would not have kept WordPress stopped.** Its restart
   policy was `always`, so a daemon restart or reboot would have started it
   again. The policy is now `no`.

## Still open

- **Search Console DNS TXT** (Scott). There was no `google-site-verification`
  TXT record at 09:40. The replica serves the same HTML as WordPress did, so
  any tag-based verification still works. Site Kit's OAuth verification is gone
  with WordPress.
- ~~`henley-aws/docker-compose.yml` must name `henley-website-prod-net`~~
  **Done**: Scott, henley-aws `3f60ba8`, pushed. `docker compose config` passed.
- **The drain**: the gate is met (above). Step 5a is done: Scott cleared
  `DB_HOST` at 09:56 (`INTAKE_DB_PATH` kept). The intake-only `DRY_RUN=true` run
  at 09:57 exited 0 with "No changes required" and no warning or error. Step
  5b is met (2026-09-26 and 2026-09-27 nights, above). Step 5c was executed
  2026-10-06 10:36 (above). Still to do: check the 2026-10-07 00:30 night's
  log for any WordPress or `DB_*` error.
- **The proxy-trust redeploy** (above): both environment files set to their
  network's subnet, both receivers recreated, and each startup line checked.
  Open until "Deployed" is recorded.
- **Google Ads tracking** for the marketing partner: the `enquiry_submitted`
  event on the thank-you page is live (`7e23bd5`, checked on production
  2026-09-27). Still open: the `GTM-M3MV9VG` decision, and the CSP check for
  call tracking once their tag is in GTM Preview.
- The "After" list in the runbook.
