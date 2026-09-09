# Village Comparison Document — what the site must do

Checked 2026-09-10 against the Act as in force at 28 April 2026 and the
department's operator instructions. Copies of both are in `docs/reference/`
so the wording this page relies on cannot drift away from it.

## The obligation

The Village Comparison Document (VCD, approved Form 3) is a statutory
disclosure under the *Retirement Villages Act 1999* (Qld), section 74. It
covers the **retirement village scheme** — the apartments and the services
around them. The private aged care household is regulated separately under
Commonwealth aged care law and is not what section 74 is about, although the
same web page may market both.

Section 74(6), quoted from the reprint:

> The scheme operator for a retirement village scheme must—
> (a) publish the village comparison document on the scheme's website so the
> document, or a link to the document, **appears prominently on each page of
> the website that contains, or has a link to, marketing material for the
> scheme**; and
> (b) ensure any promotional material for the scheme that is given to a
> person, other than as part of a general distribution of the material in a
> mail-out or other way, is accompanied by a copy of the village comparison
> document for the scheme; and
> (c) give a copy of the village comparison document for the scheme to a
> prospective resident within 7 days of receiving a request from the
> prospective resident.
>
> Maximum penalty— (a) for paragraphs (a) and (b)—50 penalty units; or
> (b) for paragraph (c)—120 penalty units.

Section 74(4)–(5): on becoming aware of a material change the operator must
amend the document immediately (50 penalty units), and within 28 days give
the chief executive written notice plus a copy (540 penalty units).

The department's instructions add (page 1 and page 6): publish it "so the
document, or a link to the document, appears prominently on each page of the
website that contains, or has a link to, marketing material", "ensure that the
scheme website contains the latest Village Comparison Document", and expect it
to need updating "at least annually" because several items report the last
financial year.

## What that means for thehenley.com.au

**Not home-page-only, and not aged-care-pages-only.** The test is *each page
that contains or links to marketing material for the scheme*. Every page of
this site carries the header and footer, which link to the apartment-living
pages, so every page meets that description. The current WordPress site links
the VCD from the home page alone, which is narrower than the section requires.

**A footer link on every page satisfies the words**, provided it is prominent
rather than buried among legal links. Recommended:

- A "Village Comparison Document" link in the site footer on every page, in
  the same visual weight as the navigation columns, not the small-print row.
- The same link in the body of `/luxury-retirement-living/` and
  `/supported-living/`, next to the fees question, where a prospective
  resident actually wants it.
- The link target is the stable alias `/documents/village-comparison-document.pdf`
  (see `source/migration-manifest.json`), which always points at the current
  revision and is served `Cache-Control: no-cache`, so an amended document
  reaches visitors immediately. The dated file keeps its
  `/wp-content/uploads/2026/08/Henley-Form-3-VCD-1-July-2026.pdf` path.
- Link text should say what it is. "Village Comparison Document (Form 3)"
  rather than "Compare us".

**Currency.** The document on the live site is dated 1 July 2026 and uses the
approved form version V10 (June 2025), the same version other Queensland
operators are publishing in 2026. Nine earlier revisions exist in the
WordPress uploads back to January 2023; they stay reachable at their dated
paths but nothing should link to them.

**Ownership.** Amending the VCD, notifying the chief executive and the annual
refresh are the operator's obligations, not the website's. The website's job
is to make the current one impossible to miss and easy to replace: replacing
the file behind the alias is a content change, not a deploy.

## Sources

Retrieved 2026-09-10.

- *Retirement Villages Act 1999* (Qld), s 74 — Queensland legislation site,
  reprint current at 28 April 2026:
  <https://www.legislation.qld.gov.au/view/html/inforce/current/act-1999-071#sec.74>
  (PDF of the whole reprint:
  <https://www.legislation.qld.gov.au/view/pdf/inforce/current/act-1999-071>;
  saved as `docs/reference/retirement-villages-act-1999-qld-2026-04-28.pdf`,
  CC BY 4.0, © State of Queensland).
- *Instructions and notes for village operators for completing Form 3 and
  Form 4*, V2 December 2022, Queensland Government:
  <https://www.qld.gov.au/__data/assets/pdf_file/0025/114496/RetirementVillagesForm3Form4Instructions.pdf>
  (saved as `docs/reference/qld-retirement-villages-form3-form4-instructions.pdf`).
- Approved Form 3 template (Word) and the operator forms index, Business
  Queensland:
  <https://www.housing.qld.gov.au/__data/assets/word_doc/0016/4903/retirementvillagesform3.docx>
  and
  <https://www.business.qld.gov.au/industries/housing-accommodation/retirement-village-operators/operating-retirement-village/forms>.
  (The .docx download refused a non-browser client, so it is linked, not saved.)
- Business Queensland, *Documents and contracts for retirement village
  operations* (7-day request rule, keeping the document up to date):
  <https://www.business.qld.gov.au/industries/service-industries-professionals/housing-accommodation/operating-retirement-village/documents-contracts>

Not covered here: the Schedule of Fees for the aged care household and any
publication duty under the Commonwealth *Aged Care Act 2024*. That is a
separate question and has not been checked.
