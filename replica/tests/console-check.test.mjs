import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { checkOrigin } from '../console-check.mjs';

const html = (body) => `<!doctype html><html><body>${body}</body></html>`;

let server;
let origin;
let probeStatus = 404;

test.before(async () => {
  server = createServer((request, response) => {
    switch (request.url) {
      case '/missing-local/':
        response.end(html('<img src="/missing.jpg">'));
        return;
      case '/csp/':
        response.setHeader('Content-Security-Policy', "default-src 'self'; img-src 'none'");
        response.end(html('<img src="/allowed-by-html-but-blocked-by-csp.jpg">'));
        return;
      case '/external-failure/':
        // A closed local port is a deterministic third-party-origin failure.
        response.end(html('<img src="http://127.0.0.1:1/gtm-style-failure.jpg">'));
        return;
      case '/no-such-page-console-check/':
        response.statusCode = probeStatus;
        response.end(html('expected probe'));
        return;
      default:
        response.statusCode = 404;
        response.end('missing asset');
    }
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  origin = `http://127.0.0.1:${server.address().port}`;
});

test.after(async () => {
  server.close();
  await once(server, 'close');
});

async function gate(path) {
  const lines = [];
  const result = await checkOrigin(origin, { paths: [path], widths: [390], log: (line) => lines.push(line) });
  return { result, lines };
}

test('browser fixture: a missing local image fails through the response event', async () => {
  const { result, lines } = await gate('/missing-local/');
  assert.ok(result.fatalFindings > 0);
  assert.equal(result.externalWarnings, 0);
  assert.match(lines.join('\n'), /404: .*\/missing\.jpg/);
});

test('browser fixture: a CSP violation fails through the injected event listener', async () => {
  const { result, lines } = await gate('/csp/');
  assert.ok(result.fatalFindings > 0);
  assert.match(lines.join('\n'), /CSP img-src blocked/);
});

test('browser fixture: an external failed request is reported but passes', async () => {
  const { result, lines } = await gate('/external-failure/');
  assert.equal(result.fatalFindings, 0);
  assert.ok(result.externalWarnings > 0);
  assert.match(lines.join('\n'), /external: failed .*127\.0\.0\.1:1/);
});

test('browser fixture: the expected main-document 404 passes but the same probe at 500 fails', async () => {
  probeStatus = 404;
  const expected = await gate('/no-such-page-console-check/');
  assert.equal(expected.result.fatalFindings, 0);

  // The route remains exactly the probe path: status, rather than path alone,
  // controls the exception.
  probeStatus = 500;
  const broken = await gate('/no-such-page-console-check/');
  assert.ok(broken.result.fatalFindings > 0);
  assert.match(broken.lines.join('\n'), /500: .*\/no-such-page-console-check\//);
  probeStatus = 404;
});
