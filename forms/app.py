"""
The Henley enquiry receiver.

Accepts the website's enquiry form and writes one row to a SQLite file. That is
all it does. It holds no Salesforce credential, no corporate database password
and no session state, so the internet-facing half of the enquiry pipeline has
nothing worth stealing: the nightly henley-utils job opens the same file
read-only and does the classification, the Salesforce upsert and the reception
digest from inside the network.

Bot protection is a honeypot, a minimum fill time, per-IP and daily caps, and a
body-size limit — no CAPTCHA. The reasoning is in docs/decisions.md; briefly,
the live WordPress form already runs honeypot-only despite having a reCAPTCHA
add-on installed, real volume is a handful a week, the downstream classifier
already sorts spam from six categories, and leaving CAPTCHA out is what lets
the form work as a plain POST with JavaScript disabled.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Deque

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

logger = logging.getLogger("henley.forms")

# ── Configuration ────────────────────────────────────────────────────────────

DB_PATH = Path(os.environ.get("INTAKE_DB_PATH", "/data/intake.sqlite"))
SCHEMA_PATH = Path(os.environ.get("SCHEMA_PATH", Path(__file__).with_name("schema.sql")))

SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://thehenley.com.au")
THANK_YOU_PATH = "/thank-you/?sent=1"

CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "07 5591 2111")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "info@thehenley.com.au")

MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", 16 * 1024))
MAX_PER_IP_PER_HOUR = int(os.environ.get("MAX_PER_IP_PER_HOUR", 3))
MAX_PER_DAY = int(os.environ.get("MAX_PER_DAY", 100))
MIN_FILL_SECONDS = float(os.environ.get("MIN_FILL_SECONDS", 3))

# Only these peers may be believed about X-Forwarded-For. Anyone can send the
# header; trusting it from an arbitrary peer would make every rate limit
# bypassable by inventing an address per request.
TRUSTED_PROXIES = {
    ip.strip() for ip in os.environ.get("TRUSTED_PROXY_IPS", "").split(",") if ip.strip()
}

# Field lengths. Generous for a person, bounded for everyone else.
LIMITS = {
    "name": 120,
    "email": 254,          # RFC 5321 maximum
    "phone": 40,
    "referral_source": 500,
    "enquiry_text": 5000,
    "page_path": 200,
}

# Deliberately loose: this rejects "not an address at all", not "an address
# that will not receive mail". Bouncing a real prospect over a regex that
# dislikes their domain costs far more than accepting one bad address.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

# The exact strings the WordPress form stored, which the classifier reads and
# Salesforce keeps in InterestType_c__c. They are values, not labels: changing
# the wording on the page must not change what is written here.
INTEREST_APARTMENT = "Apartment Living"
INTEREST_AGED_CARE = "Private Aged Care"


# ── Storage ──────────────────────────────────────────────────────────────────


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the intake database for writing, configured for a concurrent reader."""
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    # WAL so the nightly reader never blocks a visitor's submission and vice
    # versa. NORMAL is the right durability for WAL: a crash can lose the last
    # commits only on power loss, and an fsync per enquiry buys nothing here.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialise(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.executescript(SCHEMA_PATH.read_text())
    # The -wal and -shm sidecars are created by the first write and must be
    # readable by the henley-utils reader, which runs as the same host user.
    logger.info("intake database ready at %s", path)


# ── Request helpers ──────────────────────────────────────────────────────────


def client_ip(request: Request) -> str:
    """The visitor's address, believing X-Forwarded-For only from the proxy."""
    peer = request.client.host if request.client else "unknown"
    if peer in TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for", "")
        # The proxy appends the peer it saw, so the last entry is the one it
        # observed rather than one the client made up.
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return peer


def clean(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    trimmed = " ".join(value.split()) if field in {"name", "email", "phone"} else value.strip()
    if not trimmed:
        return None
    return trimmed[: LIMITS.get(field, 1000)]


def checked(value: str | None) -> bool:
    """An HTML checkbox sends its value when ticked and nothing when not."""
    return bool(value) and value.lower() not in {"0", "false", "off", "no"}


# ── Rate limiting ────────────────────────────────────────────────────────────

_recent: dict[str, Deque[float]] = {}


def within_ip_limit(ip: str, now: float | None = None) -> bool:
    """At most MAX_PER_IP_PER_HOUR submissions from one address per hour."""
    now = time.time() if now is None else now
    window = _recent.setdefault(ip, deque())
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= MAX_PER_IP_PER_HOUR:
        return False
    window.append(now)
    # Bound the table: an address with nothing in its window is not remembered.
    for address in [a for a, w in _recent.items() if not w]:
        del _recent[address]
    return True


def within_daily_limit(connection: sqlite3.Connection) -> bool:
    """A ceiling on the whole day, so a distributed flood still stops.

    Counted from the database rather than memory so a restart cannot reset it.
    """
    (count,) = connection.execute(
        "SELECT COUNT(*) FROM enquiries WHERE created_at >= datetime('now', '-1 day')"
    ).fetchone()
    return count < MAX_PER_DAY


def _reset_rate_limits() -> None:
    """Test helper: forget every in-memory window."""
    _recent.clear()


# ── Responses ────────────────────────────────────────────────────────────────


def accepted() -> RedirectResponse:
    # 303, not 302: the browser must follow with GET, so a refresh on the
    # thank-you page cannot resubmit the enquiry.
    return RedirectResponse(THANK_YOU_PATH, status_code=303)


def problem(message: str, status: int) -> HTMLResponse:
    """An error page that is still a way to get in touch.

    A visitor who has just typed out an enquiry and been told "something went
    wrong" should not have to go and find the phone number.
    """
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>We could not send your enquiry — The Henley on Broadwater</title>
<style>
  body {{ margin:0; background:#FAF9F6; color:#1E2427;
         font:400 18px/1.56 "Avenir Next LT Pro", Avenir, Calibri, system-ui, sans-serif; }}
  main {{ max-width:34rem; margin:0 auto; padding:96px 24px; }}
  h1 {{ font-size:30px; line-height:1.2; color:#0E5B70; margin:0 0 24px; }}
  a {{ color:#0E5B70; }}
  .contact {{ margin-top:32px; padding:24px; background:#fff; border-radius:8px; }}
  .contact p {{ margin:0 0 8px; }}
</style>
</head>
<body>
<main>
  <h1>We could not send your enquiry</h1>
  <p>{message}</p>
  <div class="contact">
    <p>Please call us on <a href="tel:{CONTACT_PHONE.replace(' ', '')}">{CONTACT_PHONE}</a>
       or email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> and we will pick it up
       from there.</p>
  </div>
  <p><a href="/contact/">Back to the contact page</a></p>
</main>
</body>
</html>
""",
        status_code=status,
    )


# ── Application ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise()
    yield


app = FastAPI(
    title="The Henley enquiry receiver",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz() -> JSONResponse:
    try:
        with connect() as connection:
            (count,) = connection.execute("SELECT COUNT(*) FROM enquiries").fetchone()
        return JSONResponse({"status": "ok", "enquiries": count})
    except sqlite3.Error as error:
        logger.error("health check failed: %s", error)
        return JSONResponse({"status": "unhealthy"}, status_code=503)


@app.post("/api/enquiry")
async def enquiry(
    request: Request,
    name: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    referral_source: str = Form(default=""),
    enquiry_text: str = Form(default=""),
    interest_apartment: str = Form(default=""),
    interest_aged_care: str = Form(default=""),
    page_path: str = Form(default=""),
    # Named to look like a field worth filling and hidden from people in CSS.
    # A browser leaves it empty; a bot filling every input does not.
    company: str = Form(default=""),
    # Milliseconds since the page loaded, set by JavaScript. Absent when
    # JavaScript is off, in which case the check is skipped rather than
    # failing a legitimate no-JS visitor.
    started_at: str = Form(default=""),
):
    if company.strip():
        # Answer as though it worked. Telling a bot why it failed only helps it.
        logger.info("honeypot triggered from %s", client_ip(request))
        return accepted()

    if started_at.strip():
        try:
            elapsed = (time.time() * 1000 - float(started_at)) / 1000
            if elapsed < MIN_FILL_SECONDS:
                logger.info("submitted in %.1fs from %s", elapsed, client_ip(request))
                return accepted()
        except ValueError:
            pass  # An unparseable value proves nothing either way.

    ip = client_ip(request)
    if not within_ip_limit(ip):
        logger.warning("per-IP limit reached for %s", ip)
        return problem(
            "We have had several enquiries from your connection in the last hour, "
            "so this one was not sent.",
            status=429,
        )

    name_value = clean(name, "name")
    email_value = clean(email, "email")

    if not name_value or not email_value:
        return problem("Please give us your name and email address so we can reply.", status=400)
    if not EMAIL_RE.match(email_value):
        return problem(f"“{email_value}” does not look like an email address.", status=400)

    try:
        with connect() as connection:
            if not within_daily_limit(connection):
                logger.error("daily cap of %s reached; enquiry not stored", MAX_PER_DAY)
                return problem(
                    "We are not able to accept enquiries through the website right now.",
                    status=503,
                )

            cursor = connection.execute(
                """
                INSERT INTO enquiries
                    (name, email, phone, referral_source,
                     interest_apartment, interest_aged_care, enquiry_text,
                     remote_ip, user_agent, page_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name_value,
                    email_value,
                    clean(phone, "phone"),
                    clean(referral_source, "referral_source"),
                    int(checked(interest_apartment)),
                    int(checked(interest_aged_care)),
                    clean(enquiry_text, "enquiry_text"),
                    ip,
                    (request.headers.get("user-agent") or "")[:500] or None,
                    clean(page_path, "page_path"),
                ),
            )
    except sqlite3.Error as error:
        # Log the failure, never the enquiry: it is someone's name, address and
        # reason for calling.
        logger.error("could not store enquiry: %s", error)
        return problem("Something went wrong at our end and your enquiry was not saved.", status=500)

    logger.info("enquiry %s stored from %s", cursor.lastrowid, ip)
    return accepted()


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Refuse oversized bodies before they are parsed."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return problem("That enquiry was too long to send.", status=413)
    return await call_next(request)
