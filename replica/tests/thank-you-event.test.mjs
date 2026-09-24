// The one piece of behaviour the replica adds to a WordPress page: the
// thank-you page tells GTM about a stored enquiry, once. This runs the page's
// own inline script, read from the committed export, against a stub window.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const page = readFileSync(new URL('../site/thank-you/index.html', import.meta.url), 'utf8');
const match = page.match(/<script id="enquiry-submitted-event">([\s\S]*?)<\/script>/);

function visit(href, dataLayer) {
  const replaced = [];
  const window = {
    location: { href },
    history: { state: null, replaceState: (state, title, url) => replaced.push(url) },
  };
  if (dataLayer) window.dataLayer = dataLayer;
  vm.runInNewContext(match[1], { window, URL });
  return { dataLayer: window.dataLayer, replaced };
}

// Objects made inside the sandbox have the sandbox's prototypes, which strict
// deep equality rejects even when the data matches; compare the data.
const plain = (value) => JSON.parse(JSON.stringify(value));

test('the thank-you page carries the event script', () => {
  assert.ok(match, 'no <script id="enquiry-submitted-event"> in site/thank-you/index.html');
  assert.equal(page.match(/enquiry-submitted-event/g).length, 1, 'the script must appear once');
});

test('a stored enquiry pushes the event once and removes the marker', () => {
  const { dataLayer, replaced } = visit('https://thehenley.com.au/thank-you/?sent=1');
  assert.deepEqual(plain(dataLayer), [{ event: 'enquiry_submitted' }]);
  assert.deepEqual(replaced, ['/thank-you/']);
});

test('the event joins the dataLayer GTM already created', () => {
  const existing = [{ 'gtm.start': 1, event: 'gtm.js' }];
  const { dataLayer } = visit('https://thehenley.com.au/thank-you/?sent=1', existing);
  assert.equal(dataLayer, existing);
  assert.deepEqual(plain(dataLayer), [{ 'gtm.start': 1, event: 'gtm.js' }, { event: 'enquiry_submitted' }]);
});

test('other query parameters and the fragment survive the clean-up', () => {
  const { replaced } = visit('https://thehenley.com.au/thank-you/?utm_source=google&sent=1&gclid=abc#top');
  assert.deepEqual(replaced, ['/thank-you/?utm_source=google&gclid=abc#top']);
});

for (const href of [
  'https://thehenley.com.au/thank-you/',
  'https://thehenley.com.au/thank-you/?sent=0',
  'https://thehenley.com.au/thank-you/?utm_source=newsletter',
]) {
  test(`no event and no URL change for ${new URL(href).search || 'a plain visit'}`, () => {
    const { dataLayer, replaced } = visit(href);
    assert.equal(dataLayer, undefined);
    assert.deepEqual(replaced, []);
  });
}
