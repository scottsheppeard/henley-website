# Decisions

Choices made while rebuilding thehenley.com.au, with the reasoning that would
otherwise be lost. Newest first within each section. The scope this works to is
[the review](2026-09-09-rebuild-review.md); the build order is
[the plan](plan-2026-09-09-website-rebuild.md); the inventory of what the old
site does is [the baseline](2026-09-09-rebuild-baseline-and-proposal.md).

---

## The primary button on the deep ground

**On Broadwater Deep the primary button is Warm Sand with Deep text, not the
kit's Henley Teal fill.**

The kit's `button-primary` is Henley Teal `#0E5B70` on white. Every hero and
enquiry band on this site sits on Broadwater Deep `#083B4A`, and teal on deep
measures about 1.5:1 — the main action on the page was the least visible
element in it, and on a phone in daylight it disappeared. Warm Sand `#D9CFC0`
on Deep is 7.9:1 and Deep text on Warm Sand is 9:1. The teal button is
unchanged on light grounds. Raised 2026-09-10 from a mobile review; like the
focus ring, this belongs back in the kit as an `on-dark` variant.

The same review stacked the hero's two actions full-width below 480px, gave
the header 12px of vertical padding and a phone icon on the number, marked the
current page with a 3px Paper rule and a semibold label, floored the mobile
hero photograph at 240px, and rounded the top corners of the first content
band over the deep hero. Body text was already 18px, weight 400, line-height
1.56 from the kit and was left as it is.

## Photography

**The sample uses the professional shoots already held in SharePoint and on
the old site, at the resolution we have, rather than waiting for anything.**

Twelve photographs were chosen on 2026-09-10 from the review pull in
`assets/` (inventories: `assets/sharepoint/README.md`,
`assets/existing-site/README.md`; the originals are untracked). The source
of each file in `src/images/` is recorded in `assets/sharepoint/README.md`
by original filename:

| Site file | Source | Shoot |
|---|---|---|
| `broadwater-aerial.jpg` | `_53a1178_20  brighter.jpg` | Jan 2015 aerial series |
| `apartment-balcony.jpg` | `220415_418.jpg` | Brand & Co, April 2015 |
| `apartment-balcony-parklands.jpg` | `_53a1098_08.jpg` | Jan 2015 series |
| `apartment-view-type-b.jpg`, `-lounge-type-b`, `-kitchen-type-b` | `View / Lounge and Dining / Kitchen Type B 2.jpg` | 2017 apartment shoot |
| `pool.jpg` | `220415_379.jpg` | Brand & Co, April 2015 |
| `sky-deck-bowls.jpg` | `_MG_0790.jpg` | 2016 pool/Sky Deck shoot |
| `care-nurse-resident.jpg` | `Page 4-1.jpg` | 2019 newsletter set, full res |
| `care-dining-room.jpg`, `care-kitchen`, `care-chef`, `care-suite` | `THE HENLEY-PROOF-317 / 557 / 214 / 386.jpg` | Level 3 aged care shoot, 2048px proofs |

The aged care shoot exists in SharePoint only as 2048px proofs and the
photographer's details are gone. Scott's call: 2048px is more than the site
ever serves (the largest rendition is 1920px, and galleries top out at
1080px), so the proofs are used as-is rather than chased.

Source copies in `src/images/` are downscaled to 2400px JPEG so the repo does
not carry 5–8 MB originals; Astro generates the AVIF renditions at build.

**Consent.** `care-dining-room.jpg` and `care-nurse-resident.jpg` show
identifiable residents and staff from 2019 marketing shoots. No consent record
was found in SharePoint. They stay in the sample so the GM can see the page
as intended; before launch either the consent is confirmed or they are
replaced with the no-people frames from the same shoots (the household
lounge, `PROOF-543`, and the balcony, `PROOF-27`, are already in `assets/`).

The four brand-kit exteriors that carried the first sample were removed from
`src/images/`; they remain in the brand kit and in `assets/existing-site/`.

## Node version

**The repo pins Node 22 in `.node-version` and selects it per-repo, never globally.**

Astro 7 requires Node >= 22.12. The host's default is 20.20 from
`/mnt/persistent/node/bin`, and it has to stay there: `raceimages-webapp`'s
`node_modules` contains native modules (`sharp`) built against the Node 20 ABI,
and a silent bump to 22 would break its builds.

So Node 22.23.2 is installed under `~/.local/share/fnm` and reached two ways:

- **Interactive shells** — `~/.bashrc` evaluates `fnm env --use-on-cd`, which
  switches Node only on entering a directory that pins one. `cd` into this repo
  gives 22; everywhere else keeps 20.
- **Everything else** — `scripts/with-node.sh <command>`. Landing checks, agent
  shells and cron are non-interactive, never load `~/.bashrc`, and so would get
  Node 20. The wrapper resolves `.node-version` through `fnm exec` itself, so it
  works regardless of the caller's PATH. The stream tooling's checks for this
  repo are registered as `scripts/with-node.sh npm run check` / `... npm run
  build` for exactly this reason, and `npm ci` in a fresh worktree must be run
  through it too.

`FNM_RESOLVE_ENGINES=false` is set alongside, and is load-bearing rather than
tidiness: with fnm's default of `true` it also honours `package.json` `engines`,
and `raceimages-webapp` declares `node >=20`, which the newest installed version
satisfies — so entering that repo would silently hand it Node 22. With engines
resolution off, only `.node-version` and `.nvmrc` count.

`.node-version` says `22` rather than `22.23.2`, matching the `node:22-bookworm-slim`
build stage in the Dockerfile. The lockfile, not the Node patch level, is what
makes the build reproducible.

## Fonts

**Self-hosted Avenir Next WOFF2 subsets, on the basis that a web licence was
bought with the design package.**

The brand kit ships desktop-licensed Linotype TTFs (`05_Fonts/`,
Regular and Demi) with no WOFF2 and no licence file. The baseline document read
that as "no web licence exists"; that inference does not follow from the files
present. Scott confirmed during planning that a web licence was purchased as
part of the design package, and this build proceeds on that basis. If the
entitlement turns out to be desktop-only, the fallback chain below already
carries the site and only `src/styles/fonts.css` changes.

Fallback stack stays in place regardless: Avenir Next LT Pro → Avenir → Calibri
→ system sans, per the brand style guide.

## Focus ring colour departs from the brand kit

**The site's focus ring is Henley Teal on light grounds and Warm Sand on dark,
not the kit's Coastal Mist.**

`DESIGN.md` nominates Coastal Mist `#6FA3B2` as the focus ring. Against the
Paper page ground `#FAF9F6` that is **2.64:1**, below the 3:1 that WCAG 2.2
SC 1.4.11 requires of a focus indicator — a keyboard user would lose track of
where they are on the page. The substitutes measure 7.26:1 (Henley Teal on
Paper) and 7.86:1 (Warm Sand on Broadwater Deep).

This is a finding about the kit rather than a preference, and it should go back
to the kit rather than living only here: any Henley interface using that token
on a light surface has the same problem, not just this website. Raised with the
brand kit; until it changes, `--color-focus-ring` is deliberately unused by this
site and `src/styles/global.css` says why.

The same measurement pass moved two pieces of small text off Driftwood
`#8A7E6C`, which is 3.78:1 on Paper — fine for the accordion's plus/minus marks
at the 3:1 non-text threshold, under the 4.5:1 minimum for words. The
"(optional)" markers on form fields and the contact page's field labels are the
words most worth being able to read.

## Enquiry intake identity

**New submissions get ids starting at 100000.**

henley-utils de-duplicates against the full set of ids already in
`data/forms.db` (currently 1674–5229), not a high-water mark, and Salesforce
upserts on `WebFormID_c__c` keyed by that id. A store restarting at 1 would
therefore either be silently skipped as "already processed" or, worse, overwrite
an unrelated Lead. Starting well above the historical range removes both. No
historical enquiries are migrated — Salesforce already holds what matters.

## Enquiry form fields

**Four visible fields, down from seven.** Scott's instruction was to treat the
old Gravity Form as a guide rather than a specification, and to weigh completion
rate against what is genuinely useful when an enquiry is processed.

What the form asks now:

| Field | Required | Why it earns its place |
|---|---|---|
| Name | yes | Needed to reply, split into Salesforce FirstName/LastName, and read by the spam classifier. |
| Email | yes | The reply channel that always works, and `_find_existing_lead` matches on it first — it is how a repeat enquiry becomes a Task on the existing Lead instead of a duplicate. |
| Phone | no | Read by the classifier (an Australian number is authenticity evidence), matched second for duplicates, and the channel the sales team actually uses to arrange a visit. Encouraged, not required: making it mandatory would cost the privacy-conscious more than the extra numbers are worth. |
| Your message | no | The classifier's main signal, and the only field a salesperson reads before picking up the phone. |

What it stopped asking:

- **"How did you hear about us?"** Free text, so the answers were never
  analysable in aggregate. The classifier does not read it — it reads name,
  email, phone and message only. It reached Salesforce as
  `ReferralSource_c__c`, which is enrichment, not routing. And it asks a
  visitor to do attribution work that GA4 and the two Google Ads click
  conversions already do properly. It is the field on the old form with the
  worst ratio of completion cost to processing value, so it goes.
  The database column stays (unwritten) so the 9-tuple henley-utils reads keeps
  its shape and the question can return without a schema change.

- **"How can we help?"** as a question. The two interest checkboxes still
  exist and still populate `InterestType_c__c`, but on a service page the form
  arrives with the matching box already ticked, from the page the visitor is
  on. Someone enquiring from `/private-aged-care/` has already told us what
  they are interested in; asking again is a question that costs a completion
  and buys nothing. They remain visible and changeable, so the pre-selection is
  honest rather than hidden, and `/contact/` — reached from the nav, with no
  context to infer from — asks properly.

Nothing was added. "Preferred contact time" and "are you enquiring for
yourself?" were both considered and rejected: the second is something the
classifier already infers from the message, and paying a question for an
answer you can infer is a bad trade.

`page_path` is stored with every submission, so the context the form used is
recoverable later even though the visitor never typed it.

## Bot protection

**Honeypot, a minimum fill-time, per-IP and daily caps and a body-size limit at
launch. No CAPTCHA.** Recorded as a recommendation Scott can overturn.

The live WordPress form has a reCAPTCHA add-on installed but serves no
reCAPTCHA script, so today's effective protection is already the honeypot alone.
Legitimate volume is a handful a week, and the downstream classifier already
separates spam from the six categories. Leaving CAPTCHA out keeps the receiver
free of any outbound credential and lets the form work as a plain POST without
JavaScript — reCAPTCHA v3 and Turnstile both require client-side JS, so keeping
one would have meant either breaking the no-JS path or shipping a promise the
page cannot keep. If spam becomes a classifier-cost problem, Turnstile can go
behind the same endpoint later.

## Favicon

**Provisional only.** The brand kit has just the wide wordmark — no compact or
stacked mark, no favicon. A monogram derived from the wordmark's "H" lives in
this repo, *not* in the brand kit, and is flagged for Scott as a brand decision
rather than treated as an addition to the canonical kit.
