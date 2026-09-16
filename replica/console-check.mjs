#!/usr/bin/env node
/**
 * console-check.mjs — browser errors that can make the replica incomplete.
 *
 * CSP violations, same-origin failed requests/HTTP errors, page exceptions
 * and actionable console errors fail the gate. Third-party network failures
 * are listed separately: the live site's retired GTM container must not hide
 * a local regression.
 */
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const probePath = '/no-such-page-console-check/';
const resourceConsoleError = /Failed to load resource: (?:the server responded with a status of|net::)/i;
const cspConsoleError = /\bCSP\b|content security policy|violates the following content security policy/i;

export function isSameOrigin(url, base) {
  try { return new URL(url).origin === new URL(base).origin; }
  catch { return false; }
}

export function isExpectedProbe(url, base) {
  try {
    const parsed = new URL(url);
    return parsed.origin === new URL(base).origin && parsed.pathname === probePath;
  } catch { return false; }
}

export function classifyNetwork(url, base, detail, {
  expectedProbe = false, isMainDocument = false, status,
} = {}) {
  // The probe deliberately asks nginx for its 404 document.  It is the only
  // allowed failure: a failed request or a non-404 response at that path is a
  // defect and must remain visible to the gate.
  if (expectedProbe && isMainDocument && status === 404 && isExpectedProbe(url, base)) return null;
  return { severity: isSameOrigin(url, base) ? 'fatal' : 'external', detail: `${detail}: ${url}` };
}

export function classifyConsoleError(text) {
  if (cspConsoleError.test(text)) return 'fatal';
  // Request and response events retain the URL and origin, so they are
  // authoritative for these generic, URL-less Chromium messages.
  if (resourceConsoleError.test(text)) return 'network-event';
  return 'fatal';
}

export async function checkOrigin(base, { paths, widths = [390, 1280], log = console.log } = {}) {
  const manifest = JSON.parse(readFileSync('source/migration-manifest.json', 'utf8'));
  const checkPaths = paths ?? [...manifest.urls.map((u) => u.path), '/news/page/2/', probePath];
  const browser = await chromium.launch();
  let fatalFindings = 0;
  let externalWarnings = 0;
  for (const width of widths) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    await context.addInitScript(() => {
      document.addEventListener('securitypolicyviolation', (event) => {
        console.error(`CSP ${event.violatedDirective} blocked ${event.blockedURI}`);
      });
    });
    for (const path of checkPaths) {
      const page = await context.newPage();
      const fatal = new Set();
      const external = new Set();
      const expectedProbe = path === probePath;
      const recordNetwork = (url, detail, options = {}) => {
        const finding = classifyNetwork(url, base, detail, { expectedProbe, ...options });
        if (finding) (finding.severity === 'fatal' ? fatal : external).add(finding.detail);
      };
      page.on('console', (message) => {
        if (message.type() !== 'error') return;
        const detail = `console: ${message.text()}`;
        if (classifyConsoleError(message.text()) === 'fatal') fatal.add(detail);
      });
      page.on('pageerror', (error) => fatal.add(`pageerror: ${error.message}`));
      page.on('requestfailed', (request) => {
        recordNetwork(request.url(), `failed (${request.failure()?.errorText ?? 'unknown error'})`);
      });
      page.on('response', (response) => {
        if (response.status() >= 400) {
          recordNetwork(response.url(), `${response.status()}`, {
            isMainDocument: response.request().isNavigationRequest(), status: response.status(),
          });
        }
      });
      try {
        await page.goto(base + path, { waitUntil: 'networkidle', timeout: 60000 });
        const height = await page.evaluate(() => document.body.scrollHeight);
        for (let y = 0; y < height; y += 600) {
          await page.evaluate((position) => window.scrollTo(0, position), y);
          await page.waitForTimeout(100);
        }
        await page.waitForLoadState('networkidle');
      } catch (error) {
        fatal.add(`navigation: ${error.message}`);
      }
      await page.close();
      const local = [...fatal];
      const remote = [...external];
      log(`${local.length ? 'FAIL' : 'ok  '} ${String(width).padStart(4)}  ${path}${remote.length ? ` (${remote.length} external warning${remote.length === 1 ? '' : 's'})` : ''}`);
      for (const finding of local) log(`         ${finding}`);
      for (const warning of remote) log(`         external: ${warning}`);
      fatalFindings += local.length;
      externalWarnings += remote.length;
    }
    await context.close();
  }
  await browser.close();
  return { fatalFindings, externalWarnings };
}

async function main() {
  const base = process.argv[2];
  if (!base) { console.error('usage: console-check.mjs <origin>'); process.exit(2); }
  const result = await checkOrigin(base);
  console.log(`\n${result.fatalFindings} fatal finding(s); ${result.externalWarnings} external warning(s).`);
  process.exit(result.fatalFindings ? 1 : 0);
}

if (import.meta.url === new URL(process.argv[1], 'file:').href) await main();
