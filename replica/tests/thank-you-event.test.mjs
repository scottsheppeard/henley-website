// The one piece of behaviour the replica adds to a WordPress page: the
// thank-you page tells GTM about a stored enquiry, once. This runs the page's
// own inline script, read from the committed export, against a stub window.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const page = readFileSync(new URL('../site/thank-you/index.html', import.meta.url), 'utf8');
const match = page.match(/<script id="enquiry-submitted-event">([\s\S]*?)<\/script>/);

const EMAIL = 'a'.repeat(64);
const PHONE = 'b'.repeat(64);
const REF = 'Zk3_x-9QpLm2Ab7c';
const marker = (...parts) => `henley_enquiry=${parts.join('.')}`;

// `cookies` is the Cookie header the browser would hold; writes are recorded
// rather than applied, so a test can see exactly what the page asked for.
function visit(href, { cookies = '', dataLayer } = {}) {
  const replaced = [];
  const written = [];
  const window = {
    location: { href },
    history: { state: null, replaceState: (state, title, url) => replaced.push(url) },
  };
  if (dataLayer) window.dataLayer = dataLayer;
  const document = {
    get cookie() { return cookies; },
    set cookie(value) { written.push(value); },
  };
  vm.runInNewContext(match[1], { window, document, URL });
  return { dataLayer: window.dataLayer, replaced, written };
}

// Objects made inside the sandbox have the sandbox's prototypes, which strict
// deep equality rejects even when the data matches; compare the data.
const plain = (value) => JSON.parse(JSON.stringify(value));

test('the thank-you page carries the event script', () => {
  assert.ok(match, 'no <script id="enquiry-submitted-event"> in site/thank-you/index.html');
  assert.equal(page.match(/enquiry-submitted-event/g).length, 1, 'the script must appear once');
});

test('a stored enquiry pushes the event once, with its reference and hashes', () => {
  const { dataLayer, replaced, written } = visit('https://thehenley.com.au/thank-you/?sent=1', {
    cookies: `_ga=GA1.1.1.2; ${marker('v1', REF, EMAIL, PHONE)}`,
  });
  assert.deepEqual(plain(dataLayer), [{
    event: 'enquiry_submitted',
    enquiry_ref: REF,
    enquiry_user_data: { sha256_email_address: EMAIL, sha256_phone_number: PHONE },
  }]);
  assert.deepEqual(replaced, ['/thank-you/']);
});

test('the marker is deleted where the receiver set it, so a reload cannot count again', () => {
  const { written } = visit('https://thehenley.com.au/thank-you/?sent=1', {
    cookies: marker('v1', REF, EMAIL, PHONE),
  });
  assert.equal(written.length, 1);
  assert.match(written[0], /^henley_enquiry=;/);
  assert.match(written[0], /Max-Age=0/);
  assert.match(written[0], /Path=\/thank-you\//);
});

test('an enquiry without a phone number sends the email hash alone', () => {
  const { dataLayer } = visit('https://thehenley.com.au/thank-you/?sent=1', {
    cookies: marker('v1', REF, EMAIL, ''),
  });
  assert.deepEqual(plain(dataLayer), [{
    event: 'enquiry_submitted',
    enquiry_ref: REF,
    enquiry_user_data: { sha256_email_address: EMAIL },
  }]);
});

test('the event joins the dataLayer GTM already created', () => {
  const existing = [{ 'gtm.start': 1, event: 'gtm.js' }];
  const { dataLayer } = visit('https://thehenley.com.au/thank-you/?sent=1', {
    cookies: marker('v1', REF, EMAIL, PHONE),
    dataLayer: existing,
  });
  assert.equal(dataLayer, existing);
  assert.equal(dataLayer.length, 2);
  assert.equal(dataLayer[1].event, 'enquiry_submitted');
});

test('other query parameters and the fragment survive the clean-up', () => {
  const { replaced } = visit('https://thehenley.com.au/thank-you/?utm_source=google&sent=1&gclid=abc#top');
  assert.deepEqual(replaced, ['/thank-you/?utm_source=google&gclid=abc#top']);
});

// The address is not proof of an enquiry: the spam trap, a shared link and a
// typed URL all carry ?sent=1 and none of them carries the receiver's cookie.
for (const [label, href, cookies] of [
  ['?sent=1 with no marker', 'https://thehenley.com.au/thank-you/?sent=1', '_ga=GA1.1.1.2'],
  ['a plain visit', 'https://thehenley.com.au/thank-you/', ''],
  ['a cookie whose name only ends like ours', 'https://thehenley.com.au/thank-you/?sent=1', `old_${marker('v1', REF, EMAIL, PHONE)}`],
]) {
  test(`no event for ${label}`, () => {
    const { dataLayer, written } = visit(href, { cookies });
    assert.equal(dataLayer, undefined);
    assert.deepEqual(written, []);
  });
}

// A marker that is not ours to trust is dropped, and still deleted.
for (const [label, value] of [
  ['an unknown version', marker('v2', REF, EMAIL, PHONE)],
  ['a missing reference', marker('v1', '', EMAIL, PHONE)],
  ['a reference with markup in it', marker('v1', '<script>alert(1)</script>', EMAIL, PHONE)],
]) {
  test(`no event for ${label}`, () => {
    const { dataLayer, written } = visit('https://thehenley.com.au/thank-you/?sent=1', { cookies: value });
    assert.equal(dataLayer, undefined);
    assert.equal(written.length, 1);
  });
}

test('values that are not SHA-256 hashes never reach the dataLayer', () => {
  const { dataLayer } = visit('https://thehenley.com.au/thank-you/?sent=1', {
    cookies: marker('v1', REF, 'margaret@example.com', '0400000000'),
  });
  assert.deepEqual(plain(dataLayer), [{ event: 'enquiry_submitted', enquiry_ref: REF }]);
});
