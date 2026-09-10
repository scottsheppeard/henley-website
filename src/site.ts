/**
 * Facts about The Henley that appear in more than one place.
 *
 * They live here so the phone number, address and navigation labels cannot
 * drift between the header, the footer, the contact page and the structured
 * data — which is exactly what happened on the old site, where four different
 * labels ("Enquire Today", "Contact Us", "Book a Tour", "Find out more") all
 * pointed at the same page.
 */

/** The number published on every page of the live site. */
export const PHONE = '07 5591 2111';
export const PHONE_HREF = 'tel:+61755912111';

export const EMAIL = 'info@thehenley.com.au';

export const ADDRESS = {
  street: '70 Marine Parade',
  suburb: 'Southport',
  state: 'QLD',
  postcode: '4215',
  country: 'AU',
} as const;

export const SOCIAL = [
  { label: 'Facebook', href: 'https://www.facebook.com/thehenleyonbroadwater/' },
  { label: 'Instagram', href: 'https://www.instagram.com/the_henley_on_broadwater/' },
] as const;

/**
 * Main navigation.
 *
 * Three entries, not the old site's nine. Two of them are the two ways to live
 * here — the decision a visitor is actually making — and the third is the
 * action. Everything else (dining, the health club, the location, news, the
 * legal pages) is reachable from the footer and from inside the section it
 * belongs to, where it means something.
 */
export const NAV = [
  { href: '/luxury-retirement-living/', label: 'Apartment living' },
  { href: '/private-aged-care/', label: 'Private aged care' },
  // `action` marks the call to action rather than a place. The header drops it
  // on a narrow screen: it is the button in every hero, the button at the foot
  // of every service page and a footer link, so keeping a third copy in a
  // sticky header costs a row of a small screen on every page and adds nothing.
  { href: '/contact/', label: 'Book a visit', action: true },
] as const;

/**
 * The residents' maintenance form.
 *
 * A Microsoft Form the maintenance team owns, linked from the footer and from
 * the contact page. It is here once because it was here twice: both copies had
 * been replaced with the placeholder `forms.office.com/r/maintenance`, which is
 * not a Henley address and never resolved, so every existing resident who
 * followed either link got nothing.
 *
 * The value is the one the live site published, recovered from
 * source/live-capture-2026-09-09/pages/contact.html. Confirmed on 2026-09-10 to
 * still open "Maintenance Request — Request assistance from the maintenance team
 * at The Henley on Broadwater", asking unit number, the request, the labour and
 * materials acknowledgement and a name. If it is ever retired, the replacement
 * comes from the form's owner; do not invent a shortlink.
 */
export const MAINTENANCE_FORM = {
  href: 'https://forms.office.com/pages/responsepage.aspx?id=juKGyJ_MokG0gjcr_cUkcGG7XWGR5wtMgypQqRG4KFVUN1pGSExIVVI2MzlVUU9VMkNEU1RHWkZMNy4u',
  label: 'Maintenance request',
} as const;

/**
 * Statutory documents.
 *
 * The Village Comparison Document (approved Form 3) must appear, or be linked,
 * prominently on every page that carries or links to marketing for the
 * apartments — Retirement Villages Act 1999 (Qld) s 74(6)(a); see
 * docs/village-comparison-document.md. On this site that is every page, so it
 * is a footer link in the navigation columns rather than the small-print row,
 * and the apartment pages link it again where the cost question is asked.
 *
 * The alias always points at the current revision and is served no-cache; the
 * dated file keeps its WordPress-era path because it is indexed and printed.
 */
export const DOCUMENTS = {
  villageComparison: {
    href: '/documents/village-comparison-document.pdf',
    label: 'Village Comparison Document',
    format: 'PDF',
  },
} as const;

/** Everything the footer lists, grouped as a visitor would expect to find it. */
export const FOOTER_NAV = [
  {
    heading: 'Living here',
    links: [
      { href: '/luxury-retirement-living/', label: 'Apartment living' },
      { href: '/supported-living/', label: 'Support in your apartment' },
      { href: '/private-aged-care/', label: 'Private aged care' },
      {
        href: DOCUMENTS.villageComparison.href,
        label: `${DOCUMENTS.villageComparison.label} (${DOCUMENTS.villageComparison.format})`,
      },
    ],
  },
  {
    heading: 'The resort',
    links: [
      { href: '/the-henley-health-club/', label: 'Health club' },
      { href: '/dining/', label: 'Dining' },
      { href: '/location/', label: 'Location' },
      { href: '/news/', label: 'News' },
    ],
  },
  {
    heading: 'Residents',
    links: [
      {
        href: MAINTENANCE_FORM.href,
        label: MAINTENANCE_FORM.label,
        external: true,
      },
      { href: '/contact/', label: 'Contact reception' },
    ],
  },
] as const;

export const LEGAL_NAV = [
  { href: '/privacy-policy/', label: 'Privacy policy' },
  { href: '/disclaimer/', label: 'Disclaimer' },
] as const;

/**
 * The two enquiry paths.
 *
 * `interest` is the form field the page pre-ticks, so someone enquiring from a
 * service page has already answered "how can we help?" without being asked.
 * The values are the exact strings Gravity Forms stored and Salesforce keeps
 * in InterestType_c__c — they are data, not labels, and must not be reworded
 * when the visible text changes.
 */
export const PATHS = {
  apartment: { interest: 'interest_apartment', label: 'Apartment living' },
  agedCare: { interest: 'interest_aged_care', label: 'Private aged care' },
} as const;

export type InterestField = (typeof PATHS)[keyof typeof PATHS]['interest'];
