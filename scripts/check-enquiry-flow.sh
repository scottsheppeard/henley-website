#!/usr/bin/env bash
#
# check-enquiry-flow.sh — prove the built form and the receiver still agree.
#
# The two halves of the enquiry path are written in different languages, live in
# different directories and are tested separately. Both suites can be green
# while the whole thing is broken: rename a field in the Astro form and the
# receiver quietly stores a NULL, because an HTML form simply does not send a
# field the server was hoping for.
#
# So this reads the field names out of the *built* HTML, posts exactly those to
# a real receiver, and checks what lands in the database — including the two
# things henley-utils depends on and neither side's own tests can see together:
# the id floor and the timestamp format.
#
# Usage: scripts/check-enquiry-flow.sh   (builds the site if dist/ is missing)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PORT="${PORT:-8099}"
WORK="$(mktemp -d)"
RECEIVER_PID=""

cleanup() {
  [[ -n "$RECEIVER_PID" ]] && kill "$RECEIVER_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

[[ -f dist/contact/index.html ]] || {
  echo "building the site ..."
  scripts/with-node.sh npm run build >/dev/null
}

[[ -x forms/.venv/bin/python ]] || {
  echo "forms/.venv is missing — see forms/README.md" >&2
  exit 1
}

echo "starting the receiver on :$PORT ..."
INTAKE_DB_PATH="$WORK/intake.sqlite" \
  forms/.venv/bin/python -m uvicorn app:app --app-dir forms --port "$PORT" --log-level warning &
RECEIVER_PID=$!

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
  sleep 0.25
done
curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null || { echo "receiver did not start" >&2; exit 1; }

WORK="$WORK" PORT="$PORT" REPO_ROOT="$REPO_ROOT" forms/.venv/bin/python - <<'PY'
import html
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

port = os.environ["PORT"]
work = Path(os.environ["WORK"])
root = Path(os.environ["REPO_ROOT"])

failures = []


def check(condition, message):
    print(f"  {'PASS' if condition else 'FAIL'}  {message}")
    if not condition:
        failures.append(message)


# ── What the built page actually asks for ────────────────────────────────────
page = (root / "dist/contact/index.html").read_text()
form = re.search(r"<form[^>]*action=\"/api/enquiry\"[^>]*>(.*?)</form>", page, re.S)
if not form:
    sys.exit("no enquiry form found in dist/contact/index.html")

fields = re.findall(r"<(?:input|textarea)[^>]*\bname=\"([^\"]+)\"", form.group(1))
print(f"\nfields in the built form: {sorted(set(fields))}\n")

for required in ("name", "email", "phone", "enquiry_text",
                 "interest_apartment", "interest_aged_care",
                 "page_path", "started_at", "company"):
    check(required in fields, f"the form still sends `{required}`")

check("referral_source" not in fields,
      "the form no longer asks 'How did you hear about us?'")

action = re.search(r"<form[^>]*action=\"([^\"]+)\"", page).group(1)
check(action == "/api/enquiry", f"the form posts to /api/enquiry (found {action})")

method = re.search(r"<form[^>]*method=\"([^\"]+)\"", page).group(1)
check(method.lower() == "post", "the form uses POST")

# The checkbox values are data, not labels: the classifier and Salesforce read
# these exact strings.
values = dict(re.findall(r"name=\"(interest_[a-z_]+)\"\s+value=\"([^\"]+)\"", form.group(1)))
check(values.get("interest_apartment") == "Apartment Living",
      "interest_apartment still sends the exact string 'Apartment Living'")
check(values.get("interest_aged_care") == "Private Aged Care",
      "interest_aged_care still sends the exact string 'Private Aged Care'")


def post(payload):
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/enquiry",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request) as response:
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers)


# ── A real submission, using only the fields the page sends ──────────────────
print()
submission = {field: "" for field in set(fields)}
submission.update({
    "name": "Margaret Hale",
    "email": "margaret@example.com",
    "phone": "0400 123 456",
    "enquiry_text": "Could I see a two-bedroom apartment?",
    "interest_apartment": "Apartment Living",
    "page_path": "/luxury-retirement-living/",
    "started_at": "",       # as a no-JavaScript browser sends it
    "company": "",          # honeypot, left empty by a real browser
})
status, headers = post(submission)
check(status == 303, f"a real submission is accepted (303, got {status})")
check(headers.get("location") == "/thank-you/?sent=1",
      f"it redirects to /thank-you/?sent=1 (got {headers.get('location')})")

# ── And a bot filling every field, as bots do ────────────────────────────────
bot = dict(submission, email="bot@example.com", company="Acme Pty Ltd")
status, _ = post(bot)
check(status == 303, "the honeypot answers with the same 303 a person gets")

# ── What actually landed ─────────────────────────────────────────────────────
print()
connection = sqlite3.connect(f"file:{work / 'intake.sqlite'}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row
rows = [dict(r) for r in connection.execute("SELECT * FROM enquiries ORDER BY id")]

check(len(rows) == 1, f"only the real submission was stored (found {len(rows)})")
if rows:
    row = rows[0]
    check(row["id"] == 100000, f"the first id is 100000 (got {row['id']})")
    check(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", row["created_at"])),
          f"created_at is the format henley-utils parses (got {row['created_at']!r})")
    check(row["name"] == "Margaret Hale", "the name survived the round trip")
    check(row["email"] == "margaret@example.com", "the email survived the round trip")
    check(row["phone"] == "0400 123 456", "the phone survived the round trip")
    check((row["interest_apartment"], row["interest_aged_care"]) == (1, 0),
          "the ticked interest is 1 and the unticked one is 0")
    check(row["page_path"] == "/luxury-retirement-living/",
          "the page the enquiry came from was recorded")
    check(row["referral_source"] is None,
          "referral_source is null, since the form no longer asks")

# ── The 9-tuple henley-utils will build from this row ────────────────────────
print()
if rows:
    row = rows[0]
    tuple_row = (
        row["id"], row["name"], row["email"], row["phone"], row["enquiry_text"],
        row["created_at"], row["referral_source"],
        "Apartment Living" if row["interest_apartment"] else None,
        "Private Aged Care" if row["interest_aged_care"] else None,
    )
    print(f"  9-tuple for update_salesforce_leads: {tuple_row}")
    check(len(tuple_row) == 9, "the reader can build the 9-tuple its call sites index positionally")
    check(tuple_row[7] == "Apartment Living",
          "interest_type_1 is the string Salesforce's InterestType_c__c expects")

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("enquiry flow: the built form and the receiver agree")
PY
