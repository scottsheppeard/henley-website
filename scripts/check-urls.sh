#!/usr/bin/env bash
#
# check-urls.sh — assert a deployment against the migration manifest.
#
# Every address the WordPress site answered has to keep answering, or keep
# redirecting to something that does. That contract is recorded in
# source/migration-manifest.json and src/content/redirects.json; this checks a
# running site against it, one request at a time, and says which ones are wrong.
#
# Two modes, because it is asked two different questions.
#
#   --strict   (default) Everything in the manifest must be right. This is the
#              release gate: a missing page, a missing feed, a document that is
#              not a PDF, a redirect whose destination 404s, or a connection
#              that fails, all make it exit non-zero. Nothing is skipped and
#              nothing unknown passes.
#
#   --sample   The design sample is five pages; the rest is Stage 3. Required
#              pages must still be right, everything else outstanding is
#              *reported* rather than failed, and the exit code stays zero.
#              This is a progress report. It is not launch acceptance and must
#              never be quoted as one.
#
# It also checks *what came back*, not only the status. A static server will
# happily answer /feed/ with the home page and /documents/x.pdf with an HTML
# error page, both with a 200; the earlier version of this script would have
# called that a pass.
#
#   scripts/check-urls.sh --sample https://dev.thehenley.com.au
#   scripts/check-urls.sh --strict https://thehenley.com.au
#   scripts/check-urls.sh http://localhost:8080          # strict
set -euo pipefail

MODE="strict"
BASE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) MODE="strict"; shift ;;
    --sample) MODE="sample"; shift ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \?//'; exit 0 ;;
    -*) echo "check-urls.sh: unknown option $1" >&2; exit 2 ;;
    *) BASE="$1"; shift ;;
  esac
done

BASE="${BASE:-http://localhost:8080}"
# CHECK_URLS_ROOT exists for scripts/check-urls-fixture.sh, which needs to point
# the checker at a deliberately malformed manifest to prove it refuses one.
REPO_ROOT="${CHECK_URLS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

BASE="$BASE" MODE="$MODE" REPO_ROOT="$REPO_ROOT" python3 - <<'PY'
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

base = os.environ["BASE"].rstrip("/")
mode = os.environ["MODE"]
root = Path(os.environ["REPO_ROOT"])
strict = mode == "strict"

manifest = json.loads((root / "source/migration-manifest.json").read_text())
redirects = json.loads((root / "src/content/redirects.json").read_text())

passed, failures, pending = 0, [], []

# The pages the design sample covers. In sample mode everything else in the
# manifest is Stage 3 and is reported as outstanding rather than as a failure —
# a checker that shows 21 red lines for work nobody has started yet is a checker
# people stop reading. In strict mode this set means nothing: all of it is
# required.
SAMPLE = {
    "/", "/luxury-retirement-living/", "/private-aged-care/",
    "/contact/", "/thank-you/",
}

MAX_HOPS = 5
TIMEOUT = "20"


class Fetch:
    """One request, with enough of the response to tell what actually came back."""

    def __init__(self, path):
        self.path = path
        self.url = f"{base}{path}"
        self.status = None
        self.location = None
        self.content_type = ""
        self.cache_control = ""
        self.body = b""
        self.error = None

        with tempfile.TemporaryDirectory() as work:
            body_file = Path(work) / "body"
            head_file = Path(work) / "head"
            result = subprocess.run(
                ["curl", "-sS", "--max-time", TIMEOUT,
                 "-o", str(body_file), "-D", str(head_file),
                 "-w", "%{http_code}", self.url],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                self.error = (result.stderr.strip().splitlines() or ["curl failed"])[-1]
                return
            self.status = result.stdout.strip()
            headers = head_file.read_text(errors="replace")
            self.location = self._header(headers, "location")
            self.content_type = (self._header(headers, "content-type") or "").lower()
            self.cache_control = (self._header(headers, "cache-control") or "").lower()
            # Enough to identify a document; never the whole of one.
            self.body = body_file.read_bytes()[:8192]

    @staticmethod
    def _header(headers, name):
        found = None
        for line in headers.splitlines():
            if ":" in line and line.split(":", 1)[0].strip().lower() == name:
                found = line.split(":", 1)[1].strip()  # last wins, after redirects
        return found

    @property
    def text(self):
        return self.body.decode("utf-8", errors="replace")

    def same_origin_path(self):
        """The Location as a path, or None when it points somewhere else."""
        if not self.location:
            return None
        if self.location.startswith("/"):
            return self.location
        split = urlsplit(self.location)
        if f"{split.scheme}://{split.netloc}" != base:
            return None
        return split.path + (f"?{split.query}" if split.query else "")


def record(ok, label, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(label)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
    return ok


def outstanding(path, detail):
    pending.append((path, detail))


# ── What a response has to look like to count ────────────────────────────────
#
# A 200 is not evidence that the right thing came back. nginx will serve the
# SPA-ish fallback, an HTML error page, or the home page for a path it does not
# recognise, and the old check counted every one of those as a pass.

def kind_of(path):
    clean = path.split("?", 1)[0]
    if clean.endswith(".pdf"):
        return "pdf"
    if clean.endswith("/feed/") or clean.endswith("/feed"):
        return "feed"
    if clean.endswith(".xml"):
        return "sitemap"
    if clean.endswith(".txt"):
        return "text"
    return "html"


CANONICAL_RE = re.compile(
    r"""<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']+)["']""", re.I,
)


def content_is_right(path, response):
    """Does the body look like the thing that was asked for?"""
    kind = kind_of(path)

    if kind == "pdf":
        if "application/pdf" not in response.content_type:
            return False, f"content-type {response.content_type or 'missing'}, not a PDF"
        if not response.body.startswith(b"%PDF-"):
            return False, "body does not begin %PDF-"
        return True, ""

    if kind in {"feed", "sitemap"}:
        if "xml" not in response.content_type:
            return False, f"content-type {response.content_type or 'missing'}, not XML"
        head = response.body.lstrip()[:400].lower()
        if not head.startswith(b"<?xml"):
            return False, "body does not begin <?xml"
        wanted = (b"<rss", b"<feed") if kind == "feed" else (b"<sitemapindex", b"<urlset")
        if not any(token in head for token in wanted):
            return False, f"no {' or '.join(t.decode() for t in wanted)} element"
        return True, ""

    if kind == "text":
        if "text/" not in response.content_type:
            return False, f"content-type {response.content_type or 'missing'}"
        return True, ""

    # HTML. The canonical link is the page saying which page it is, and every
    # page on this site emits one — so a home page or an error page served in
    # place of /dining/ identifies itself rather than passing quietly.
    if "text/html" not in response.content_type:
        return False, f"content-type {response.content_type or 'missing'}, not HTML"
    match = CANONICAL_RE.search(response.text)
    if not match:
        return False, "no <link rel=canonical> to identify the page"
    canonical_path = urlsplit(match.group(1)).path or "/"
    if canonical_path.rstrip("/") != path.split("?", 1)[0].rstrip("/"):
        return False, f"canonical says {canonical_path}"
    return True, ""


def resolve(path, label, hops=MAX_HOPS):
    """Follow a redirect chain to the resource it is supposed to reach.

    A redirect with the right status and the right Location is still broken if
    the destination is not there, and that is exactly the failure a header-only
    check cannot see.
    """
    seen = [path]
    current = path
    for _ in range(hops):
        response = Fetch(current)
        if response.error:
            return False, f"{current}: {response.error}"
        if response.status in {"301", "302", "307", "308"}:
            nxt = response.same_origin_path()
            if nxt is None:
                return False, f"{current} redirects off-origin to {response.location}"
            if nxt in seen:
                return False, f"redirect loop: {' -> '.join(seen)} -> {nxt}"
            seen.append(nxt)
            current = nxt
            continue
        if response.status != "200":
            return False, f"{' -> '.join(seen)} ends {response.status}"
        ok, why = content_is_right(current, response)
        if not ok:
            return False, f"{' -> '.join(seen)} arrives at the wrong thing: {why}"
        return True, " -> ".join(seen)
    return False, f"more than {hops} redirects: {' -> '.join(seen)}"


def expect_ok(path, want_status, label, want_target=None, check_content=True):
    response = Fetch(path)
    if response.error:
        return record(False, label, f"request failed: {response.error}")
    if response.status != str(want_status):
        return record(False, label, f"expected {want_status}, got {response.status}")

    if want_target is not None:
        actual = response.same_origin_path()
        if actual is None:
            return record(False, label, f"redirects off-origin to {response.location}")
        if actual.rstrip("/") != want_target.rstrip("/"):
            return record(False, label, f"redirects to {actual}, expected {want_target}")
        reached, detail = resolve(path, label)
        if not reached:
            return record(False, label, detail)
        return record(True, label)

    if check_content and response.status == "200":
        ok, why = content_is_right(path, response)
        if not ok:
            return record(False, label, why)

    return record(True, label)


# ── Index the redirect rules, so a manifest URL covered by one is satisfied ───
literal_redirects = {
    rule["from"]: rule for rule in redirects["redirects"] if not rule.get("pattern")
}

print(f"checking {base}  [{mode} mode]\n")

# ── Every page and post the old site published ──────────────────────────────
print(f"pages and posts ({len(manifest['urls'])}):")
for entry in manifest["urls"]:
    path = entry["path"]
    if strict or path in SAMPLE:
        expect_ok(path, 200, path)
    else:
        response = Fetch(path)
        if response.error:
            record(False, path, f"request failed: {response.error}")
        elif response.status == "200" and content_is_right(path, response)[0]:
            passed += 1
        else:
            outstanding(path, f"{response.status}")

# ── The addresses the sitemaps omitted ──────────────────────────────────────
print("\nother live addresses:")
for entry in manifest["extra_urls"]:
    path = entry["path"]
    want = entry.get("expect")

    # A path with a redirect rule of its own is satisfied by that redirect
    # resolving, which the redirect section below checks. The Yoast sitemaps are
    # this case: the manifest says they answered 200, and the new site answers
    # them with a deliberate 301 to /sitemap-index.xml.
    if path in literal_redirects:
        print(f"  ...  {path}  (satisfied by a redirect rule; checked below)")
        continue

    if want == "404":
        expect_ok(path, 404, path, check_content=False)
    elif want == "200":
        if strict or path in SAMPLE:
            expect_ok(path, 200, path)
        else:
            response = Fetch(path)
            if response.error:
                record(False, path, f"request failed: {response.error}")
            elif response.status == "200" and content_is_right(path, response)[0]:
                passed += 1
            else:
                outstanding(path, f"{response.status}")
    elif want == "200 or intended 301":
        # Deliberate either way, but it has to end somewhere real.
        response = Fetch(path)
        if response.error:
            record(False, path, f"request failed: {response.error}")
        elif response.status in {"200", "301", "302", "307", "308"}:
            reached, detail = resolve(path, path)
            if reached:
                record(True, path)
            elif strict:
                record(False, path, detail)
            else:
                outstanding(path, detail)
        elif strict:
            record(False, path, f"expected 200 or a deliberate redirect, got {response.status}")
        else:
            outstanding(path, f"{response.status}")
    else:
        # An expectation nobody has written down is not a pass. It used to be a
        # `continue`, which is how /feed/ and /news/page/2/ went unchecked.
        record(False, path, f"unknown expectation {want!r} in the manifest")

# ── Documents, at both their addresses ──────────────────────────────────────
print(f"\ndocuments ({len(manifest['documents'])} x 2 addresses):")
for document in manifest["documents"]:
    for label, path in (("dated", document["path"]), ("alias", document["alias"])):
        if not strict and path not in SAMPLE:
            response = Fetch(path)
            if response.error:
                record(False, path, f"request failed: {response.error}")
            elif response.status == "200" and content_is_right(path, response)[0]:
                passed += 1
            else:
                outstanding(path, f"{response.status}")
            continue

        if not expect_ok(path, 200, f"{path} ({label})"):
            continue
        # The alias always points at the current revision, so it must
        # revalidate; the dated file never changes, so it should not.
        response = Fetch(path)
        cache = response.cache_control
        if label == "alias":
            record("no-cache" in cache or "must-revalidate" in cache or "max-age=0" in cache,
                   f"{path} revalidates", f"cache-control: {cache or 'missing'}")
        else:
            record("max-age=" in cache and "max-age=0" not in cache,
                   f"{path} is long-cached", f"cache-control: {cache or 'missing'}")

# ── Redirects ───────────────────────────────────────────────────────────────
named = [r for r in redirects["redirects"] if not r["from"].startswith("/?p=")]
shortlinks = [r for r in redirects["redirects"] if r["from"].startswith("/?p=")]

print(f"\nnamed redirects ({len(named)}):")
for rule in named:
    if rule.get("pattern"):
        # /latest-articles/(.*) -> /$1, checked with a real article slug.
        slug = "top-10-questions-to-ask-your-sales-manager"
        source = f"/latest-articles/{slug}/"
        if strict or f"/{slug}/" in SAMPLE:
            expect_ok(source, 301, f"{source} ({rule['reason']})", f"/{slug}/")
        else:
            response = Fetch(source)
            if response.error:
                record(False, source, f"request failed: {response.error}")
            elif response.status == "301":
                passed += 1   # the rule fires; its destination is Stage 3
                if not resolve(source, source)[0]:
                    outstanding(source, "redirect fires, destination not built yet")
            else:
                outstanding(source, f"{response.status}")
    else:
        target_built = rule["to"] in SAMPLE or rule["to"].endswith(".xml")
        if strict or target_built:
            expect_ok(rule["from"], rule["status"], f"{rule['from']} ({rule['reason']})", rule["to"])
        else:
            response = Fetch(rule["from"])
            if response.error:
                record(False, rule["from"], f"request failed: {response.error}")
            elif response.status == str(rule["status"]):
                passed += 1
                if not resolve(rule["from"], rule["from"])[0]:
                    outstanding(rule["from"], "redirect fires, destination not built yet")
            else:
                outstanding(rule["from"], f"{response.status}")

print(f"\nshortlinks ({len(shortlinks)}):")
for rule in shortlinks:
    if strict or rule["to"] in SAMPLE:
        expect_ok(rule["from"], 301, rule["from"], rule["to"])
    else:
        response = Fetch(rule["from"])
        if response.error:
            record(False, rule["from"], f"request failed: {response.error}")
        elif response.status == "301":
            passed += 1
            if not resolve(rule["from"], rule["from"])[0]:
                outstanding(rule["from"], "redirect fires, destination not built yet")
        else:
            outstanding(rule["from"], f"{response.status}")

# An id that was never published simply resolves to /, because a query string
# does not identify a different resource on a static site. WordPress answered
# 404 there only because it interpreted ?p= itself. Serving the home page is
# the correct behaviour and a better landing than a 404; this pins that it is
# deliberate rather than an accident of configuration.
print("\nunknown shortlink:")
expect_ok("/?p=999999", 200, "/?p=999999 serves the home page")

# ── WordPress paths are gone for good ───────────────────────────────────────
print("\nretired WordPress surface:")
for path in ("/xmlrpc.php", "/wp-login.php", "/wp-admin/", "/wp-json/", "/index.php"):
    expect_ok(path, 410, path, check_content=False)

# ── Security headers ────────────────────────────────────────────────────────
print("\nsecurity headers:")
home = Fetch("/")
if home.error:
    record(False, "security headers", f"request failed: {home.error}")
else:
    raw = subprocess.run(
        ["curl", "-sSI", "--max-time", TIMEOUT, f"{base}/"],
        capture_output=True, text=True,
    ).stdout.lower()
    for header in ("content-security-policy", "x-content-type-options",
                   "referrer-policy", "permissions-policy"):
        record(header in raw, f"header {header}")

    # The CSP must name the Google Ads hosts, or the tel:/mailto: click
    # conversions — currently the only measurement the business has — stop
    # firing silently.
    for host in ("googletagmanager.com", "googleadservices.com", "google-analytics.com"):
        record(host in raw, f"CSP allows {host}")

# ── Verdict ─────────────────────────────────────────────────────────────────
if pending:
    print(f"\n{len(pending)} address(es) not built yet (Stage 3), not counted as failures:")
    for path, detail in pending:
        print(f"  ...  {path}  ({detail})")

print(f"\n{passed} passed, {len(failures)} failed, {len(pending)} outstanding")

if strict:
    if pending:
        # Nothing may be outstanding in strict mode; if anything is, the mode
        # has a hole in it and saying so is more useful than a green tick.
        print("strict mode reported outstanding work, which it should never do")
        sys.exit(1)
    print("STRICT: every address in the manifest answers correctly"
          if not failures else "STRICT: NOT READY")
else:
    print("SAMPLE: a progress report, not launch acceptance. "
          "Run --strict before any cutover.")

sys.exit(1 if failures else 0)
PY
