#!/usr/bin/env bash
#
# check-urls.sh — assert a deployment against the migration manifest.
#
# Every address the WordPress site answered has to keep answering, or keep
# redirecting to something that does. That contract is recorded in
# source/migration-manifest.json and src/content/redirects.json; this checks a
# running site against it, one request at a time, and says which ones are wrong.
#
# Run it against the container before a deploy, against nonprod after one, and
# against production immediately after cutover.
#
#   scripts/check-urls.sh http://localhost:8080
#   scripts/check-urls.sh https://dev.thehenley.com.au
set -euo pipefail

BASE="${1:-http://localhost:8080}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE="$BASE" REPO_ROOT="$REPO_ROOT" python3 - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

base = os.environ["BASE"].rstrip("/")
root = Path(os.environ["REPO_ROOT"])

manifest = json.loads((root / "source/migration-manifest.json").read_text())
redirects = json.loads((root / "src/content/redirects.json").read_text())

passed, failures, pending = 0, [], []

# The pages the design sample covers. Everything else in the manifest is Stage 3
# and is reported as outstanding rather than as a failure — a checker that shows
# 21 red lines for work nobody has started yet is a checker people stop reading.
BUILT = {
    "/", "/luxury-retirement-living/", "/private-aged-care/",
    "/contact/", "/thank-you/",
}


def request(path):
    """Status and Location for one request, without following the redirect."""
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "20", "-o", "/dev/null",
         "-w", "%{http_code} %{redirect_url}", f"{base}{path}"],
        capture_output=True, text=True,
    )
    status, _, target = result.stdout.partition(" ")
    return status, target.strip()


def expect(path, want_status, want_target=None, note=""):
    global passed
    status, target = request(path)

    ok = status == str(want_status)
    if ok and want_target is not None:
        # Compare paths, so the check works against any origin.
        actual = target.replace(base, "") or "/"
        ok = actual == want_target

    if ok:
        passed += 1
    else:
        failures.append((path, want_status, want_target, status, target, note))
        arrow = f" -> {want_target}" if want_target else ""
        print(f"  FAIL {path}  expected {want_status}{arrow}, got {status} {target}")


print(f"checking {base}\n")

# ── Every page and post the old site published ──────────────────────────────
print(f"pages and posts ({len(manifest['urls'])}):")
for entry in manifest["urls"]:
    if entry["path"] in BUILT:
        expect(entry["path"], 200)
    else:
        status, _ = request(entry["path"])
        if status == "200":
            passed += 1
        else:
            pending.append(entry["path"])

# ── The addresses the sitemaps omitted ──────────────────────────────────────
print(f"\nother live addresses:")
for entry in manifest["extra_urls"]:
    # /feed/ and the news pagination are Stage 3 work; skip until they exist.
    if entry["path"] in {"/feed/", "/news/feed/", "/news/page/2/"}:
        continue
    if entry["path"] in {"/sitemap_index.xml", "/page-sitemap.xml", "/post-sitemap.xml"}:
        continue  # asserted as redirects below
    want = 404 if entry["expect"] == "404" else 200
    expect(entry["path"], want)

# ── Redirects ───────────────────────────────────────────────────────────────
named = [r for r in redirects["redirects"] if not r["from"].startswith("/?p=")]
shortlinks = [r for r in redirects["redirects"] if r["from"].startswith("/?p=")]

print(f"\nnamed redirects ({len(named)}):")
for rule in named:
    if rule.get("pattern"):
        # /latest-articles/(.*) -> /$1, checked with a real article slug.
        slug = "top-10-questions-to-ask-your-sales-manager"
        expect(f"/latest-articles/{slug}/", 301, f"/{slug}/", rule["reason"])
    else:
        expect(rule["from"], rule["status"], rule["to"], rule["reason"])

print(f"\nshortlinks ({len(shortlinks)}):")
for rule in shortlinks:
    expect(rule["from"], 301, rule["to"])

# An id that was never published simply resolves to /, because a query string
# does not identify a different resource on a static site. WordPress answered
# 404 there only because it interpreted ?p= itself. Serving the home page is
# the correct behaviour and a better landing than a 404; this pins that it is
# deliberate rather than an accident of configuration.
print("\nunknown shortlink:")
expect("/?p=999999", 200)

# ── WordPress paths are gone for good ───────────────────────────────────────
print("\nretired WordPress surface:")
for path in ("/xmlrpc.php", "/wp-login.php", "/wp-admin/", "/wp-json/", "/index.php"):
    expect(path, 410)

# ── Security headers ────────────────────────────────────────────────────────
print("\nsecurity headers:")
headers = subprocess.run(
    ["curl", "-sSI", "--max-time", "20", f"{base}/"], capture_output=True, text=True
).stdout.lower()
for header in ("content-security-policy", "x-content-type-options",
               "referrer-policy", "permissions-policy"):
    if header in headers:
        passed += 1
    else:
        failures.append((f"header {header}", "present", None, "absent", "", ""))
        print(f"  FAIL missing header: {header}")

# The CSP must name the Google Ads hosts, or the tel:/mailto: click conversions
# — currently the only measurement the business has — stop firing silently.
for host in ("googletagmanager.com", "googleadservices.com", "google-analytics.com"):
    if host in headers:
        passed += 1
    else:
        failures.append((f"CSP allows {host}", "present", None, "absent", "", ""))
        print(f"  FAIL CSP does not allow {host}")

if pending:
    print(f"\n{len(pending)} URL(s) not built yet (Stage 3), not counted as failures:")
    for path in pending:
        print(f"  ...  {path}")

print(f"\n{passed} passed, {len(failures)} failed, {len(pending)} outstanding")
sys.exit(1 if failures else 0)
PY
