# Website brief

Draft, 2026-09-10. **Needs the GM's and the sales team's confirmation** — the
sections marked *decision* and every claim marked *evidence needed* are theirs,
not ours. Everything else is drawn from the existing site's copy, the brand
style guide and the enquiry pipeline.

This is the document the design sample is reviewed against. If a page cannot be
justified from what is written here, it does not get built.

## The objective

The GM's ask, verbatim:

> scope the project for the rebuild so that the language, branding and UI is
> assisting lead generation and reflecting our market position.

Which the [review](2026-09-09-rebuild-review.md) expands to: help prospective
residents and their families understand the lifestyle, accommodation and care
options, recognise what makes The Henley distinctive, and confidently arrange a
visit or make an enquiry — applying the current brand across language,
photography and interaction design, preserving useful functionality and search
visibility, and scoping enquiry integration to new submissions only.

## Who the site is for

| Audience | What they arrive wanting | What they need to leave with |
|---|---|---|
| **A prospective resident, roughly 70+**, considering downsizing | Whether this is a place they would enjoy living, and what it costs | A clear picture of daily life, an honest sense of price, and a booked visit |
| **An adult child researching for a parent**, often remotely and often urgently | Whether the care is good and whether the parent would be safe and happy | Care specifics, evidence rather than adjectives, and a phone number they can call now |
| **An existing resident or family member** | Reception, maintenance, a document | The shortest possible path to a phone number, the maintenance form, or a PDF |

The third group is not a lead, and the site should not treat them as one. They
are a large share of real traffic and they need a fast exit, not a funnel.

## The two paths

Apartment living and private aged care are different decisions, made by
different people, on different timescales. The site carries both from the home
page, each with its own photography, practical detail and enquiry route.

*Decision (GM):* whether the two get **equal prominence**, or one leads.
Default until told otherwise: equal. The existing site's content supports both,
and enquiry volume is not currently split finely enough to argue either way.

## What makes The Henley distinctive

Four claims, drawn from the current copy and the style guide. Each has to be
either evidenced or dropped — the review's point is that a rebuilt site must
substantiate its differentiators, not restate them louder.

1. **On the Broadwater, in the middle of Southport.** Beaches, parklands,
   transport, shopping and hospitals are genuinely walkable.
   *Evidence held* — the address is 70 Marine Parade and the proximity is
   verifiable. The current site asserts this with a static map image; a rebuilt
   page should show it rather than claim it.

2. **Care that scales without moving house.** Independent apartments, support
   in your own apartment in ten-minute increments, and a private aged care
   household on the same site.
   *Evidence held* for the structure of the offer. *Evidence needed* for how
   the transition actually works in practice, which is the question an adult
   child will ask first.

3. **A twelve-suite aged care household, single floor, registered nurse on
   site 24 hours, high staff-to-resident ratio.**
   *Evidence needed* — "high staff-to-resident ratio" is not a claim, it is an
   adjective. It needs the actual ratio, confirmed against current rostering
   and safe to publish, or it should be replaced with something concrete. The
   24-hour RN cover and the twelve suites need the same confirmation.

4. **Resort amenity as standard**, not as an upgrade: bistro, pool, gym, Sky
   Deck bowling green, hair and beauty room, and a monthly events calendar.
   *Evidence held* — all of it is on site and photographable. Current brand
   photography exists for some; the rest needs a shoot or honest reuse.

*Decision (GM/sales):* which of these lead, and whether anything is missing
that the sales team actually hears prospects respond to.

## What we ask visitors to do

One label set, used everywhere. The current site uses four labels for the same
action — "Enquire Today", "Contact Us", "Book a Tour", "Find out more" — all
pointing at `/contact/`, which teaches visitors nothing and makes the analytics
unreadable.

- **Primary: "Book a visit."** Seeing the place is what converts; the sales
  team's job is the tour, not the form.
- **Secondary: "Call 07 5591 2111."** A tel: link, visible on every page. Adult
  children ring; older visitors often prefer to. Google Ads already tracks
  `tel:` clicks as a conversion, so this is also a measured action.
- The enquiry form carries the page's context, so an enquiry from
  `/private-aged-care/` arrives knowing that. No qualification questionnaire.

*Confirm:* **07 5591 2111** is the number on every page of the live site; the
brand kit's email signature says 07 5557 0000. The site number is used here
until someone says otherwise.

## Statutory content

The Village Comparison Document (Form 3) must be linked prominently from
**every page** that carries or links to marketing for the apartments, which on
this site is every page. A footer link on every page plus an in-body link on
the apartment pages is the plan; the current site's home-page-only link is
narrower than the Act requires. Detail and sources:
[village-comparison-document.md](village-comparison-document.md).

## What counts as a useful lead

An enquiry the classifier calls `prospective_resident` with contact details
good enough to follow up — which is what becomes a Salesforce Lead today.
Roughly a handful a week. Existing-resident and other legitimate enquiries are
useful too, but they are reception's, not sales', and are routed accordingly.

Measure: qualified enquiries and visits arranged, supported by phone and email
clicks and form completions, reviewed as a trend over months. At this volume,
conversion-rate targets and A/B testing would be measuring noise.

## Page matrix

URL disposition comes from `source/migration-manifest.json`; every path below
is preserved unless the row says otherwise. **Keep** = copy stands, restyled.
**Rewrite** = same URL and search intent, new words. **Archive** = keep the URL
resolving, but the content needs a decision.

### Pages

| URL | Disposition | Note |
|---|---|---|
| `/` | Rewrite | Tagline plus a factual descriptor — a tagline alone does not explain retirement living. The 25-question FAQ moves off the hero into a "Questions" section lower down. |
| `/luxury-retirement-living/` | Rewrite | The representative service page built for the design sample. Keeps its slug and H1 keyword for search continuity. |
| `/private-aged-care/` | Rewrite | The other path's landing page. Its 8-question FAQ stays; the funding paragraph must be corrected (see below). |
| `/supported-living/` | Rewrite | Edited July 2026, so the copy is current; restyle and tighten. |
| `/location/` | Rewrite | Show the location properly rather than asserting it. |
| `/the-henley-health-club/`, `/dining/` | Rewrite | Short amenity pages; candidates to fold into the apartment-living path if the GM prefers fewer, stronger pages. *Decision.* |
| `/news/`, `/news/page/2/` | Keep | Both are live and indexed. Keep page 2 real or redirect it deliberately. |
| `/contact/` | Rewrite | Details, the enquiry form, and a fast exit for existing residents. |
| `/thank-you/` | Keep | URL retained: analytics and the Ads setup depend on it. |
| `/privacy-policy/` | Rewrite | Must be checked against the actual data flow — Salesforce, Microsoft, the AI classifier, analytics — not declared accurate because it mentions a form. |
| `/disclaimer/` | Keep | Copy verbatim. |

### Posts

| Group | Disposition | Note |
|---|---|---|
| Nine evergreen articles (2023) | Keep, light edit | Australian spelling, brand vocabulary, honest dates. |
| `making-the-most-of-your-homecare-package` | **Rewrite or archive** | It describes the Home Care Packages Program as current. Support at Home replaced HCP on 1 November 2025. Republishing it as current guidance would be wrong, and it is one of the pages an adult child is most likely to land on. *Decision needed before launch.* |
| Five 2023 resident-life posts | Keep with honest dates | *Decision (GM):* keep, refresh or retire. They date the site, but they are the only real evidence of resident life it has. |

## Claims held for confirmation

Nothing below ships until someone with authority signs it off:

- Weekly fee figures and the "Retirement Villages Act" wording in the home FAQ.
- The staff-to-resident ratio, 24-hour RN cover, and twelve-suite count.
- "Highest benchmarks in Australia" — an unsupported superlative as written.
- The testimonials ("Phil & Jill"), which need current permission to publish.
- Home Care Package funding language, per the Support at Home change above.
- Stock photography licences (`iStock`, `AdobeStock`, `shutterstock`) and
  resident photo permissions. Renovation renders must be labelled as renders.

## Questions the design sample must answer

Put in front of Scott, then the GM and Giselle, with the home page, one service
page and the enquiry journey at 360px and desktop:

1. Can a visitor tell what The Henley is, and where, within one screen?
2. Can each of the three audiences find their path without reading everything?
3. Is it obvious what to do next, and does it feel like a small ask?
4. Does the language sound like The Henley, or like a brochure?
5. Can an 80-year-old on a phone read it, tap it, and zoom it?
