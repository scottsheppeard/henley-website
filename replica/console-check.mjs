#!/usr/bin/env node
/**
 * console-check.mjs — what the browser complains about on each page.
 *
 * Loads every manifest page on one origin at phone and desktop width and
 * collects: Content-Security-Policy violations (via the securitypolicyviolation
 * event, which the console does not always show), requests that failed or
 * came back 4xx/5xx, and console errors. A CSP directive missing a host fails
 * silently for the visitor — a font quietly falls back — so this is the gate
 * for security-headers.replica.conf, not a nicety.
 *
 *   scripts/with-node.sh node replica/console-check.mjs http://127.0.0.1:8090
 *   scripts/with-node.sh node replica/console-check.mjs https://dev.thehenley.com.au
 *
 * Exits 1 on any finding.
 */
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const base = process.argv[2];
if (!base) { console.error('usage: console-check.mjs <origin>'); process.exit(2); }

const manifest = JSON.parse(readFileSync('source/migration-manifest.json', 'utf8'));
const paths = [...manifest.urls.map((u) => u.path), '/news/page/2/', '/no-such-page-console-check/'];

const browser = await chromium.launch();
let findings = 0;
for (const width of [390, 1280]) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  await context.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error(`CSP ${e.violatedDirective} blocked ${e.blockedURI}`);
    });
  });
  for (const path of paths) {
    const page = await context.newPage();
    const problems = [];
    page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
    page.on('requestfailed', (r) => problems.push(`failed: ${r.url()} (${r.failure()?.errorText})`));
    page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('/no-such-page-console-check/')) problems.push(`${r.status()}: ${r.url()}`); });
    try {
      await page.goto(base + path, { waitUntil: 'networkidle', timeout: 60000 });
      const height = await page.evaluate(() => document.body.scrollHeight);
      for (let y = 0; y < height; y += 600) { await page.evaluate((y) => window.scrollTo(0, y), y); await page.waitForTimeout(100); }
      await page.waitForLoadState('networkidle');
    } catch (error) {
      problems.push(`navigation: ${error.message}`);
    }
    await page.close();
    const unique = [...new Set(problems)];
    console.log(`${unique.length ? 'FAIL' : 'ok  '} ${String(width).padStart(4)}  ${path}`);
    for (const p of unique) console.log(`         ${p}`);
    findings += unique.length;
  }
  await context.close();
}
await browser.close();
console.log(`\n${findings} finding(s).`);
process.exit(findings ? 1 : 0);
