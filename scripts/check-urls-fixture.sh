#!/usr/bin/env bash
#
# check-urls-fixture.sh — prove that check-urls.sh --strict actually fails.
#
# A release gate is only worth having if you know what it catches, and the
# previous one caught less than it looked like it did: pages outside a
# hard-coded set were merely "outstanding", /feed/, /news/feed/ and
# /news/page/2/ were skipped entirely, and a redirect with the right status was
# accepted without anyone asking whether its destination existed. All of that
# still exits zero.
#
# So this builds a *complete* fixture site out of the same manifest the checker
# reads, asserts strict passes against it, then breaks one thing at a time and
# asserts strict fails for that reason. No production, no nonprod, no network.
#
# Usage: scripts/check-urls-fixture.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PORT="${PORT:-8125}"
DEAD_PORT="${DEAD_PORT:-8126}"
WORK="$(mktemp -d)"
SERVER_PID=""

cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

cat >"$WORK/fixture.py" <<'PY'
"""A complete Henley site, served from the manifest, with one deliberate flaw.

The flaw is named in BREAK. Everything else answers exactly as a finished
deployment should, so a failure the checker reports is the flaw and nothing
else.
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ["REPO_ROOT"])
PORT = int(os.environ["PORT"])
BREAK = os.environ.get("BREAK", "")
ORIGIN = f"http://127.0.0.1:{PORT}"

manifest = json.loads((ROOT / "source/migration-manifest.json").read_text())
redirects = json.loads((ROOT / "src/content/redirects.json").read_text())

SECURITY_HEADERS = {
    "Content-Security-Policy":
        "default-src 'self'; script-src 'self' https://www.googletagmanager.com "
        "https://www.googleadservices.com https://www.google-analytics.com",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=()",
}

LONG_CACHE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


def page(path, canonical=None):
    href = f"{ORIGIN}{canonical or path}"
    return (f'<!doctype html><html lang="en-AU"><head><meta charset="utf-8">'
            f'<link rel="canonical" href="{href}">'
            f'<title>{path}</title></head><body><h1>{path}</h1></body></html>').encode()


def feed(path):
    return (f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<rss version="2.0"><channel><title>{path}</title>'
            f'<link>{ORIGIN}{path}</link></channel></rss>').encode()


def sitemap():
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'<sitemap><loc>{ORIGIN}/sitemap-0.xml</loc></sitemap>'
            '</sitemapindex>').encode()


PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"

# ── The finished site ────────────────────────────────────────────────────────
routes = {}       # path -> (status, content-type, body, cache-control)
moves = {}        # path -> target

for entry in manifest["urls"]:
    routes[entry["path"]] = (200, "text/html; charset=utf-8", page(entry["path"]), None)

routes["/news/page/2/"] = (200, "text/html; charset=utf-8", page("/news/page/2/"), None)
routes["/feed/"] = (200, "application/rss+xml; charset=utf-8", feed("/feed/"), None)
routes["/news/feed/"] = (200, "application/rss+xml; charset=utf-8", feed("/news/feed/"), None)
routes["/sitemap-index.xml"] = (200, "application/xml", sitemap(), None)
routes["/robots.txt"] = (200, "text/plain; charset=utf-8",
                         f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap-index.xml\n".encode(),
                         None)

for document in manifest["documents"]:
    routes[document["path"]] = (200, "application/pdf", PDF, LONG_CACHE)
    routes[document["alias"]] = (200, "application/pdf", PDF, REVALIDATE)

for rule in redirects["redirects"]:
    if rule.get("pattern"):
        continue
    moves[rule["from"]] = rule["to"]

RETIRED = ("/xmlrpc.php", "/wp-login.php", "/wp-admin/", "/wp-json/", "/index.php")

# ── The one deliberate flaw ──────────────────────────────────────────────────
if BREAK == "missing-page":
    del routes["/dining/"]
elif BREAK == "missing-feed":
    del routes["/feed/"]
elif BREAK == "missing-news-feed":
    del routes["/news/feed/"]
elif BREAK == "missing-news-page-2":
    del routes["/news/page/2/"]
elif BREAK == "missing-document":
    del routes["/documents/village-comparison-document.pdf"]
elif BREAK == "broken-redirect":
    # The Location is exactly what redirects.json promises. The destination is
    # not there. A header-only check calls this a pass.
    del routes["/luxury-retirement-living/"]
elif BREAK == "redirect-loop":
    # Likewise correct-looking, and it never arrives anywhere.
    del routes["/luxury-retirement-living/"]
    moves["/luxury-retirement-living/"] = "/luxury-resort-living/"
elif BREAK == "offsite-redirect":
    moves["/luxury-resort-living/"] = "https://example.com/luxury-retirement-living/"
elif BREAK == "home-page-for-feed":
    # The failure that looks healthiest: 200, HTML, the home page.
    routes["/feed/"] = (200, "text/html; charset=utf-8", page("/feed/", canonical="/"), None)
elif BREAK == "html-for-pdf":
    routes["/documents/village-comparison-document.pdf"] = (
        200, "text/html; charset=utf-8", page("/404/", canonical="/"), REVALIDATE)
elif BREAK == "wrong-page-served":
    routes["/dining/"] = (200, "text/html; charset=utf-8", page("/dining/", canonical="/"), None)
elif BREAK == "alias-never-revalidates":
    routes["/documents/village-comparison-document.pdf"] = (200, "application/pdf", PDF, LONG_CACHE)
elif BREAK == "missing-security-header":
    SECURITY_HEADERS.pop("Referrer-Policy")
elif BREAK == "csp-without-ads":
    SECURITY_HEADERS["Content-Security-Policy"] = "default-src 'self'"
elif BREAK == "wordpress-path-404":
    RETIRED = tuple(p for p in RETIRED if p != "/wp-login.php")
elif BREAK:
    raise SystemExit(f"fixture: unknown BREAK {BREAK!r}")

SHORTLINK = re.compile(r"^/\?p=(\d+)$")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, status, content_type, body, cache_control=None, location=None):
        self.send_response(status)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        if location:
            self.send_header("Location", location)
        if content_type:
            self.send_header("Content-Type", content_type)
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def route(self):
        raw = self.path
        path = urlsplit(raw).path

        if raw in moves:
            return self._send(301, "text/html", b"", location=moves[raw])
        if path in moves and not urlsplit(raw).query:
            return self._send(301, "text/html", b"", location=moves[path])

        match = SHORTLINK.match(raw)
        if match:
            target = manifest["shortlinks"].get(match.group(1))
            if target:
                return self._send(301, "text/html", b"", location=target)
            # An id that was never published lands on the home page, deliberately.
            return self._send(200, "text/html; charset=utf-8", page("/"))

        if raw.startswith("/latest-articles/"):
            return self._send(301, "text/html", b"",
                              location="/" + raw[len("/latest-articles/"):])

        if path in RETIRED or path.startswith("/wp-admin") or path.startswith("/wp-json"):
            return self._send(410, "text/html; charset=utf-8", b"<!doctype html>gone")

        if raw in routes:
            status, content_type, body, cache = routes[raw]
            return self._send(status, content_type, body, cache)
        if path in routes:
            status, content_type, body, cache = routes[path]
            return self._send(status, content_type, body, cache)

        return self._send(404, "text/html; charset=utf-8",
                          page("/404/", canonical="/404/"))

    do_GET = route
    do_HEAD = route


ThreadingHTTPServer.allow_reuse_address = True
ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
PY

failures=0
check() {
  if [[ "$1" == "ok" ]]; then
    printf '  PASS  %s\n' "$2"
  else
    printf '  FAIL  %s\n' "$2"
    failures=$((failures + 1))
  fi
}

start_fixture() {
  [[ -n "$SERVER_PID" ]] && { kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; }
  BREAK="$1" REPO_ROOT="$REPO_ROOT" PORT="$PORT" python3 "$WORK/fixture.py" &
  SERVER_PID=$!
  for _ in $(seq 1 60); do
    curl -sf --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && return 0
    sleep 0.2
  done
  echo "fixture did not start" >&2
  exit 1
}

# ── A finished site passes strict ────────────────────────────────────────────
echo "a complete site:"
start_fixture ""
if scripts/check-urls.sh --strict "http://127.0.0.1:$PORT" >"$WORK/complete.log" 2>&1; then
  check ok "strict passes with zero failures and zero outstanding"
  grep -E '^[0-9]+ passed' "$WORK/complete.log" | sed 's/^/        /'
else
  check no "strict should pass against a complete fixture"
  grep -E '^  FAIL|^[0-9]+ passed' "$WORK/complete.log" | head -12 | sed 's/^/        /'
fi

# ── And each deliberate flaw fails it ────────────────────────────────────────
echo
echo "one deliberate flaw at a time — strict must fail each:"

expect_failure() {
  local flaw="$1" expected="$2"
  start_fixture "$flaw"
  if scripts/check-urls.sh --strict "http://127.0.0.1:$PORT" >"$WORK/$flaw.log" 2>&1; then
    check no "$flaw — strict passed a broken site"
  elif grep -q "$expected" "$WORK/$flaw.log"; then
    check ok "$flaw"
  else
    check no "$flaw — failed, but not for the expected reason"
    grep -E '^  FAIL' "$WORK/$flaw.log" | head -3 | sed 's/^/        /'
  fi
}

expect_failure missing-page            '/dining/ — expected 200, got 404'
expect_failure missing-feed            '/feed/ — expected 200, got 404'
expect_failure missing-news-feed       '/news/feed/ — expected 200, got 404'
expect_failure missing-news-page-2     '/news/page/2/'
expect_failure missing-document        '/documents/village-comparison-document.pdf'
expect_failure broken-redirect         'ends 404'
expect_failure redirect-loop           'redirect loop'
expect_failure offsite-redirect        'off-origin'
expect_failure home-page-for-feed      'not XML'
expect_failure html-for-pdf            'not a PDF'
expect_failure wrong-page-served       'canonical says /'
expect_failure alias-never-revalidates 'revalidates'
expect_failure missing-security-header 'header referrer-policy'
expect_failure csp-without-ads         'CSP allows googleadservices.com'
expect_failure wordpress-path-404      '/wp-login.php — expected 410'

# ── An expectation nobody wrote down is not a pass ───────────────────────────
#
# This is the shape of the original hole: /feed/, /news/feed/ and /news/page/2/
# were `continue`d past, so the gate said nothing about three live addresses.
echo
echo "a manifest expectation the checker does not understand:"
mkdir -p "$WORK/shadow/source" "$WORK/shadow/src/content"
python3 - "$REPO_ROOT" "$WORK/shadow" <<'EDIT'
import json, sys
from pathlib import Path
source, shadow = Path(sys.argv[1]), Path(sys.argv[2])
manifest = json.loads((source / "source/migration-manifest.json").read_text())
for entry in manifest["extra_urls"]:
    if entry["path"] == "/feed/":
        entry["expect"] = "probably fine"
(shadow / "source/migration-manifest.json").write_text(json.dumps(manifest))
(shadow / "src/content/redirects.json").write_text(
    (source / "src/content/redirects.json").read_text())
EDIT
start_fixture ""
if CHECK_URLS_ROOT="$WORK/shadow" scripts/check-urls.sh --strict "http://127.0.0.1:$PORT" \
     >"$WORK/unknown.log" 2>&1; then
  check no "strict passed a manifest expectation it cannot interpret"
else
  grep -q "unknown expectation" "$WORK/unknown.log" \
    && check ok "an uninterpretable expectation fails, and says so" \
    || check no "failed, but not because of the unknown expectation"
fi

# ── A connection that never answers is a failure, not a quiet zero ───────────
echo
echo "a site that is not there:"
if scripts/check-urls.sh --strict "http://127.0.0.1:$DEAD_PORT" >"$WORK/dead.log" 2>&1; then
  check no "strict passed against a closed port"
else
  grep -q "request failed" "$WORK/dead.log" \
    && check ok "a refused connection is reported and exits non-zero" \
    || check no "exited non-zero but did not report the connection failure"
fi

# ── Sample mode stays useful, and stays honest about what it is ──────────────
echo
echo "sample mode, on a site that is only the design sample:"
start_fixture "missing-page"
if scripts/check-urls.sh --sample "http://127.0.0.1:$PORT" >"$WORK/sample.log" 2>&1; then
  check ok "an outstanding page does not fail sample mode"
else
  check no "sample mode failed on outstanding Stage 3 work"
  grep -E '^  FAIL' "$WORK/sample.log" | head -5 | sed 's/^/        /'
fi
grep -q "not launch acceptance" "$WORK/sample.log" \
  && check ok "sample mode says it is not launch acceptance" \
  || check no "sample mode did not disclaim itself"
grep -qE '^[0-9]+ passed, [0-9]+ failed, [1-9]' "$WORK/sample.log" \
  && check ok "sample mode still reports its outstanding count" \
  || check no "sample mode lost its outstanding count"

echo
if (( failures )); then
  echo "$failures fixture check(s) failed"
  exit 1
fi
echo "url gate: strict fails on every defect it is supposed to catch, and passes a complete site"
