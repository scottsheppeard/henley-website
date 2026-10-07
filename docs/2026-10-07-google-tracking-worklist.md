# Google tracking worklist for thehenley.com.au — 7 October 2026

This file is a self-contained brief for a Claude Code session running on
Scott's MacBook with Chrome and the browser extension. That session has no
access to the website repository or the server. It works only in the Google
dashboards, in the browser profile where Scott is already signed in.

Written from the server-side session after reviewing ten screenshots Scott
took on 7 October 2026, decoding the tag container Google currently serves
for the site, and reading the September email thread with Pup Digital.

## Status, 7 October 2026 (later the same day)

Most of this file was overtaken within hours, and no browser session ran it.

- A service account (`scripts/google/README.md`) now reads Analytics and Tag
  Manager from the server, which answered Part A except for Google Ads and
  Search Console. The findings: the four GA4 key events measure views of the
  Location page and a `/thanks/` page that does not exist; only Ads account
  `751-464-6535` has traffic this year; the container's users are the Henley
  login and `alex@pupdigital.com.au` (Publish).
- Part B1 to B4 are `scripts/google/ga_settings.py`. Part C2 is
  `scripts/google/gtm_enquiry.py`, and the website side changed with it: see
  `docs/decisions.md`, "Enquiry conversions (2026-10-07)". Scott applied both
  and the container was published as version 3 that afternoon.
- Still as written here: B0 (Pup's access, held until the Tag Manager build
  is applied), B5 (Search Console by DNS), C1, C3, C4, C5 and the Google Ads
  questions in A4.
- The email to Pup Digital is on the Review Desk, To send:
  `pup-2026-10-07-enquiry-conversion-setup`.

## How to work through this file

1. Do Part A first. It is read-only: look, and write down what you find in a
   new file called `google-tracking-findings.md` next to this one, using the
   template at the end. Scott brings that file back to the server session.
2. Do Part B next. These are small settings changes that Scott has agreed in
   principle by handing you this file. Tell Scott what you are about to
   change before each one, and record the old and new value.
3. Part C needs a decision from Scott or from Pup Digital first. Do not act
   on a Part C item until Scott says so in your session.
4. Part D is for the server-side session. Do nothing with it.

### Rules for the whole job

- Never press **Submit** or **Publish** in Tag Manager unless Scott tells you
  to in your session, for that specific change.
- Never delete, unlink, archive or move to trash anything unless a step in
  Part B says to, or Scott tells you to.
- Never remove or downgrade a user without Scott's say-so for that user.
- Do not touch Google Ads campaigns, budgets, bids or billing at all.
- Never submit the real enquiry form on the website to test something. A
  real submission creates a sales lead. To test the enquiry event, load
  `https://thehenley.com.au/thank-you/?sent=1` instead (see step C2).
- Scott types any password or two-factor code himself.
- If a screen does not match what a step describes, stop and record what you
  see. Google renames and moves these screens often.

## What is known today

| Thing | Value |
|---|---|
| Live site | `https://thehenley.com.au` (the `www` name redirects to it) |
| Dev site | `https://dev.thehenley.com.au`, which loads the same tags |
| Analytics account | `thehenley`, id `108222553` |
| GA4 property | `www.thehenley.com.au - GA4`, id `398547918`, Brisbane time, AUD |
| GA4 web stream | id `5873509418`, measurement ID `G-YRX87W827V`, stream URL `http://www.thehenley.com.au` |
| Google tag in the page HTML | `GT-TXH3QGV`, which sends to `G-YRX87W827V` |
| Tag Manager account / container | account `6221327270`, container `179782643` = `GTM-PGSH3HF7` ("thehenley.com.au") |
| Second container in the page HTML | `GTM-M3MV9VG`. Google returns 404 for it. Owner unknown. |
| Google Ads conversion ID | `AW-880243114` (this is not an Ads customer number) |
| Ads accounts linked to GA4 | `751-464-6535` "The Henley" and `693-655-6794` "The Henley On Broadwater - QLD - 70715", both linked 22 July 2023, "Linked by: Unknown" |
| DNS | Hosted at Crazy Domains. The only root TXT record is SPF. |
| Marketing partner | Pup Digital. Current contacts: Carrie Riessen `carrie@pupdigital.com.au` and Daniella (Dani) Pozzolungo `dani@pupdigital.com.au`. `alex@pupdigital.com.au` appears in Analytics and in the container's history. |
| Henley people | Scott Sheppeard (technology), Giselle Spice (Sales Manager), Blake Johnston (General Manager) |

Direct links:

- Analytics admin: `https://analytics.google.com/analytics/web/#/a108222553p398547918/admin`
- Tag Manager workspace: `https://tagmanager.google.com/#/container/accounts/6221327270/containers/179782643/workspaces/3`

### What the website does

- Every page loads the Google tag `GT-TXH3QGV` directly, and separately loads
  the container `GTM-PGSH3HF7`. Page views reach GA4 through the Google tag,
  not through Tag Manager.
- The enquiry form posts to the site's own server, which redirects the
  visitor to `/thank-you/?sent=1`. That page pushes
  `{ event: 'enquiry_submitted' }` to the `dataLayer` once, then removes
  `?sent=1` from the address bar. A reload does not push it again.
- That push is a Tag Manager event. GA4 does not receive it unless a tag in
  the container forwards it.
- The phone link (`tel:07 5591 2111`) and email link
  (`mailto:info@thehenley.com.au`) appear only on `/contact/`.

### What Pup Digital asked for, and what they have been told

Pup Digital runs the Google Ads campaigns (Performance Max and a Brand
Search campaign; $2,395.74 spent and 80 conversion actions in July to
September 2026).

- On 23 September they asked for: the existing container kept on every page;
  a conversion on a completed enquiry form, raised as a `dataLayer` event;
  phone conversions through Google call forwarding with a minimum call
  length; and container access for `carrie@pupdigital.com.au` and
  `dani@pupdigital.com.au`.
- On 24 September Scott told them the `enquiry_submitted` event was live, to
  trigger on it with Page Hostname equals `thehenley.com.au`, that email-link
  clicks should stop counting as conversions, and that phone-link clicks
  should stop counting once call forwarding is live. He asked them to tell
  him when a call tag is in Preview, before publishing, so the site's
  security headers can be checked.
- At that time the login that owns `GTM-PGSH3HF7` could not be used, so Scott
  offered a new Henley-owned container as a fallback. **That fallback is no
  longer needed**: Scott now has the login.
- Pup replied that they have no access to either container and never have.
  That does not match the container history, which shows
  `alex@pupdigital.com.au` adding a tag two years ago.
- On 28 September and again in their 1 October quarterly report to the
  General Manager, Pup said they are still waiting for container access, and
  that since the new site went live the campaigns are getting weaker
  conversion signals. **Giving them access is the one thing holding up their
  work.**

### What the review found

1. **No enquiry-form conversion is live.** The published container (version
   2) holds three tags: the Conversion Linker, an Ads conversion on any
   `tel:` link click (label `ELcdCNaJ-psZEKrj3aMD`), and an Ads conversion on
   any `mailto:` link click (label `GkCWCPi785sZEKrj3aMD`). Nothing fires on a
   form submission.
2. **A form conversion was built and never published.** The workspace shows
   two pending changes, a tag and a trigger both named "PD* Thankyou Page",
   added by `alex@pupdigital.com.au` about two years ago.
3. **GA4 has four key events and 1,394 of them this year, but which events
   they are is not known.** They were set up for the old WordPress site. Some
   may have stopped firing when the site was replaced on 24 September 2026.
4. **GA4's "Conversions" section shows 0 conversions configured**, with a
   warning icon.
5. **Enhanced measurement is on but measures page views only.**
6. **The stream URL is the old `http://www.` address.**
7. **Redact data shows "Email inactive" and "URL query parameter keys
   inactive".**
8. **Two Ads accounts are linked and it is not known which one is live.**
   GA4 reports $7,522.19 of ad cost this year, so at least one is spending.
9. **Tag Manager rates the container "Needs Attention" with 2 issues.**
10. **Search Console ownership is not secured by DNS.** The old verification
    went with WordPress.
11. Collection is healthy: 426 active users and 2.3K events in the last 7
    days, and "Data collection is active in the past 48 hours".
12. The API log shows the app "AgencyAnalytics" reading the property as
    `dani@pupdigital.com.au` several times a day. That is Pup's reporting
    tool and is expected.

Already done by Scott on 7 October: removed `newsxtend.analytics@news.com.au`
from the Analytics account, and changed `dani@pupdigital.com.au` from
Administrator to Editor.

## Part A — look and record (no changes)

### A1. GA4 key events

Admin → Data display → Key events. For each of the four, record the event
name and whether it is switched on.

Then Reports → Engagement → Events. Set the date range to 1 September to
today and, for each key event, record the daily count either side of
24 September 2026. The question is whether any key event dropped to zero, or
appeared, on or after that date.

Also record every event name in the Events report for the last 28 days, with
its count.

### A2. GA4 "Conversions" section

Advertising → Tools → Conversion management. Record what is listed, and the
text behind the warning icon on the Conversion performance report.

### A3. GA4 settings to read

Record the current value of each:

- Admin → Data collection and modification → Data retention (event data
  retention period, and "Reset user data on new activity").
- Admin → Data collection and modification → Data collection (Google signals
  on or off, and the user-provided data setting).
- Admin → Data collection and modification → Data filters (list them, with
  their state).
- Admin → Data display → Attribution settings (model, and the key event
  lookback windows).
- Data streams → the web stream → gear icon beside Enhanced measurement
  (which of the toggles are on).
- Data streams → the web stream → Configure tag settings → Show more: "List
  unwanted referrals", "Define internal traffic" and "Configure your
  domains".
- Admin → Product links → Search Console links (any link present?).
- Admin → Property → Property change history, last 12 months: who changed
  what. Summarise; do not copy every row.

### A4. Which Ads account is live

Reports → Acquisition → Traffic acquisition (or the Google Ads report in the
Advertising section). Add "Google Ads account name" or "Google Ads customer
ID" as a dimension, date range this year. Record cost and sessions for each
account.

If the signed-in Google account can open Google Ads
(`https://ads.google.com`), then for each of `751-464-6535` and
`693-655-6794` record:

- whether the account opens at all for this login, and with what access
  level;
- whether any campaign is enabled, and the last date with spend;
- Admin → Access and security: every user and manager account, with access
  level;
- Goals → Conversions → Summary: every conversion action, with its source
  (website tag, GA4 import, calls), whether it is Primary or Secondary, its
  status, and its count for the last 30 days;
- which account the conversion ID `AW-880243114` belongs to. Open a
  website-sourced conversion action → Tag setup → "Use Google Tag Manager";
  it shows the conversion ID and label. Match the labels
  `ELcdCNaJ-psZEKrj3aMD` and `GkCWCPi785sZEKrj3aMD` to their action names;
- conversions per day for each action from 10 September to today. Pup says
  the signals weakened when the site changed on 24 September. Record whether
  the daily numbers show that, and for which action.

Look only. Change nothing in Google Ads.

### A5. Tag Manager

In the workspace for `GTM-PGSH3HF7`:

- Open the tag "PD* Thankyou Page" and the trigger "PD* Thankyou Page".
  Record every field: tag type, conversion ID, conversion label, trigger
  type, and the trigger's conditions. Do not save, even if prompted.
- Click "View 2 issues" under Container quality and record both.
- Tags, Triggers and Variables: list everything, with type and, for tags,
  the firing triggers.
- Versions: list each version with its date, who published it, and its name.
- Admin → Container → User management, and Admin → Account → User
  management: every user with their account and container permission. Note
  in particular whether `alex@pupdigital.com.au`, `carrie@pupdigital.com.au`
  or `dani@pupdigital.com.au` is listed, and any login that looks like a
  former staff member or a former agency.
- Go to "All accounts" at the top left. List every Tag Manager account and
  container this login can see. State plainly whether `GTM-M3MV9VG` appears
  anywhere.

### A6. Search Console

Open `https://search.google.com/search-console`. Record which properties
this login can see for `thehenley.com.au` (Domain property, or URL-prefix
properties for the `http`, `https`, `www` variants), whether each is
verified and by what method, and Settings → Users and permissions for each.

## Part B — changes to make

Tell Scott before each one. Record old and new values.

### B0. Give Pup Digital access to the container (do this first)

Do A5 before this, so the user list is recorded as it was.

In Tag Manager for `GTM-PGSH3HF7`: Admin → Container → User management → +
→ Add users. Add `carrie@pupdigital.com.au` and `dani@pupdigital.com.au`
with container permission **Publish**. If the screen insists on an account
permission, choose **User**, not Administrator.

Then tell Scott it is done, so he can reply to Carrie. The reply should
repeat the two requests from 24 September: trigger on the custom event
`enquiry_submitted` with the hostname condition, and tell Scott when the
call tag is in Preview, before publishing.

### B1. Keep event data for 14 months

Admin → Data collection and modification → Data retention. If event data
retention is 2 months, set it to 14 months and save. This affects only
Explorations, not standard reports, and only data collected from now on.

### B2. Correct the stream URL

Data streams → the web stream → pencil icon. Change the stream URL from
`http://www.thehenley.com.au` to `https://thehenley.com.au`. Leave the
stream name alone. This is a label; it does not affect collection.

### B3. Turn on email redaction

Data streams → the web stream → Redact data. Turn on email redaction. Leave
URL query parameter redaction off. The enquiry form does not put personal
details in the address, so this is a safeguard and changes no report.

### B4. Widen enhanced measurement

Data streams → the web stream → gear icon beside Enhanced measurement. Turn
on **Scrolls**, **Outbound clicks** and **File downloads**. Leave **Form
interactions**, **Site search** and **Video engagement** off. Form
interactions would count attempts and spam alongside real enquiries; the
site has no search.

### B5. Secure Search Console by DNS

Only if A6 found no verified Domain property.

1. In Search Console, add a property of type **Domain** for
   `thehenley.com.au`. Copy the `google-site-verification=…` value.
2. Scott signs in to Crazy Domains. In the DNS settings for
   `thehenley.com.au`, add a **new** TXT record on the root (`@`) with that
   value.
3. Do not edit or delete the existing record
   `v=spf1 include:spf.protection.outlook.com -all`. Email depends on it.
4. Back in Search Console, press Verify. If it fails, wait ten minutes and
   try again; do not re-add the record.
5. Sitemaps → submit `https://thehenley.com.au/sitemap-index.xml` (with a
   hyphen; checked on 7 October, it returns the sitemap).
6. In Analytics: Admin → Product links → Search Console links → Link, choose
   the new Domain property and the web stream.

Record the TXT value in the findings file so the server session can confirm
it resolves.

## Part C — needs a decision first

### C1. Access tidy-up

After Part A, give Scott one list of every person and manager account found
across Analytics, Tag Manager, Google Ads and Search Console, marking any
that are not `thehenleyonbroadwater@gmail.com` or Pup Digital. Scott decides
each. Suggested end state:

- at least two Henley-controlled administrators on each product, so one lost
  mailbox or phone does not lock Henley out again. Scott's plan is a Henley
  service account that is not tied to one staff member, with two-factor
  authentication on a number or device Henley controls;
- check the recovery phone and recovery email on
  `thehenleyonbroadwater@gmail.com` itself. Its two-factor step was tied to
  a former staff member's private phone. Scott does this himself;
- Pup Digital: Editor on the GA4 property, **Publish** on the container
  `GTM-PGSH3HF7`, and User (not Admin) on the Tag Manager account;
- ask Pup whether `alex@pupdigital.com.au` still works there, and remove
  that login if not;
- nobody from a former agency.

### C2. The enquiry conversion (Pup Digital builds, Scott approves)

The agreed design, for whoever builds it in Tag Manager:

- **Trigger:** Custom Event, event name `enquiry_submitted`, with the
  condition Page Hostname equals `thehenley.com.au`. Do not use a page-view
  trigger on `/thank-you/`: that page can be opened without submitting
  anything.
- **Tag 1:** Google Ads Conversion Tracking, conversion ID `880243114`, with
  the label of a form-submission conversion action from the live Ads
  account.
- **Tag 2:** GA4 Event, measurement ID `G-YRX87W827V`, event name
  `generate_lead`. Then in GA4, mark `generate_lead` as a key event.
- Add the same hostname condition to the existing `tel:` and `mailto:`
  triggers, so the dev site stops counting.
- In Google Ads, make the form conversion Primary. Stop counting the
  `mailto:` click as a conversion now, and the `tel:` click once call
  forwarding (C3) is live. This is what Scott and Pup agreed on 24
  September.
- The event fires for every saved submission, including spam that Henley
  filters out before leads reach Salesforce, so form conversions will run
  somewhat above genuine leads. Pup has been told.

Compare this with what A5 found in "PD* Thankyou Page". If that old tag uses
a page-view trigger, it should be rebuilt rather than published as it is.

To test in Tag Manager Preview: connect Preview to
`https://thehenley.com.au/thank-you/?sent=1`. The event `enquiry_submitted`
should appear once in the left-hand list, with both tags fired on it. Loading
`https://thehenley.com.au/thank-you/` without `?sent=1` should fire neither.

**Before anything is published**, tell Scott, so the server session can run
its page checks against the Preview build. Extra Google hosts may need
allowing in the site's security headers, and a tag blocked by those headers
fails silently.

### C3. Call conversions with a Google forwarding number

Pup Digital asked for this. It needs a "Calls from website" conversion action
in the live Ads account and a "Google Ads Calls from Website Conversion" tag
in the container, set to replace the number as it is displayed on
`/contact/`. Record the exact displayed text of the phone number on that
page for them. Same rule as C2: Preview first, tell Scott, publish only
after the server session has checked the security headers.

### C4. The second Ads account

Once A4 shows which account is live, Scott decides whether to unlink the
other from GA4. Do not unlink before then.

### C5. The dead container `GTM-M3MV9VG`

If A5 shows it is not in any account this login can see, Scott asks Pup
Digital whether it is theirs. The removal itself is a website change (Part
D).

## Part D — server-side session (not for the MacBook session)

- Confirm the Search Console TXT record resolves, then tick it off in
  `docs/runbook-cutover.md` and `docs/2026-09-24-cutover-record.md`.
- Remove the `GTM-M3MV9VG` snippets from the pages once C5 is answered.
- Run `replica/console-check.mjs` against the Preview build for C2 and C3 and
  extend `deploy/security-headers.replica.conf` if a Google host is blocked.
- Decide whether the dev site should stop loading the Google tag. GA4 cannot
  filter by hostname, so dev visits are counted in the property today.
- `robots.txt` names `sitemap_index.xml`, which redirects to
  `sitemap-index.xml`. Point it at the final address.
- Help Scott reply to Carrie once B0 is done.

## Findings template

Copy this into `google-tracking-findings.md` and fill it in.

```markdown
# Google tracking findings — <date>

Signed-in Google account used: <email>

## A1 Key events
| Event name | On? | Daily count before 24 Sep | Daily count after 24 Sep |
All events, last 28 days: <name: count, ...>

## A2 Conversions section
<what is listed; warning text>

## A3 GA4 settings
- Data retention:
- Google signals / user-provided data:
- Data filters:
- Attribution model and lookback:
- Enhanced measurement toggles:
- Unwanted referrals / internal traffic / domains:
- Search Console link:
- Change history summary:

## A4 Ads accounts
| Account | Opens? Access level | Enabled campaigns / last spend | Cost this year in GA4 |
Users and managers per account:
Conversion actions per account (name, source, Primary/Secondary, status, 30-day count, label):
AW-880243114 belongs to:

## A5 Tag Manager
- "PD* Thankyou Page" tag:
- "PD* Thankyou Page" trigger:
- Container quality issues:
- Tags / triggers / variables:
- Versions:
- Users (account, container):
- Accounts and containers visible; GTM-M3MV9VG present?:

## A6 Search Console
| Property | Verified? Method | Users |

## Part B changes made
| Step | Old value | New value | Time |
TXT record value added (B5):

## Anything that did not match the instructions
```
