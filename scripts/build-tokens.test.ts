/**
 * Tests for the brand token generator.
 *
 * Run: npm test   (or: node --test scripts/)
 * Update the snapshot after an intended change: npm run test:update
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { generate } from './build-tokens.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = resolve(HERE, 'fixtures/design-fixture.md');
const SNAPSHOT = resolve(HERE, 'fixtures/design-fixture.expected.css');
const BRAND_KIT = process.env.HENLEY_DESIGN_MD
  ?? '/mnt/persistent/git/branding/henley/DESIGN.md';

const fixture = readFileSync(FIXTURE, 'utf8');

/** Swap one YAML line in the fixture, to build a deliberately broken kit. */
function withLine(from: string, to: string): string {
  assert.ok(fixture.includes(from), `fixture no longer contains: ${from}`);
  return fixture.replace(from, to);
}

test('generated CSS matches the committed snapshot', () => {
  const css = generate(fixture);

  if (process.env.UPDATE_SNAPSHOTS === '1' || !existsSync(SNAPSHOT)) {
    writeFileSync(SNAPSHOT, css);
    console.log(`snapshot written: ${SNAPSHOT}`);
    return;
  }

  assert.equal(
    css,
    readFileSync(SNAPSHOT, 'utf8'),
    'generated tokens differ from the snapshot. If the change is intended, ' +
      'rerun with UPDATE_SNAPSHOTS=1 (npm run test:update) and review the diff.',
  );
});

test('a reference to a token the kit does not define is a hard error', () => {
  const broken = withLine('backgroundColor: "{colors.primary}"', 'backgroundColor: "{colors.teal}"');
  assert.throws(
    () => generate(broken),
    (error: Error) => {
      assert.match(error.message, /components\.button-primary\.backgroundColor/);
      assert.match(error.message, /no colors\.teal/);
      return true;
    },
    'an unresolved reference must throw rather than emit an empty value',
  );
});

test('a required component missing from the kit is a hard error', () => {
  const broken = fixture.replace(/  input:\n(    .*\n)+/, '');
  assert.throws(() => generate(broken), /has no component "input"/);
});

test('an optional component missing from the kit is not an error', () => {
  // `footer` has no recipe in the kit at all; the generator must tolerate that.
  const css = generate(fixture);
  assert.ok(!css.includes('--footer-'), 'footer tokens should be absent, not empty');
});

test('other brands and chart palettes are left out', () => {
  const css = generate(fixture);
  for (const absent of ['--color-cortex-primary', '--color-henley-care-ink', '--color-chart-1']) {
    assert.ok(!css.includes(absent), `${absent} belongs to another brand and must not be emitted`);
  }
  assert.ok(css.includes('--color-primary: #0E5B70;'), 'the site\'s own colours must survive');
});

test('components the site does not use are left out', () => {
  const css = generate(fixture);
  assert.ok(!css.includes('--table-row-'), 'table-row is in the kit but not in COMPONENTS');
});

test('references become var(), never inlined literals', () => {
  const css = generate(fixture);
  assert.ok(css.includes('--button-primary-bg: var(--color-primary);'));
  assert.ok(
    !/--button-primary-bg: #/.test(css),
    'inlining the literal would make the alias a copy that goes stale',
  );
});

test('spacing tokens are not double-prefixed', () => {
  const css = generate(fixture);
  assert.ok(css.includes('--space-lg: 24px;'));
  assert.ok(css.includes('--space-touch-target: 44px;'));
  assert.ok(!css.includes('--space-space-'), 'the kit\'s space- prefix must be stripped once');
  // The resolver has to agree with the emitter, or components point at nothing.
  assert.ok(css.includes('--card-padding: var(--space-lg);'));
});

test('type scales emit a usable font shorthand', () => {
  const css = generate(fixture);
  assert.ok(css.includes('--type-body-md: 400 16px/1.5 var(--family-sans);'));
  assert.ok(css.includes('--type-body-md-size: 16px;'));
  assert.ok(css.includes('--type-button-label-letter-spacing: 0.02em;'));
  assert.ok(css.includes('--family-mono: ui-monospace, Consolas, monospace;'));
});

test('front-matter is required', () => {
  assert.throws(() => generate('# Just a heading\n\nNo front-matter here.\n'), /no YAML front-matter/);
});

test('the real brand kit still generates', { skip: !existsSync(BRAND_KIT) && 'brand kit not mounted' }, () => {
  const css = generate(readFileSync(BRAND_KIT, 'utf8'));
  // Henley Teal, the one colour whose value the style guide states outright.
  assert.ok(css.includes('--color-primary: #0E5B70;'));
  assert.ok(css.includes('--color-focus-ring: #6FA3B2;'));
  assert.ok(css.includes('--space-touch-target: 44px;'), 'the 44px touch target is an accessibility floor');
  assert.ok(!css.includes('--color-cortex-'), 'Cortex tokens must not reach this site');
  assert.ok(!/var\(--[a-z-]*undefined/.test(css));
});
