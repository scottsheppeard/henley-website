# Website rebuild — independent review and revised brief

Review date: 9 September 2026. Reviewed against the [original proposal](2026-09-09-rebuild-baseline-and-proposal.md), live website, running containers, WordPress configuration, Henley brand kit, henley-utils, and current Keystone/Vertex source and deployment records.

**Recommendation: retain the static-site direction, but revise the project brief before building all the pages.** The original is a useful technical inventory. It is less complete as a proposal for a website that communicates The Henley's position and generates suitable enquiries. The GM's feedback should become a primary acceptance criterion.

Scott clarified during this review that historical enquiries need no migration: Salesforce already contains the records that matter. Legitimate enquiry volume is a handful per week. The handover should therefore stay small; historical backfills, parallel processing systems and an elaborate transition are outside scope.

**What the proposal gets right**

Astro-generated HTML, TypeScript, ordinary CSS, minimal browser JavaScript and nginx are a good fit. Keep the separate form receiver, existing public URLs, document links, email-signature assets, SVG logos, responsive images and development preview. Removing WordPress/PHP and the public administration interface substantially reduces the maintenance and attack surface. The form service, proxy and third-party scripts still need ordinary maintenance; this does not eliminate every security risk.

I verified the production WordPress and MariaDB containers, document root, 12 published pages and 15 posts, Yoast, Gravity Forms, the daily henley-utils job, and the apex `/webhooks` proxy exception. Preserving that exception matters to systems beyond the website.

**1. Put the commercial brief ahead of the framework decision**

Suggested replacement opening for the proposal:

> Rebuild The Henley's website to help prospective residents and their families understand the lifestyle, accommodation and care options, recognise what makes The Henley distinctive, and confidently arrange a visit or make an enquiry. Apply the current brand consistently across language, photography and interaction design. Preserve useful existing functionality and search visibility while replacing WordPress with a small, maintainable site. Scope enquiry integration to new submissions from cutover onward.

The [brand guide](</mnt/persistent/git/branding/henley/01_Style_Guide/The Henley - Brand Style Guide.docx>) already supplies a direction: a refined, warm lifestyle resort on the Broadwater, with service, social connection and ease of living. The [design system](/mnt/persistent/git/branding/henley/DESIGN.md:400) translates that into calm, spacious layouts and conversational language. Use those as the starting point; the GM and sales team should confirm the business priorities and supporting claims.

Before producing every page, agree a short messaging brief covering priority audiences, apartment versus care enquiry priorities, three or four genuine differentiators, evidence for those claims, and the desired next action. Existing content supports separate apartment-living and private-aged-care visitor paths; their relative prominence remains a business decision. Existing residents and families still need an easy way to reach reception or the maintenance form.

Translate this into a homepage, one representative service page and the enquiry flow for early team review. Ask whether visitors can understand the offer, find their relevant path and know what happens next. This is more useful than first building every old page and then asking whether the team likes the styling.

**2. Preserve useful content and URLs, rather than freezing the old wording and navigation**

The proposal's repeated “copy verbatim” and “keep H1 keywords” instructions are too restrictive for the GM's brief. Preserve established URLs and valuable search intent, but allow clearer headings, grouped navigation, stronger introductions and useful calls to action. Nine existing navigation entries need not become nine equally prominent desktop links.

Recommended visitor experience:

- Explain the offer and location immediately, using the approved tagline with a factual descriptor. A tagline alone does not explain retirement living or the care offering.
- Provide clear paths into apartment living and private aged care, with relevant photographs, practical information and substantiated resident experiences.
- Make arranging a visit and calling the team easy, with consistent labels. Carry the service-page context into the enquiry where useful, without adding a long qualification questionnaire.
- Place fees, comparison documents and FAQs where they answer the visitor's questions. Do not let a 25-question homepage accordion dominate the initial experience.
- Preserve a short form, visible labels, accessible errors, readable body text and generous controls. Include keyboard, mobile, zoom and screen-reader checks; a Lighthouse score alone does not establish usability for older visitors.

Some supposedly evergreen content needs substantive review. The home-care-package article discusses a then-new government announcement. Support at Home replaced the Home Care Packages Program on 1 November 2025, so republishing that article as current guidance is inappropriate. Review funding terminology, fees, eligibility, care claims and testimonials, while retaining genuinely useful older resident stories with honest dates. [Current government program description](https://www.health.gov.au/our-work/support-at-home/about).

The privacy policy also should not be declared “still accurate” merely because it mentions a form. Check its wording against Salesforce, Microsoft, the AI classification provider, analytics and the selected bot protection. This is a focused review of the actual data flow, not a requirement to add an indiscriminate cookie banner. Keep enquiry responses and optional marketing permissions distinct.

**3. Google Ads tracking is a confirmed requirement**

The proposal leaves GTM contents unknown and speculates mainly about form or thank-you conversions. A read-only fetch of the currently published [GTM-PGSH3HF7 script](https://www.googletagmanager.com/gtm.js?id=GTM-PGSH3HF7) exposed these configured tags:

| Published tag | Configuration observed |
|---|---|
| Conversion Linker | Present |
| Google Ads telephone-link conversion | ID `880243114`, label `ELcdCNaJ-psZEKrj3aMD`; trigger matches `tel:` link clicks |
| Google Ads email-link conversion | ID `880243114`, label `GkCWCPi785sZEKrj3aMD`; trigger matches `mailto:` link clicks |

These are click conversions, not proof of a completed call or email. The inspected resource did not contain a form/thank-you conversion. The other embedded container, `GTM-M3MV9VG`, returned HTTP 404 during this review. That is a point-in-time observation, not proof about account ownership or historical campaign configuration.

Preserve the working Ads click tracking and existing Google tag initially. Confirm the GA4 destination, Ads conversion actions and account ownership before consolidating anything. Add an explicit successful-enquiry event after persistence; do not count a submit-button click or every revisit to `/thank-you/` as a new lead. Preserve advertising query parameters through redirects. Test using preview/debug facilities without feeding development activity into live campaign conversions.

For the GM, measure qualified enquiries and visits arranged, supported by phone/email clicks and form completion. At this volume, review trends and sales feedback over meaningful periods. A/B testing infrastructure or statistically ambitious conversion targets would be disproportionate.

**4. Keep future-enquiry delivery simple, with a deliberate destination choice**

No historical database import is needed. A small durable intake store, a scheduled processor and visible failures are sufficient. Save accepted submissions before showing success; retain failed deliveries for retry; alert the operator if processing fails. Keep sales-versus-reception routing and avoid silently discarding uncertain classifications. No message broker, new CRM interface or real-time processing requirement is justified by current volume.

The original “~40-line change” understates the details, though the implementation can still be small:

- henley-utils filters against existing integer IDs and upserts Salesforce through `WebFormID_c__c`. Starting a fresh store at ID 1 can skip or collide with existing records even without importing history. Choose a non-colliding identity scheme and reuse each submission's identity on retry. This is an implementation detail, not a migration project. [Reader](/mnt/persistent/git/henley-utils/scripts/update/update_salesforce_leads.py:134), [local identity](/mnt/persistent/git/henley-utils/scripts/modules/forms_database.py:79), [Salesforce mapping](/mnt/persistent/git/henley-utils/scripts/update/update_salesforce_leads.py:259).
- There is another WordPress lookup, `fetch_extra_fields_for_ids()`, used by catch-up processing. Account for it before retiring the WordPress database. [Catch-up path](/mnt/persistent/git/henley-utils/scripts/update/update_salesforce_leads.py:454).
- Keystone's current API is staff-authenticated and represents phone enquiries. Its Salesforce adapter sets `LeadSource='Phone'` and uses `PhoneEnquiryID_c__c`; its input accepts one interest, while the website permits both checkbox choices. It is not a ready-made website receiver. [API](/mnt/persistent/git/keystone/tenants/henley/api/app/routes/enquiries.py:29), [Salesforce adapter](/mnt/persistent/git/keystone/tenants/henley/api/app/enquiries/salesforce.py:132).
- Keystone's improved enquiry delivery source has landed, but the project records separate production rollout gates. The webhook-ingress document is still a deferred design. Do not equate source availability with a deployed public capability. [Current state](/mnt/persistent/git/keystone/docs/current-state.md:130), [ingress design](/mnt/persistent/git/keystone/docs/webhook-ingress-design.md:1).

My implementation default for the smallest first release is to reuse the existing classifier and Salesforce/reception processor behind the new receiver. If consolidating into Keystone now is a business priority, use its trusted processing side with an explicit website mapping and preserve reception routing. Pick one delivery owner for launch; do not make two successive backend migrations a compulsory part of the website project.

The public receiver should have no Salesforce or corporate-database credentials. CAPTCHA verification does require a provider secret and outbound verification access, so replace the blanket “no outbound credentials” claim with that narrower boundary. Public-browser capability URLs cannot be treated as secret authentication. Trust forwarded IP headers only from the configured proxy, and apply modest request-size and rate limits.

Also resolve the no-JavaScript promise: reCAPTCHA v3 and Turnstile require client-side JavaScript. A plain POST cannot silently bypass the bot check. Provide a clear alternative contact method if verification cannot run. Google specifies server verification of the response and expected action, with tokens generated at submission because they expire quickly. [reCAPTCHA documentation](https://developers.google.com/recaptcha/docs/v3).

**5. Fill the small but real gaps in URL and asset continuity**

- `/news/page/2/` is live, returns 200 and has its own canonical. It is absent from the proposal's supposedly complete URL inventory. Preserve it, or deliberately redirect it if the new index includes all posts. [Current second news page](https://thehenley.com.au/news/page/2/).
- WordPress shortlinks work today: `/?p=555` resolves to its article, and public page HTML advertises these links. Generate the small ID-to-slug redirect map rather than declaring them unnecessary without evidence.
- The live `www` contact URL redirects to the apex. Reproduce canonical host, HTTPS and trailing-slash behavior, alongside the named legacy redirects. Inventory actual article slugs, relevant archive/feed URLs, current titles/descriptions and document links in a compact migration manifest. [Google migration guidance](https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes).
- Keep legacy email-signature image URLs for as long as sent emails depend on them; 12 months is not a useful expiry date. Serve an audited public-asset copy, not a mount of the whole WordPress root. Keep source images and provenance separately from the optimized website output.
- Use current approved photographs where possible. Confirm stock and resident-photo permissions; label renovation renders accurately. Existing imagery can support continuity without forcing generic stock photographs into the new brand.
- Give the latest-document aliases short/revalidating cache behavior, while retaining immutable dated PDFs. Otherwise visitors can keep seeing obsolete fees despite the alias being updated.
- Preserve Search Console ownership before removing Site Kit. OAuth access is distinct from the site's verification method; identify and retain the token, or establish DNS ownership first. [Google ownership verification](https://support.google.com/webmasters/answer/9008080).

**6. Correct the technology and brand assumptions**

| Proposal statement | Recommended correction |
|---|---|
| Start a new project on Astro 5 | Astro 7 was released on 22 June 2026. Select and pin a current stable release and compatible supported Node build image, with a lockfile and reproducible build. Static rendering remains the recommendation. [Official release](https://astro.build/blog/astro-7/). |
| Astro automatically supplies all image/sitemap/RSS behavior | These require chosen components, integrations and configuration. Explicitly configure them; plain files copied into `public/` are not automatically optimized. [Astro images](https://docs.astro.build/en/guides/images/). |
| The provided TTFs establish that no web licence exists | Their presence does not prove The Henley's contractual rights. Record web-use rights as unverified until entitlement is checked. Adobe offers Avenir Next for web projects; self-hosting requires appropriate rights. [Adobe family and licensing options](https://fonts.adobe.com/fonts/avenir-next). |
| Default to Nunito Sans and create an H monogram | These change brand decisions. Preview with the approved fallback stack while resolving fonts; treat a new favicon design as a small brand decision, not an automatic addition to the canonical kit. |
| FAQPage schema as an SEO launch feature | Keep useful, accessible FAQs. Google retired FAQ rich results in May 2026, so this markup is not a Google rich-result opportunity or a launch priority. [Google Search updates](https://developers.google.com/search/updates). |
| CSP allows self, analytics and fonts | Include the actual Ads and CAPTCHA requirements, then verify the form and tags under the policy. Avoid a nominal security header that breaks conversions. [Google CSP guide](https://developers.google.com/tag-platform/security/guides/csp). |
| 55 submissions were unrecoverably lost | The DB shows a submission gap, but access-log POST counts do not establish valid enquiries, unique people or unrecoverability. Describe the gap as observed and the business impact as unknown. |

The active-plugin list includes the reCAPTCHA add-on but does not list Zero Spam; the fetched contact HTML did not expose a reCAPTCHA script. Honeypot protection is enabled in the form definition. Distinguish installed/configured protection from verified runtime behavior rather than assuming all listed protections are active.

One infrastructure detail also deserves accurate wording: Docker publishes MariaDB port 6306 on all host interfaces. That is broader than the reader's loopback connection; it does not by itself establish internet exposure because firewall/security-group controls were not inspected. Retiring the database removes that dependency. Do not change shared infrastructure as an incidental part of the visual rebuild.

**7. A proportionate delivery scope and order**

| Stage | Deliverable and acceptance |
|---|---|
| Brief and content decisions | GM/sales alignment on audience priorities, positioning, claims, CTAs and what constitutes a useful lead. Mark each existing page keep/rewrite/archive; preserve its URL or map it explicitly. |
| Design sample | Homepage, one service page and enquiry journey at desktop and mobile widths, with real copy and representative approved imagery. Review before duplicating the design across all pages. |
| Website build | Astro static site, brand styling, migrated/revised content, optimized media, documents, redirects, SEO and the verified tracking configuration. |
| Enquiry integration | New submissions only; one delivery destination, sales/reception routing, stable identities, saved failures and a basic alert. Use synthetic contacts in an isolated preview environment. |
| Preview and acceptance | Private team preview with noindex; development forms and analytics isolated from live delivery. Check navigation, documents, accessibility, phone/email clicks and form success/error behavior. |
| Release | Save rollback material, switch NPM while preserving `/webhooks`, check the live site and controlled enquiry routing, then stop the old WordPress services. Check any last pending old-form items once; no historical reconciliation exercise. Keep a documented route back if the release fails. |

Name who maintains copy, photographs and annually revised fee documents after launch. A git-based editing workflow can be entirely appropriate if Scott or an agent will make those updates; replacing WordPress also removes its staff editor, so state that operational choice explicitly. There is no need to introduce a CMS unless the actual editing workflow demands one.

Treat the lifestyle feed as an optional follow-up. Keystone already has a deliberately public signage feed, but its activities response covers the next 48 hours and is not a complete public lifestyle calendar. Any later website feature should consume a curated public projection and tolerate backend downtime; it should not expose staff APIs or hold corporate credentials in the browser. [Current feed contract](/mnt/persistent/git/keystone/tenants/henley/api/app/routes/signage.py:1).

**Review limits:** No form submissions, Salesforce writes, emails, deployments or infrastructure changes were made. Google account settings, campaign delivery, Search Console ownership, font entitlements and image permissions remain unverified. Public HTML, published tag configuration and read-only database/source checks establish the findings above; they do not establish those account-level facts.
