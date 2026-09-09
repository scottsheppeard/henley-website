/**
 * export-content.ts — turn the 2026-09-09 live capture into editable content.
 *
 * The old site's copy lives inside Elementor's markup: forty layers of nested
 * <div> per page, class names carrying the layout, and the actual words strewn
 * through it. This walks each captured page, throws away the chrome and the
 * layout, and writes what a person would call the content — headings, body
 * copy, lists, links, images — as Markdown with front-matter, one file per URL.
 *
 * What it is NOT: a converter whose output ships as-is. The review's whole
 * point is that the new site rewrites and regroups this material rather than
 * reproducing it. So every file lands with `status: needs-review`, and the
 * front-matter records where it came from and what the old page's title,
 * description and canonical were — the things that must survive rewriting for
 * search continuity, per the migration manifest.
 *
 * It is safe to rerun. Files whose front-matter has been changed to
 * `status: reviewed` are left alone, so a re-export after fixing a conversion
 * bug never overwrites edited copy.
 *
 * Run: npm run export:content [-- --force]
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as cheerio from 'cheerio';
import TurndownService from 'turndown';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MANIFEST = resolve(REPO_ROOT, 'source/migration-manifest.json');
const CAPTURE = resolve(REPO_ROOT, 'source/live-capture-2026-09-09');
const CONTENT = resolve(REPO_ROOT, 'src/content');
const ORIGIN = 'https://thehenley.com.au';

interface ManifestUrl {
  path: string;
  type: 'page' | 'post';
  lastmod: string | null;
  title: string | null;
  description: string | null;
  canonical: string | null;
  og_image: string | null;
  robots: string | null;
  shortlink_id: number | null;
  capture: string;
}

interface Manifest {
  urls: ManifestUrl[];
  shortlinks: Record<string, string>;
  redirects: { from: string; to: string; status: number; pattern?: boolean; source: string }[];
  canonicalisation: { rule: string; example: string }[];
  documents: { path: string; alias: string | null; linked_from: string[] }[];
}

/**
 * Elementor wraps the page in one element per template part. The chrome is
 * `header` and `footer`; whatever else is left — `wp-page`, `single-page`,
 * `single-post`, `archive` — is the page's own content.
 */
const CHROME = new Set(['header', 'footer']);

/** Elementor and WordPress furniture that carries no content. */
const STRIP_SELECTORS = [
  'script',
  'style',
  'noscript',
  'link',
  'meta',
  'svg',
  'form',
  '.elementor-widget-theme-site-logo',
  '.elementor-nav-menu',
  '.elementor-menu-toggle',
  '.elementor-post-navigation',
  '.elementor-share-buttons',
  '.screen-reader-text',
  '.skip-link',
  '[aria-hidden="true"]',
];

function turndown(): TurndownService {
  const service = new TurndownService({
    headingStyle: 'atx',
    bulletListMarker: '-',
    codeBlockStyle: 'fenced',
    emDelimiter: '_',
    strongDelimiter: '**',
    linkStyle: 'inlined',
  });

  // Keep image URLs absolute-from-root and drop Elementor's srcset/size noise;
  // which file each one becomes is a decision for the image pass, not here.
  service.addRule('image', {
    filter: 'img',
    replacement: (_content, node) => {
      const element = node as unknown as { getAttribute(name: string): string | null };
      const src = (element.getAttribute('src') ?? '').replace(ORIGIN, '');
      const alt = element.getAttribute('alt') ?? '';
      return src ? `\n\n![${alt}](${src})\n\n` : '';
    },
  });

  // Site-internal links become root-relative, so the migrated copy is not
  // pinned to the old origin and does not break when the domain is served
  // from the new stack.
  service.addRule('internalLink', {
    filter: (node) => node.nodeName === 'A' && (node.getAttribute('href') ?? '').startsWith(ORIGIN),
    replacement: (content, node) => {
      const href = (node as unknown as { getAttribute(n: string): string | null })
        .getAttribute('href')!
        .replace(ORIGIN, '');
      return content.trim() ? `[${content}](${href || '/'})` : '';
    },
  });

  return service;
}

/** Collapse the runs of blank lines Elementor's empty wrappers leave behind. */
function tidy(markdown: string): string {
  return (
    markdown
      .replace(/ /g, ' ')
      // Turndown escapes a leading "1." so it cannot be read as an ordered list.
      // Inside a heading it never could be, and the backslash is visible noise in
      // copy a person is about to edit: "## 1\\. Location" -> "## 1. Location".
      .replace(/^(#{1,6} .*)$/gm, (heading) => heading.replace(/(\d)\\\./g, '$1.'))
      .replace(/[ \t]+$/gm, '')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/^\s+/, '')
      .trimEnd()
  );
}

function slugFor(path: string): string {
  return path.replace(/^\/|\/$/g, '').split('/').pop() || 'home';
}

/** YAML-quote a value: single quotes, doubled inside, always quoted. */
function yaml(value: string | number | null): string {
  if (value === null) return 'null';
  if (typeof value === 'number') return String(value);
  return `'${value.replace(/'/g, "''")}'`;
}

function extractBody(html: string): { markdown: string; images: string[]; headings: string[] } {
  const $ = cheerio.load(html);

  $('[data-elementor-type]').each((_, element) => {
    const kind = $(element).attr('data-elementor-type') ?? '';
    if (CHROME.has(kind)) $(element).remove();
  });

  const content = $('[data-elementor-type]').first();
  if (content.length === 0) throw new Error('no Elementor content region found');

  for (const selector of STRIP_SELECTORS) content.find(selector).remove();

  const images = content
    .find('img')
    .map((_, img) => ($(img).attr('src') ?? '').replace(ORIGIN, ''))
    .get()
    .filter(Boolean);

  const headings = content
    .find('h1, h2, h3')
    .map((_, h) => `${h.tagName.toUpperCase()} ${$(h).text().trim()}`)
    .get()
    .filter((h) => h.length > 3);

  return {
    markdown: tidy(turndown().turndown(content.html() ?? '')),
    images: [...new Set(images)],
    headings,
  };
}

function frontMatter(entry: ManifestUrl, body: { images: string[]; headings: string[] }): string {
  const lines = [
    '---',
    '# Migrated from the 2026-09-09 WordPress capture by scripts/export-content.ts.',
    '# Rewrite the copy freely — but keep `path`, and carry the search intent of',
    '# `legacy.title` and `legacy.description` into whatever replaces them. Set',
    '# `status: reviewed` once a person has been through this file; a re-export',
    '# then leaves it alone.',
    `status: 'needs-review'`,
    `path: ${yaml(entry.path)}`,
    `type: ${yaml(entry.type)}`,
    `title: ${yaml(entry.title?.replace(/\s*\|\s*The Henley on Broadwater\s*$/, '') ?? slugFor(entry.path))}`,
    `description: ${yaml(entry.description)}`,
  ];

  if (entry.type === 'post') lines.push(`date: ${yaml(entry.lastmod?.slice(0, 10) ?? null)}`);
  if (entry.og_image) lines.push(`ogImage: ${yaml(entry.og_image.replace(ORIGIN, ''))}`);

  lines.push(
    'legacy:',
    `  title: ${yaml(entry.title)}`,
    `  description: ${yaml(entry.description)}`,
    `  canonical: ${yaml(entry.canonical)}`,
    `  lastmod: ${yaml(entry.lastmod)}`,
    `  shortlinkId: ${entry.shortlink_id === null ? 'null' : entry.shortlink_id}`,
    `  capture: ${yaml(entry.capture)}`,
  );

  if (body.images.length) {
    lines.push('  # Images the old page used, for the image pass to re-encode or replace:');
    lines.push('  images:');
    for (const image of body.images) lines.push(`    - ${yaml(image)}`);
  }

  if (body.headings.length) {
    lines.push('  # The old page\'s heading outline, so a rewrite can see what it is replacing:');
    lines.push('  outline:');
    for (const heading of body.headings) lines.push(`    - ${yaml(heading)}`);
  }

  lines.push('---', '');
  return lines.join('\n');
}

function isReviewed(file: string): boolean {
  return /^status:\s*'?reviewed'?\s*$/m.test(readFileSync(file, 'utf8'));
}

function writeRedirects(manifest: Manifest): number {
  const shortlinks = Object.entries(manifest.shortlinks)
    .map(([id, path]) => ({ from: `/?p=${id}`, to: path, status: 301, reason: 'WordPress shortlink' }))
    .sort((a, b) => Number(a.from.slice(4)) - Number(b.from.slice(4)));

  const named = manifest.redirects.map((r) => ({
    from: r.from,
    to: r.to,
    status: r.status,
    ...(r.pattern ? { pattern: true } : {}),
    reason: r.source,
  }));

  const output = {
    $comment:
      'Generated by scripts/export-content.ts from source/migration-manifest.json. ' +
      'Every address the old site answered that the new one does not serve directly. ' +
      'nginx implements these; scripts/check-urls.sh asserts them against a deployment.',
    canonicalisation: manifest.canonicalisation.map((c) => c.rule),
    redirects: [...named, ...shortlinks],
  };

  writeFileSync(resolve(CONTENT, 'redirects.json'), `${JSON.stringify(output, null, 2)}\n`);
  return output.redirects.length;
}

function main(): void {
  const force = process.argv.includes('--force');
  const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8')) as Manifest;

  let written = 0;
  let kept = 0;

  for (const entry of manifest.urls) {
    const directory = resolve(CONTENT, entry.type === 'post' ? 'posts' : 'pages');
    const file = resolve(directory, `${slugFor(entry.path)}.md`);

    if (!force && existsSync(file) && isReviewed(file)) {
      kept += 1;
      continue;
    }

    const html = readFileSync(resolve(REPO_ROOT, entry.capture), 'utf8');
    let body;
    try {
      body = extractBody(html);
    } catch (error) {
      throw new Error(`${entry.path}: ${(error as Error).message}`);
    }

    mkdirSync(directory, { recursive: true });
    writeFileSync(file, `${frontMatter(entry, body)}${body.markdown}\n`);
    written += 1;
  }

  const redirects = writeRedirects(manifest);

  const pages = readdirSync(resolve(CONTENT, 'pages')).length;
  const posts = readdirSync(resolve(CONTENT, 'posts')).length;
  console.log(
    `content: ${written} file(s) written, ${kept} reviewed file(s) left alone ` +
      `(${pages} pages, ${posts} posts); ${redirects} redirects`,
  );
}

main();
