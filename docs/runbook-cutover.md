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

NPM hosts 5 (`thehenley.com.au`) and 11 (`www.thehenley.com.au`) each carry a
`/webhooks` location pointing at `henley-webhooks:8000`. **Systems beyond this
website depend on it.** Retargeting a host in NPM does not preserve custom
locations automatically, and nothing about the website will look broken if it
disappears — which is exactly why it is the first and last thing to check.

Screenshot both hosts' configuration before touching them.

## Before the day

- [ ] Stage 3 complete: all 27 URLs, `/news/page/2/`, `/feed/`, `/news/feed/`,
      the two PDFs at their `/wp-content/uploads/` paths plus the
      `/documents/` aliases, and the audited legacy asset copy (the
      `branding/` tree used by every staff email signature, and
      `2025/09/lightspeed.png` + `sharepoint.png` used by henley-utils
      notification emails).
- [ ] `scripts/check-urls.sh https://dev.thehenley.com.au` green with zero
      outstanding.
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

## Cutover

1. **Rollback material first.** `mysqldump` of `wordpress`, plus a tarball of
   `/mnt/persistent/prod/www_henleycomau`, both under
   `/mnt/persistent/stor/henley-website-archive/`. Verify the dump restores
   into a scratch database before continuing — an unverified backup is not one.

2. **Bring up production.**
   ```bash
   docker network create henley-website-prod-net   # once
   cd /mnt/persistent/dev/henley-website
   npm run tokens
   docker compose -f deploy/compose.prod.yml up -d --build
   ```
   Attach `henley-website-prod-net` to `npm-attachment` in
   `/home/admin/henley-aws/docker-compose.yml`, recreate NPM, then set
   `TRUSTED_PROXY_IPS` to the npm-attachment address on that network and
   recreate the forms container.

3. **Turn on the intake source, before the switch.**
   Set `INTAKE_DB_PATH=/mnt/persistent/stor/henley-website-prod/intake.sqlite`
   in `henley-utils/scripts/.env`, leaving `DB_*` alone. The nightly job now
   reads both stores. This deliberately happens *before* the traffic moves, so
   the new path is proven while the old one is still carrying the load.

4. **Switch NPM hosts 5 and 11** to `henley-website-prod:8080`, **re-adding
   `/webhooks` → `henley-webhooks:8000`** and adding
   `/api/enquiry` → `henley-website-forms-prod:8000`.

5. **Check, immediately:**
   ```bash
   scripts/check-urls.sh https://thehenley.com.au
   curl -sS -o /dev/null -w '%{http_code}\n' https://thehenley.com.au/webhooks/…
   ```
   Then submit one real enquiry through the live form and confirm the row
   appears in the production intake store.

6. **Stop WordPress**, do not remove it:
   ```bash
   docker stop wp-prod-henley db-prod-henley
   ```
   Leave both stopped for 30 days. Removing them is a separate, later decision.

## After

- [ ] Resubmit the sitemap in Search Console and watch Coverage for a fortnight.
      `scripts/check-urls.sh` catches what we predicted; Search Console catches
      what we did not.
- [ ] **Leave `DB_*` in place for at least 8 days.** The nightly job takes a
      7-day window, so WordPress's last enquiries are still arriving through it
      after the switch. Clearing it sooner drops them silently. After that, clear
      `DB_HOST` and the WordPress source drops out on its own.
- [ ] Remove the two agency administrator accounts (`admin_max` / Rouken,
      `alex@pupdigital.com.au`) from anything they still reach.
- [ ] Confirm the Ads click conversions and the new `enquiry_submitted` event
      are both firing on the live site, in GTM preview.
- [ ] The root-owned PHP `core` dump dated 2026-09-07 in the old web root goes
      with the WordPress files, not into the archive.

## If it goes wrong

Point NPM hosts 5 and 11 back at `wp-prod-henley:80`, restore the `/webhooks`
location, and `docker start wp-prod-henley db-prod-henley`. Nothing in the
cutover destroys WordPress state, and enquiries taken through the new site in
the meantime are still in the intake store and still read by the nightly job —
which is the reason it reads both sources rather than one.
