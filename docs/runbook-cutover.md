# Cutover runbook

Moving thehenley.com.au from WordPress to the static site. Written while the
pieces were being built, so it records what is actually true rather than what
was planned.

**Not yet ready to run.** Stage 3 (the remaining 22 pages, the news index and
feeds, the documents, the legacy assets) has to be finished, and the design
sample signed off, before any of this is worth doing. It is here now because
the sequencing decisions belong with the code that assumes them.

---

## The one thing that must not be lost

The NPM proxy host **`thehenley.com.au`** carries a `/webhooks` location pointing at
`henley-webhooks:8000`. **Systems beyond this website depend on it.**
Retargeting a host in NPM does not preserve custom locations automatically, and
nothing about the website will look broken if it disappears — which is exactly
why it is the first and last thing to check.

`www.thehenley.com.au` does **not** have one and does not need one: everything
on www is 301'd to the apex, so www callers arrive at `thehenley.com.au`. An
earlier version of this runbook said both carried it, and referred to them by
the numbers in `/data/nginx/proxy_host/*.conf` — which are invisible in the NPM
dashboard. Both corrected 2026-09-10.

**NPM's dashboard lists hosts by domain name.** The numbers below are only
useful when reading the generated configs on disk:
`4.conf` = `dev.thehenley.com.au`, `5.conf` = `thehenley.com.au`.
`www.thehenley.com.au` is no longer a proxy host at all — see the next
section.

It is not theoretical traffic. One day of that host's access log:

| Calls | Client | Path |
|---|---|---|
| 423 | 210.10.231.33 | `/webhooks/upload/fob` (every 10 minutes) |
| 11 | 13.54.1.75 | `/webhooks/painchek/assessment` |
| 4 | 54.92.76.241, 13.112.30.110 | `/webhooks/upload/insight` |

Three separate integrations, none of which is this website. Note that the
access log prints the *host-level* upstream in `[Sent-to …]`, so these lines say
`wp-prod-henley` even though the location proxies to `henley-webhooks:8000`.
Do not read that as evidence of where they went.

Screenshot `thehenley.com.au`'s configuration before touching it. The location,
verbatim from `/data/nginx/proxy_host/5.conf` on 2026-09-10, is:

```nginx
location /webhooks {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Scheme $scheme;
    proxy_set_header X-Forwarded-Proto  $scheme;
    proxy_set_header X-Forwarded-For    $remote_addr;
    proxy_set_header X-Real-IP          $remote_addr;
    proxy_pass       http://henley-webhooks:8000;
    include conf.d/include/force-ssl.conf;
}
```

## The other thing nobody owns yet: www → apex

`https://www.thehenley.com.au/contact/` 301'd to the apex, and **WordPress was
what issued that redirect** — `wp-prod-henley` answers `Host:
www.thehenley.com.au` with a 301 of its own. The NPM proxy host for www was a
plain one with a single `location /`; it did no canonicalisation.

The static site does not do it either, deliberately: `deploy/nginx.conf` says
TLS, HSTS and the apex/www canonicalisation are NPM's job, and the container
answers 200 to either hostname.

So the moment WordPress stopped, nothing would have redirected www — it would
have started serving the whole site a second time under a second hostname. The canonical
tags point at the apex, so it is duplicate content rather than an outage, but
it is a contract the migration manifest records (`canonicalisation: www to
apex`) and nobody currently keeps.

**DONE 2026-09-10, before cutover rather than on it.** Scott moved
`www.thehenley.com.au` out of Proxy Hosts and recreated it as a **Redirection
Host** → `https://thehenley.com.au`, 301, `$request_uri` preserved, reusing the
`npm-10` certificate. WordPress is no longer in the path.

Verified the same day: `/`, `/contact/`, `/?p=167` and a URL carrying UTM
parameters all 301 to the apex with path and query intact, on both port 80 and
443, in a single hop to a 200. Certificate renewal is safe — the redirection
host template includes `letsencrypt-acme-challenge.conf` *before* the `return`,
and a nonexistent challenge path answers 404 rather than redirecting, which is
the proof that the challenge location still matches. Cert runs to 28 Nov 2026.

```bash
curl -sS -o /dev/null -w '%{http_code} → %{redirect_url}\n' \
  https://www.thehenley.com.au/contact/
# expect: 301 → https://thehenley.com.au/contact/
```

The probe is `GET /webhooks/health`, which the service answers with
`{"status":"healthy","timestamp":"…"}` and HTTP 200. Use that, not an
arbitrary path: a 404 from `/webhooks/anything` proves only that *something*
answered, and the static site's own 404 would satisfy it just as well.

```bash
curl -sS -w '\nHTTP %{http_code}\n' https://thehenley.com.au/webhooks/health
# expect: {"status":"healthy","timestamp":"..."}  and  HTTP 200
```

Verified against production on 2026-09-10, before any cutover work.

---

## How the nightly reader actually works

Read this before the sequencing below, because the sequencing is a consequence
of it. Confirmed by inspection of henley-utils on 2026-09-10; the earlier
integration note in `plan-2026-09-09-website-rebuild.md` proposed *replacing*
the WordPress reader, and what was actually built reads both sources.

- **Two sources, selected by configuration.**
  `update_salesforce_leads.fetch_entries()` reads WordPress while `DB_HOST` is
  set, and the intake SQLite store while `INTAKE_DB_PATH` is set *and the file
  exists*. Both at once is the intended cutover state. Ids cannot collide:
  WordPress runs to ~5,300, the intake store starts at 100,000.
- **Both readers take a rolling 7-day window** — `date_created >= DATE_SUB(NOW(),
  INTERVAL 7 DAY)` on Gravity Forms, `created_at >= datetime('now','-7 day')` on
  the intake store. An enquiry that is never read inside its 7 days is never
  read at all.
- **De-duplication is the full set of ids** already in `data/forms.db`
  (`processed_ids()`), not a high-water mark. Re-presenting an old row is
  therefore safe; it is simply skipped.
- **A configured-but-unreachable WordPress database fails the whole task.**
  `_get_wp_connection()` raises, `fetch_entries()` does not catch it, and
  `main()` logs and re-raises. That night's *intake* enquiries are not read
  either. Stopping `db-prod-henley` while `DB_HOST` is still set does not
  quietly lose WordPress's last few enquiries — it stops enquiry processing
  altogether, and it looks like one failed task in the daily summary.
- **Retries after classification are generous, but only after classification.**
  `destination_catchup_rows(…, 'salesforce', days=60)` re-pushes any
  prospective-resident row with `sf_pushed IS NULL` for 60 days;
  `non_sales_notification_rows()` has no date window at all and retries until
  `non_sales_notified` is set. Neither helps a row that was never read from its
  source, because neither reads a source — they read `forms`.
- **`update_sales_forms.py` is retired** and is not scheduled. The non-sales
  route is `non_sales_enquiry_notifications.process_pending()`, run as its own
  daily task after the Salesforce step. Nothing in this cutover touches
  SharePoint.
- **A row in the intake SQLite file is receipt evidence, not delivery
  evidence.** Delivery is `sf_pushed` (sales) or `non_sales_notified`
  (non-sales) in `data/forms.db`.

**Terminal outcomes**, which is what "processed" means below:

| Classification | Terminal state in `data/forms.db` |
|---|---|
| `prospective_resident`, `spam_rating >= 70`, `duplicate` not `'Y'` | `sf_pushed IS NOT NULL` |
| `existing_resident_or_family` or `other_legitimate` | `non_sales_notified IS NOT NULL` |
| duplicate, spam, or below the confidence threshold | row present with `classification_at` set; nothing further is owed |

## Before the day

- [ ] Stage 3 complete: all 27 URLs, `/news/page/2/`, `/feed/`, `/news/feed/`,
      the two PDFs at their `/wp-content/uploads/` paths plus the
      `/documents/` aliases, and the audited legacy asset copy (the
      `branding/` tree used by every staff email signature, and
      `2025/09/lightspeed.png` + `sharepoint.png` used by henley-utils
      notification emails).
- [ ] `scripts/check-urls.sh --strict https://dev.thehenley.com.au` green.
      Strict is the gate: it requires every manifest URL, both feeds,
      `/news/page/2/`, both documents at both addresses, and every redirect's
      *destination*, and it checks that what came back is the right kind of
      thing rather than a 200. `--sample` is the progress report during Stage 3
      and is not launch acceptance.
- [ ] `scripts/check-urls-fixture.sh` green, so the gate itself is known to
      fail on the defects it claims to catch.
- [ ] The Village Comparison Document is linked prominently from every page
      (footer) and from the apartment pages, at
      `/documents/village-comparison-document.pdf`, and the file behind the
      alias is the current revision. Section 74(6)(a) of the Retirement
      Villages Act; see `docs/village-comparison-document.md`.
- [ ] The design sample signed off by the GM, and `docs/brief.md`'s held
      claims either evidenced or removed.
- [ ] **Search Console ownership secured by DNS TXT**, verified *before* Site
      Kit is removed. Site Kit's verification is an OAuth grant tied to the
      WordPress install; switching it off can take ownership with it, and
      re-verifying afterwards is much harder than verifying now.
- [ ] Scott adds the GTM trigger for the `enquiry_submitted` event the
      thank-you page pushes, and a blocking trigger on the two Ads conversions
      for `environment=nonprod` so preview traffic never counts.
- [ ] A test enquiry through dev lands in the nonprod intake store, and a
      `DRY_RUN=true` run of the nightly job classifies it and logs the
      Salesforce payload it would send.
- [ ] **The drain rehearsal below has been run end to end on nonprod**, with a
      synthetic enquiry either side of a simulated switch, one sales and one
      non-sales case, and one forced failure that the catch-up recovers.

## Cutover

1. **Rollback material first.** `mysqldump` of `wordpress`, plus a tarball of
   `/mnt/persistent/prod/www_henleycomau`, both under
   `/mnt/persistent/stor/henley-website-archive/`. Verify the dump restores
   into a scratch database before continuing — an unverified backup is not one.

   This dump is also the **final-source snapshot** the drain depends on. Take
   it again immediately after step 6, once WordPress can no longer receive a
   submission, and keep that second copy until reconciliation is clean: it is
   the only way to replay an enquiry that ages out of the reader's 7-day
   window.

2. **Bring up production.**
   ```bash
   docker network create henley-website-prod-net   # once
   cd /mnt/persistent/dev/henley-website
   scripts/with-node.sh npm ci                     # a fresh checkout has none
   scripts/with-node.sh npm run tokens
   cp deploy/.env.example deploy/.env              # then set TRUSTED_PROXY_IPS
   docker compose --env-file deploy/.env -f deploy/compose.prod.yml up -d --build
   ```
   `--env-file` is not optional: Compose reads `.env` from the directory it is
   run in, not from `deploy/`, and `deploy/.env` is gitignored so a fresh
   checkout has none. Without both, the receiver starts trusting no proxy —
   which looks exactly like a working deployment until someone tries to bypass
   a rate limit. This happened on nonprod on 2026-09-10 and the startup warning
   is what caught it.
   Attach `henley-website-prod-net` to `npm-attachment` in
   `/home/admin/henley-aws/docker-compose.yml`, recreate NPM, then set
   `TRUSTED_PROXY_IPS` to the npm-attachment address on that network and
   recreate the forms container. See "Trusted proxy address" below: an empty
   value is a misconfiguration, not a default, and the receiver says so at
   startup.

3. **Turn on the intake source, before the switch.**
   Set `INTAKE_DB_PATH=/mnt/persistent/stor/henley-website-prod/intake.sqlite`
   in `henley-utils/scripts/.env`, leaving `DB_*` alone. The nightly job now
   reads both stores. This deliberately happens *before* the traffic moves, so
   the new path is proven while the old one is still carrying the load.

   Confirm it with one `DRY_RUN=true` run before continuing, and check the log
   does not contain `INTAKE_DB_PATH is set but missing` — that warning is what
   a wrong path or an unmounted volume looks like, and the failure is otherwise
   silent.

4. **Retarget the `thehenley.com.au` proxy host** to
   `henley-website-prod:8080`, **re-adding `/webhooks` → `henley-webhooks:8000`**
   (verbatim, above) and adding `/api/enquiry` →
   `henley-website-forms-prod:8000`.

   `www.thehenley.com.au` needs nothing: it is a Redirection Host and has been
   since 2026-09-10, so it is already independent of WordPress.

   On the `/api/enquiry` location, set `client_max_body_size 64k;` in its
   Advanced box. NPM's global is `client_max_body_size 2000m`, so without it NPM
   will accept two gigabytes from a client and stream them at a receiver whose
   limit is 16 KB. The receiver stops reading at the limit and answers 413, but
   there is no reason to carry the upload that far. Copy `dev.thehenley.com.au`'s
   settings, which use `X-Forwarded-For $remote_addr` — an overwrite, and the
   shape the receiver is happiest with.

5. **Check, immediately:**
   ```bash
   scripts/check-urls.sh --strict https://thehenley.com.au
   curl -sS -w '\nHTTP %{http_code}\n' https://thehenley.com.au/webhooks/health
   ```
   Expect `{"status":"healthy",…}` and HTTP 200 from the second. Then submit
   one real enquiry through the live form and confirm the row appears in the
   production intake store.

6. **Stop the WordPress web application only.** This is the moment WordPress
   can no longer receive a submission, and it is the start of the drain.
   ```bash
   docker stop wp-prod-henley
   ```
   **Do not stop `db-prod-henley`, and do not clear `DB_*`.** The nightly job
   still has to read Gravity Forms for the enquiries taken in the days before
   this moment, and a `DB_HOST` pointing at a stopped database fails the whole
   task — the new site's enquiries included. The database is stopped later, in
   the drain, once reconciliation says it is safe.

   Removing either container is a separate, later decision.

## Draining WordPress

The window between "WordPress stopped taking enquiries" and "the last of them
reached Salesforce or reception" is the only part of this cutover that can lose
a real person's enquiry, silently, with everything looking healthy. Work
through it deliberately.

1. **Record the drain boundary.** With `wp-prod-henley` stopped and
   `db-prod-henley` still up, take the final id and timestamp:

   ```bash
   docker exec db-prod-henley mysql -u root -p"$WP_DB_ROOT_PASSWORD" wordpress -e "
     SELECT e.id, e.date_created
     FROM wp_gf_entry e
     JOIN wp_gf_form f ON f.id = e.form_id
     WHERE f.title = 'Contact Form' AND e.status = 'active'
       AND e.date_created >= DATE_SUB(NOW(), INTERVAL 14 DAY)
     ORDER BY e.date_created ASC;"
   ```

   Save that list. It is the set that must reach a terminal outcome, and its
   highest id is the last enquiry WordPress will ever take. Confirm no id
   appears after the switch: one that does means traffic is still reaching
   WordPress and the switch is not complete.

2. **Let the nightly job run.** Both sources are configured, so each run reads
   the remaining Gravity Forms rows and the new intake rows together.

3. **Reconcile, every day, until it is clean.** For the recorded ids, in
   `henley-utils/data/forms.db`:

   ```sql
   -- Nothing from the drain list may be missing from `forms`.
   SELECT :id WHERE :id NOT IN (SELECT id FROM forms);

   -- Sales route: owed a Salesforce push.
   SELECT id, date_submitted, sf_last_error FROM forms
   WHERE id IN (:drain_ids)
     AND lead_category = 'prospective_resident' AND spam_rating >= 70
     AND (duplicate = 'N' OR duplicate IS NULL)
     AND sf_pushed IS NULL;

   -- Non-sales route: owed a reception notification.
   SELECT id, date_submitted, non_sales_last_error FROM forms
   WHERE id IN (:drain_ids)
     AND lead_category IN ('existing_resident_or_family', 'other_legitimate')
     AND non_sales_notified IS NULL;
   ```

   Both queries empty, and no id missing from `forms`, is the gate. Anything
   still pending is either working through its retry (60 days for Salesforce
   catch-up, unbounded for the non-sales route) or is a real failure with an
   error recorded against it — read `sf_last_error` / `non_sales_last_error`
   rather than waiting another night.

   Run the same reconciliation over the intake store's ids for the same period,
   so the new source is proven at the same time as the old one is retired.

4. **If a row ages out of the 7-day window** before it was ever read, replay it
   from the snapshot in step 1 rather than waiting: restore the dump into a
   scratch database, point `DB_HOST`/`DB_NAME` at it for one run, and let
   `fetch_entries()` pick it up. **The replay must preserve the original
   Gravity Forms id** — the id is Salesforce's `WebFormID_c__c` external key and
   `processed_ids()` de-duplicates on the full id set, so an original id is
   correctly skipped if it was in fact processed, and correctly delivered once
   if it was not. Never re-key a replayed row.

5. **Only then remove the WordPress source.** In order:

   ```bash
   # a. prove the new source alone still works
   #    (clear DB_HOST in henley-utils/scripts/.env, leave INTAKE_DB_PATH set)
   cd /mnt/persistent/git/henley-utils && .venv/bin/python scripts/update/update_salesforce_leads.py --dry-run

   # b. one live nightly run with intake as the only source, checked in the log
   # c. and only after that:
   docker stop db-prod-henley
   ```

   Stopping the database before (a) and (b) is what the earlier version of this
   runbook told you to do, and it is the failure this section exists to prevent.

6. **Keep the rollback material** as step 1 requires: the verified dump, the
   post-switch dump, and the web-root tarball. Reconciliation being clean is
   what releases the *running database*, not the archive.

## After

- [ ] Resubmit the sitemap in Search Console and watch Coverage for a fortnight.
      `scripts/check-urls.sh --strict` catches what we predicted; Search Console
      catches what we did not.
- [ ] **`DB_*` stays set, and `db-prod-henley` stays running, until the drain
      reconciliation above is clean** — expect around 8 days, because the
      reader's window is 7, but elapsed time is not the gate and never was.
      Clear `DB_HOST` only after step 5 of the drain; the WordPress source then
      drops out on its own.
- [ ] Remove the two agency administrator accounts (`admin_max` / Rouken,
      `alex@pupdigital.com.au`) from anything they still reach.
- [ ] Confirm the Ads click conversions and the new `enquiry_submitted` event
      are both firing on the live site, in GTM preview.
- [ ] The root-owned PHP `core` dump dated 2026-09-07 in the old web root goes
      with the WordPress files, not into the archive.

## Trusted proxy address

`TRUSTED_PROXY_IPS` is the receiver's whole basis for believing
`X-Forwarded-For`, and therefore for its rate limits meaning anything.

**How NPM sets the header, confirmed 2026-09-10.** Every proxy host includes
`conf.d/include/proxy.conf`, which does:

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP       $remote_addr;
```

`$proxy_add_x_forwarded_for` **appends** the peer NPM observed to whatever the
client sent, which is exactly the model `client_ip()` reads — the last field is
NPM's own observation. There is **no proxy in front of NPM**: `dev.thehenley.com.au`'s access
log records the real visitor address as the client (`[Client 120.22.158.141]`
for a mobile visitor, `[Client 52.63.244.217]` for a request from this host),
so the chain is one hop and the last field is the visitor. If a CDN or load
balancer is ever put in front, this stops being true and both the receiver's
parsing and this note need revisiting.

**The `/api/enquiry` location is stricter still.** Added to `dev.thehenley.com.au` on
2026-09-10, it sets `X-Forwarded-For $remote_addr` — an **overwrite**, not an
append — so whatever the client sent is discarded before the receiver sees it
and the header holds exactly one address: the one NPM observed. `client_ip()`
reads the last field, so append and overwrite both give the right answer; this
is the safer of the two and the production location should be configured the
same way. Verified end to end on nonprod the same day: four submissions with
four invented first hops stored three rows, all carrying the real client
address, with the fourth refused.

~~Also outstanding on nonprod: `dev.thehenley.com.au` has only `location /`.~~ **Added
2026-09-10.** Host 4 now carries `/api/enquiry` →
`henley-website-forms-nonprod:8000` and the receiver has been exercised through
it. Configure the production hosts the same way, alongside `/webhooks`.

One thing that check taught, worth knowing before running it again: the per-IP
window lives in the worker's memory, so `docker restart` on the forms container
is what resets it, and a *validation failure* spends a slot just as a stored
submission does — the limiter runs before validation. Probe readiness with an
oversized body, which is refused at the ASGI boundary and costs nothing.

The value itself is the npm-attachment container's address **on this site's
network**:

```bash
docker inspect -f \
  '{{range $n, $c := .NetworkSettings.Networks}}{{$n}} {{$c.IPAddress}}{{"\n"}}{{end}}' \
  npm-attachment
```

Put it in `deploy/.env` and recreate the forms container. **It changes when
npm-attachment is recreated**, which happens every time a network is added to
it — including in step 2 above. Re-read it and recreate the forms container
after any NPM change, and check `docker logs henley-website-forms-prod | head`:
an empty list is a misconfiguration that looks exactly like a working
deployment until someone tries to bypass a rate limit.

## If it goes wrong

Point the `thehenley.com.au` proxy host back at `wp-prod-henley:80`, restore
the `/webhooks` location, and `docker start wp-prod-henley` (and
`db-prod-henley` if the drain had already reached step 5c).
`www.thehenley.com.au` as a Redirection Host is correct either way and needs no
rollback. Nothing in the cutover destroys WordPress state.

Enquiries taken through the new site in the meantime are still in the intake
store and are still read by the nightly job, because `INTAKE_DB_PATH` stays
configured through a rollback — that is the reason the reader takes both
sources rather than one, and the reason rolling back the website is not also a
rollback of the enquiries it received. Verify after any rollback that
`/webhooks/health` still answers 200 through both hosts.
