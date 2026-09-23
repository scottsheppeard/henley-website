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
- **`henley-aws/docker-compose.yml`** must name `henley-website-prod-net` under
  `npm-attachment` and in the top-level `networks:` block (Scott; the agent's
  edit was refused by the permission classifier). Until then, an NPM
  recreation takes the site down.
- **The drain**: reconcile after tonight's run, then step 5.
- **Google Ads tracking** for the marketing partner: the `enquiry_submitted`
  event on the replica thank-you page, the `GTM-M3MV9VG` decision, and the CSP
  check for call tracking.
- The "After" list in the runbook.
