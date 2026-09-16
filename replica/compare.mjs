#!/usr/bin/env node
/**
 * compare.mjs — is the candidate indistinguishable from the live site?
 *
 * Screenshots every page in the migration manifest on two origins at two
 * widths, diffs the pixels, and reports the share that differ. Expected
 * differences are dynamic: the lazy-load placeholders mid-fade, the year in
 * the footer once it rolls, and the contact form (four fields, not seven).
 * Everything else is a defect until explained.
 *
 *   scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au https://dev.thehenley.com.au
 *   scripts/with-node.sh node replica/compare.mjs https://thehenley.com.au http://127.0.0.1:8090 --threshold 0.5
 *
 * Writes replica/screenshots/<slug>-<width>-{live,candidate,diff}.png (gitignored)
 * and prints a table. Exits 1 if any page exceeds the threshold.
 */
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright';
import sharp from 'sharp';

const [liveBase, candidateBase, ...rest] = process.argv.slice(2);
if (!liveBase || !candidateBase) {
  console.error('usage: compare.mjs <live-origin> <candidate-origin> [--threshold pct] [--only /path/]');
  process.exit(2);
}
const flag = (name, fallback) => { const i = rest.indexOf(name); return i >= 0 ? rest[i + 1] : fallback; };
const threshold = Number(flag('--threshold', '0.5'));
const only = flag('--only', null);

const manifest = JSON.parse(readFileSync('source/migration-manifest.json', 'utf8'));
const paths = [...manifest.urls.map((u) => u.path), '/news/page/2/'].filter((p) => !only || p === only);
const widths = [390, 1280];
mkdirSync('replica/screenshots', { recursive: true });

const slug = (p) => (p === '/' ? 'home' : p.replace(/^\/|\/$/g, '').replace(/\//g, '_'));

async function shoot(browser, base, path, width) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(base + path, { waitUntil: 'networkidle', timeout: 60000 });
  // Freeze what moves, and trigger every lazy-loaded image by walking the page.
  await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }' });
  const height = await page.evaluate(() => document.body.scrollHeight);
  for (let y = 0; y < height; y += 600) {
    await page.evaluate((y) => window.scrollTo(0, y), y);
    await page.waitForTimeout(120);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  const png = await page.screenshot({ fullPage: true });
  await context.close();
  return png;
}

async function diff(a, b) {
  const [ia, ib] = await Promise.all([a, b].map((buf) => sharp(buf).ensureAlpha().raw().toBuffer({ resolveWithObject: true })));
  const width = Math.max(ia.info.width, ib.info.width);
  const height = Math.max(ia.info.height, ib.info.height);
  const pad = (img) => sharp(img.data, { raw: { width: img.info.width, height: img.info.height, channels: 4 } }).extend({
    right: width - img.info.width, bottom: height - img.info.height, background: { r: 255, g: 0, b: 255, alpha: 1 },
  }).raw().toBuffer();
  const [pa, pb] = await Promise.all([pad(ia), pad(ib)]);
  const out = Buffer.alloc(width * height * 4);
  let differing = 0;
  for (let i = 0; i < width * height; i += 1) {
    const o = i * 4;
    const delta = Math.max(Math.abs(pa[o] - pb[o]), Math.abs(pa[o + 1] - pb[o + 1]), Math.abs(pa[o + 2] - pb[o + 2]));
    if (delta > 32) {
      differing += 1;
      out[o] = 255; out[o + 1] = 0; out[o + 2] = 0; out[o + 3] = 255;
    } else {
      const grey = Math.round(200 + pa[o] * 0.2);
      out[o] = grey; out[o + 1] = grey; out[o + 2] = grey; out[o + 3] = 255;
    }
  }
  const diffPng = await sharp(out, { raw: { width, height, channels: 4 } }).png().toBuffer();
  return { pct: (100 * differing) / (width * height), heightA: ia.info.height, heightB: ib.info.height, diffPng };
}

const browser = await chromium.launch();
const rows = [];
let failed = 0;
for (const path of paths) {
  for (const width of widths) {
    const [live, candidate] = await Promise.all([shoot(browser, liveBase, path, width), shoot(browser, candidateBase, path, width)]);
    const result = await diff(live, candidate);
    const name = `${slug(path)}-${width}`;
    writeFileSync(`replica/screenshots/${name}-live.png`, live);
    writeFileSync(`replica/screenshots/${name}-candidate.png`, candidate);
    writeFileSync(`replica/screenshots/${name}-diff.png`, result.diffPng);
    const verdict = result.pct <= threshold ? 'ok' : 'REVIEW';
    if (verdict === 'REVIEW') failed += 1;
    rows.push({ path, width, pct: result.pct.toFixed(2), heights: `${result.heightA}/${result.heightB}`, verdict });
    console.log(`${verdict.padEnd(7)} ${String(width).padStart(4)}  ${result.pct.toFixed(2).padStart(6)}%  ${result.heightA}/${result.heightB}  ${path}`);
  }
}
await browser.close();
console.log(`\n${rows.length - failed} within ${threshold}%, ${failed} to review. Screenshots in replica/screenshots/.`);
process.exit(failed ? 1 : 0);
