/**
 * build-nginx-redirects.ts — turn redirects.json into nginx configuration.
 *
 * There are 30 redirects and they are the whole of the site's search
 * continuity: two WordPress Redirection rules with thousands of recorded hits
 * between them, three sitemap paths, and 25 `/?p=<id>` shortlinks that the old
 * site advertised in every page's <head>. Hand-maintaining that list in two
 * places — the manifest and an nginx file — guarantees they drift, and the way
 * you find out is a 404 in Search Console months later.
 *
 * So the manifest is the source and this generates the server config. Run it
 * whenever the manifest changes; the output is committed so a deploy needs
 * neither Node nor this script.
 *
 * Run: npm run redirects
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REDIRECTS = resolve(REPO_ROOT, 'src/content/redirects.json');
// Two files, because nginx puts them in different contexts: `map` is only
// valid inside `http`, `location` only inside `server`. One combined file
// would fail to load, and it would fail at reload time on the deployed host
// rather than here.
const MAP_OUTPUT = resolve(REPO_ROOT, 'deploy/redirects-map.conf');
const OUTPUT = resolve(REPO_ROOT, 'deploy/redirects.conf');

interface Redirect {
  from: string;
  to: string;
  status: number;
  pattern?: boolean;
  reason: string;
}

const { redirects } = JSON.parse(readFileSync(REDIRECTS, 'utf8')) as { redirects: Redirect[] };

const shortlinks = redirects.filter((r) => r.from.startsWith('/?p='));
const paths = redirects.filter((r) => !r.from.startsWith('/?p=') && !r.pattern);
const patterns = redirects.filter((r) => r.pattern);

const BANNER = [
  '# GENERATED FILE — DO NOT EDIT.',
  '#',
  '# Written by scripts/build-nginx-redirects.ts from src/content/redirects.json,',
  '# which is itself generated from source/migration-manifest.json. Change the',
  '# manifest and regenerate; editing here is a change that will be overwritten',
  '# and, worse, will disagree with what scripts/check-urls.sh asserts.',
  '#',
];

// ── http context ───────────────────────────────────────────────────────────
const mapLines: string[] = [
  ...BANNER,
  '# Included from the http block in deploy/nginx.conf.',
  '',
  '# The old site advertised /?p=<id> in every page <head>, so these are indexed',
  '# and bookmarked. A query string cannot be matched by `location`, so the id is',
  '# mapped to a path here and redirected in the server block, but only when the',
  '# map produced one — an unknown id must fall through to the 404, not to /.',
  'map $arg_p $shortlink_target {',
  '    default "";',
];

for (const { from, to } of shortlinks) {
  mapLines.push(`    ${from.replace('/?p=', '').padEnd(6)} ${to};`);
}
mapLines.push('}');

writeFileSync(MAP_OUTPUT, `${mapLines.join('\n')}\n`);

// ── server context ─────────────────────────────────────────────────────────
const lines: string[] = [
  ...BANNER,
  '# Included from the server block in deploy/nginx.conf.',
  '',
  '# ── WordPress shortlinks ──────────────────────────────────────────────────',
  '#',
  '# Paired with the map in redirects-map.conf. Only fires when that map matched.',
  'if ($shortlink_target != "") {',
  '    return 301 $shortlink_target;',
  '}',
  '',
  '# ── Named redirects ───────────────────────────────────────────────────────',
];

for (const { from, to, status, reason } of paths) {
  lines.push(`# ${reason}`, `location = ${from} {`, `    return ${status} ${to};`, '}', '');
}

lines.push('# ── Pattern redirects ─────────────────────────────────────────────────────');

for (const { from, to, status, reason } of patterns) {
  // /latest-articles/(.*) -> /$1
  const prefix = from.replace(/\(\.\*\)$/, '');
  const target = to.replace('$1', '$1');
  lines.push(
    `# ${reason}`,
    `location ^~ ${prefix} {`,
    `    rewrite ^${prefix}(.*)$ ${target} permanent;`,
    '}',
    '',
  );
  void status;
}

writeFileSync(OUTPUT, `${lines.join('\n')}\n`);
console.log(
  `redirects: wrote ${OUTPUT.replace(`${REPO_ROOT}/`, '')} and ` +
    `${MAP_OUTPUT.replace(`${REPO_ROOT}/`, '')} ` +
    `(${shortlinks.length} shortlinks, ${paths.length} named, ${patterns.length} pattern)`,
);
