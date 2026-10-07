"""
The Henley enquiry receiver.

Accepts the website's enquiry form and writes one row to a SQLite file. That is
all it does. It holds no Salesforce credential, no corporate database password
and no session state, so the internet-facing half of the enquiry pipeline has
nothing worth stealing: the nightly henley-utils job opens the same file
read-only and does the classification, the Salesforce upsert and the reception
digest from inside the network.

Bot protection is a honeypot, per-IP and daily caps, and a body-size limit — no
CAPTCHA. The reasoning is in docs/decisions.md; briefly, the live WordPress form
already runs honeypot-only despite having a reCAPTCHA add-on installed, real
volume is a handful a week, the downstream classifier already sorts spam from
six categories, and leaving CAPTCHA out is what lets the form work as a plain
POST with JavaScript disabled.

There was a minimum-fill-time check as well. It compared a timestamp taken from
the visitor's clock against ours, so a device five minutes fast discarded a real
enquiry and answered with the success redirect anyway. See docs/decisions.md.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import logging
import os
import re
import secrets
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from ipaddress import IPv4Network, IPv6Network
from pathlib import Path
from typing import Deque

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Uvicorn configures the `uvicorn.*` loggers and leaves the root logger without
# a handler, so without this nothing below WARNING was ever emitted: a correctly
# configured deployment printed nothing at startup, and so did a badly
# configured one. The line saying which proxies are trusted is exactly the one
# an operator needs to see, and silence is not confirmation.
#
# basicConfig, not a handler of our own: it is a no-op if something has already
# configured the root logger, so it cannot double up under a different runner.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s:     %(message)s",
)

logger = logging.getLogger("henley.forms")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

# ── Configuration ────────────────────────────────────────────────────────────

DB_PATH = Path(os.environ.get("INTAKE_DB_PATH", "/data/intake.sqlite"))
SCHEMA_PATH = Path(os.environ.get("SCHEMA_PATH", Path(__file__).with_name("schema.sql")))

SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://thehenley.com.au")
THANK_YOU_PATH = "/thank-you/?sent=1"

# Set on the redirect for a stored enquiry, and only then. The thank-you page
# is static and cannot know whether the visitor in front of it submitted
# anything: `?sent=1` is in the address of a honeypot hit and of anyone who
# types it, so on its own it counted spam and curiosity as leads. The cookie is
# the receiver saying "this one was stored", it is scoped to that one page, and
# the page deletes it as it reads it. Ten minutes covers a slow redirect, not a
# returning visitor.
#
# Readable by script on purpose (no HttpOnly): the page's script is its only
# consumer. It holds nothing a visitor did not just type, and never in the
# clear — see conversion_marker().
CONVERSION_COOKIE = "henley_enquiry"
CONVERSION_COOKIE_PATH = "/thank-you/"
CONVERSION_COOKIE_MAX_AGE = 600

# Cookies the Google tags on the site set on our own domain, read here from the
# form post so the click that led to an enquiry is stored beside it. No form
# field is involved, so this works with JavaScript off in the form itself.
#   _gcl_aw  the Google Ads click (gclid), written by the Conversion Linker
#   _gcl_gb  the iOS app/web equivalents (gbraid, wbraid)
#   _ga      the Google Analytics client id
CLICK_COOKIES = ("_gcl_aw", "_gcl_gb", "_ga")
CLICK_COOKIE_MAX = 300

# `GCL.<unix time>.<gclid>` is the long-standing shape of _gcl_aw. Google has
# changed cookie formats before, so the raw value is stored as well and this is
# only a convenience: a value that does not match leaves gclid empty, not wrong.
GCLID_RE = re.compile(r"^GCL\.\d+\.([A-Za-z0-9_-]{10,200})$")

CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "07 5591 2111")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "info@thehenley.com.au")

MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", 16 * 1024))
MAX_PER_IP_PER_HOUR = int(os.environ.get("MAX_PER_IP_PER_HOUR", 3))
MAX_PER_DAY = int(os.environ.get("MAX_PER_DAY", 100))

# Only peers inside these networks may be believed about X-Forwarded-For.
# Anyone can send the header; trusting it from an arbitrary peer would make
# every rate limit bypassable by inventing an address per request.
#
# On the live hosts the value is the website Docker network's subnet. The
# receiver publishes no port, so the only peers that can reach it at all are
# containers on that network and the host, through the network's gateway: the
# network is the boundary, not any one address on it. A bare address still
# works and means that one host. It used to be the proxy's address, until the
# 2026-09-27 host reboot had Docker give the proxy a different one and every
# visitor was counted as the proxy, in one rate limit.
#
# This is the only place proxy headers are interpreted. Uvicorn's own
# --proxy-headers rewriting is turned off in the Dockerfile: it runs before this
# and rewrites request.client from a header it was told to trust from anywhere,
# which silently replaced the peer this logic depends on.


def parse_trusted_proxies(value: str) -> list[IPv4Network | IPv6Network]:
    """The networks in a comma-separated TRUSTED_PROXY_IPS value.

    A bare address becomes a network of one host, so every value written before
    networks were accepted still means what it meant.

    An entry that does not parse raises, so the container refuses to start.
    Skipping it would fail closed into the same silent site-wide rate limit a
    stale address produced, and look exactly like a working deployment.
    """
    networks = []
    for entry in (part.strip() for part in value.split(",")):
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            raise ValueError(
                f"TRUSTED_PROXY_IPS entry {entry!r} is not an IP address or network"
            ) from None
    return networks


def describe_network(network: IPv4Network | IPv6Network) -> str:
    """A network as the startup line prints it: one host as its bare address.

    `10.0.0.1`, not `10.0.0.1/32`, so a deployment that configures an address
    reads exactly as it always has.
    """
    if network.prefixlen == network.max_prefixlen:
        return str(network.network_address)
    return str(network)


TRUSTED_PROXY_NETWORKS = parse_trusted_proxies(os.environ.get("TRUSTED_PROXY_IPS", ""))

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


def normalise_ip(value: str) -> str | None:
    """An address in its canonical form, or None if it is not an address.

    Proxies vary in what they write: some append a port, some bracket IPv6, and
    anything at all can arrive in the hops a client made up. Parsing rather than
    trusting means a malformed value is recognised as malformed instead of being
    stored as a rate-limit key nobody can collide with.
    """
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith("["):            # [2001:db8::1]:443
        candidate = candidate[1:].partition("]")[0]
    elif candidate.count(":") == 1:          # 203.0.113.9:443
        candidate = candidate.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


# Untrusted peers already reported for sending X-Forwarded-For. Once each per
# process: a bot flood through a misconfigured proxy is one line, not one per
# request. Only containers on the website network can reach the receiver, so
# this stays a handful of addresses.
_reported_untrusted_peers: set[str] = set()


def client_ip(request: Request) -> str:
    """The visitor's address, believing X-Forwarded-For only from the proxy."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "").strip()

    # A peer that is not an address literal at all is never trusted.
    observed_peer = normalise_ip(peer)
    trusted = observed_peer is not None and any(
        ipaddress.ip_address(observed_peer) in network for network in TRUSTED_PROXY_NETWORKS
    )
    if not trusted:
        # Either a direct connection, or a proxy nobody configured. Its own
        # address is the only thing about it we know first-hand.
        if forwarded and peer not in _reported_untrusted_peers:
            # A proxy nobody configured is also what a proxy whose address
            # drifted looks like, and that is otherwise silent: every visitor
            # just shares one bucket. Name the parsed hop, never the header,
            # which is whatever the client wrote.
            _reported_untrusted_peers.add(peer)
            hop = normalise_ip(forwarded.rsplit(",", 1)[-1])
            logger.warning(
                "untrusted peer %s sent X-Forwarded-For (last hop %s); using the peer",
                peer,
                "malformed" if hop is None else hop,
            )
        return peer

    if not forwarded:
        # No chain to read. The health check and anything else reaching the
        # proxy without one lands here, so it is not worth a warning.
        return peer

    # The proxy appends the peer it saw, so the *last* entry is the one it
    # observed rather than one the client made up. Deliberately the last field,
    # not the last parseable field: a client can put anything before the
    # proxy's entry but cannot put anything after it, so a trailing hop that
    # does not parse means the proxy did not append — and skipping back past it
    # would hand the decision to whatever the client wrote instead.
    observed = normalise_ip(forwarded.rsplit(",", 1)[-1])
    if observed is None:
        logger.warning(
            "trusted proxy %s sent an X-Forwarded-For whose last hop is not an "
            "address; using the peer instead", peer
        )
        return peer
    return observed


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


# ── Conversion measurement ───────────────────────────────────────────────────
#
# What Google Ads is told about an enquiry, and what is kept to tell it more
# later. Reasoning in docs/decisions.md, "Enquiry conversions".


def hashed_email(email: str) -> str | None:
    """SHA-256 of the address as Google normalises it, or None.

    Lower-cased with whitespace removed; for gmail.com and googlemail.com the
    dots in the local part are dropped as well, because Google treats those as
    one mailbox and will not match the hash otherwise.
    """
    address = "".join(email.split()).lower()
    local, at, domain = address.rpartition("@")
    if not at or not local or not domain:
        return None
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.replace(".", "")
    return hashlib.sha256(f"{local}@{domain}".encode()).hexdigest()


def hashed_phone(phone: str | None) -> str | None:
    """SHA-256 of the number in E.164, or None if it cannot be put in E.164.

    People type Australian numbers nationally ("0400 000 000", "07 5591 2111"),
    so a leading 0 becomes +61. Anything that does not come out as a plausible
    international number is left out: a hash of the wrong number matches nobody
    and says nothing went wrong.
    """
    if not phone:
        return None
    international = phone.strip().startswith("+")
    digits = re.sub(r"\D", "", phone)
    if international:
        pass
    elif digits.startswith("0011"):
        digits = digits[4:]
    elif digits.startswith("61") and len(digits) == 11:
        pass
    elif digits.startswith("0") and len(digits) == 10:
        digits = "61" + digits[1:]
    else:
        return None
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        return None
    return hashlib.sha256(f"+{digits}".encode()).hexdigest()


def conversion_marker(reference: str, email: str, phone: str | None) -> str:
    """The cookie value the thank-you page turns into its dataLayer event.

    `v1.<reference>.<email hash>.<phone hash>`, either hash possibly empty. The
    reference is a random token, not the enquiry id: the id is sequential and is
    the Salesforce key, and neither a visitor nor Google has any use for knowing
    how many enquiries there have been.
    """
    return ".".join(("v1", reference, hashed_email(email) or "", hashed_phone(phone) or ""))


def click_cookies(request: Request) -> dict[str, str | None]:
    """The Google click and client cookies that arrived with the form post."""
    found = {
        name: (request.cookies.get(name) or "").strip()[:CLICK_COOKIE_MAX] or None
        for name in CLICK_COOKIES
    }
    match = GCLID_RE.match(found["_gcl_aw"] or "")
    found["gclid"] = match.group(1) if match else None
    return found


# ── Rate limiting ────────────────────────────────────────────────────────────

_recent: dict[str, Deque[float]] = {}
_last_sweep: float = 0.0

# A full sweep is O(addresses seen in the last hour), which is a handful. Doing
# it once an hour rather than once a request keeps it that way even if someone
# points a botnet at the form for an afternoon.
SWEEP_INTERVAL = 3600.0


def _sweep(now: float) -> None:
    """Forget addresses whose window has emptied, whether or not they came back.

    The per-address prune below only runs for the address in front of us, so
    without this a bucket for an address that never returns is never touched
    again — it is not empty, so the "drop empty queues" pass never sees it.
    """
    global _last_sweep
    if now - _last_sweep < SWEEP_INTERVAL:
        return
    _last_sweep = now
    for address in list(_recent):
        window = _recent[address]
        while window and now - window[0] > 3600:
            window.popleft()
        if not window:
            del _recent[address]


def within_ip_limit(ip: str, now: float | None = None) -> bool:
    """At most MAX_PER_IP_PER_HOUR submissions from one address per hour."""
    now = time.time() if now is None else now
    _sweep(now)
    window = _recent.setdefault(ip, deque())
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= MAX_PER_IP_PER_HOUR:
        return False
    window.append(now)
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
    """Test helper: forget every in-memory window, and which peers were reported."""
    global _last_sweep
    _recent.clear()
    _last_sweep = 0.0
    _reported_untrusted_peers.clear()


# ── Responses ────────────────────────────────────────────────────────────────


def accepted(marker: str | None = None) -> RedirectResponse:
    """The success redirect, carrying the conversion marker for a stored enquiry.

    Called without a marker for a honeypot hit: the same redirect, so the form
    still looks as though it worked, and nothing for the page to count.
    """
    # 303, not 302: the browser must follow with GET, so a refresh on the
    # thank-you page cannot resubmit the enquiry.
    response = RedirectResponse(THANK_YOU_PATH, status_code=303)
    if marker:
        response.set_cookie(
            CONVERSION_COOKIE,
            marker,
            max_age=CONVERSION_COOKIE_MAX_AGE,
            path=CONVERSION_COOKIE_PATH,
            secure=True,
            httponly=False,
            samesite="lax",
        )
    return response


def problem(message: str, status: int) -> HTMLResponse:
    """An error page that is still a way to get in touch.

    A visitor who has just typed out an enquiry and been told "something went
    wrong" should not have to go and find the phone number.

    `message` is plain text and is escaped here, at the one boundary where text
    becomes HTML. One of these messages quotes the address the visitor typed
    back at them, and an email field is a text field on the server whatever the
    browser did with it — so an unescaped message is a script element on a page
    we served.
    """
    phone_href = html.escape("tel:" + CONTACT_PHONE.replace(" ", ""), quote=True)
    phone_text = html.escape(CONTACT_PHONE)
    email_href = html.escape("mailto:" + CONTACT_EMAIL, quote=True)
    email_text = html.escape(CONTACT_EMAIL)

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
  <p>{html.escape(message)}</p>
  <div class="contact">
    <p>Please call us on <a href="{phone_href}">{phone_text}</a>
       or email <a href="{email_href}">{email_text}</a> and we will pick it up
       from there.</p>
  </div>
  <p><a href="/contact/">Back to the contact page</a></p>
</main>
</body>
</html>
""",
        status_code=status,
    )


# ── Body limit ───────────────────────────────────────────────────────────────


class LimitBodySize:
    """Refuse an oversized body at the ASGI boundary, before anything parses it.

    Content-Length is a claim, not a measurement — a chunked request carries no
    length at all — so the declared value is only an early shortcut. The real
    check counts the bytes as they arrive and stops at the limit, rather than
    reading the whole body and measuring it afterwards, which is the same as not
    having a limit.

    The budget is the encoded request, not the message someone typed: form
    encoding and non-ASCII characters both cost more bytes than characters.

    It buffers an accepted body — 16 KB, once — and replays it to the
    application, so the endpoint below sees an ordinary request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read per request, so reloading the module or overriding the value in a
        # test applies to the middleware as well as to the endpoint.
        limit = MAX_BODY_BYTES

        declared = _header(scope, b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._refuse(scope, send)
            return

        body = bytearray()
        buffered: list[Message] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Nothing to answer: hand it on so the application unwinds.
                buffered.append(message)
                break
            body += message.get("body", b"")
            if len(body) > limit:
                await self._refuse(scope, send)
                return
            if not message.get("more_body", False):
                buffered.append({"type": "http.request", "body": bytes(body), "more_body": False})
                break

        async def replay() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay, send)

    async def _refuse(self, scope: Scope, send: Send) -> None:
        """One response, and the body still arriving is simply never read."""
        response = problem("That enquiry was too long to send.", status=413)
        await response(scope, _closed, send)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


async def _closed() -> Message:
    """A receive channel for a response that does not read the request."""
    return {"type": "http.disconnect"}


# ── Application ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise()
    if TRUSTED_PROXY_NETWORKS:
        logger.info(
            "X-Forwarded-For is believed from %s",
            ", ".join(sorted(describe_network(network) for network in TRUSTED_PROXY_NETWORKS)),
        )
    else:
        # An empty list is what a missed deployment step looks like, and it looks
        # exactly like a working one: every submission is attributed to the
        # proxy, so the per-IP limit becomes a site-wide limit of three an hour.
        logger.warning(
            "TRUSTED_PROXY_IPS is empty. X-Forwarded-For will be ignored and every "
            "request through a proxy shares one rate-limit bucket. Set it to this "
            "Docker network's subnet (see deploy/.env.example) and recreate this "
            "container."
        )
    yield


app = FastAPI(
    title="The Henley enquiry receiver",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(LimitBodySize)


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
):
    if company.strip():
        # Answer as though it worked. Telling a bot why it failed only helps it.
        logger.info("honeypot triggered from %s", client_ip(request))
        return accepted()

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

    # After the enquiry is safely stored, and never able to undo that: a lead
    # without its attribution is still a lead.
    reference = secrets.token_urlsafe(12)
    clicks = click_cookies(request)
    try:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO enquiry_attribution
                    (enquiry_id, conversion_ref, gclid, gcl_aw, gcl_gb, ga_client)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cursor.lastrowid, reference, clicks["gclid"],
                 clicks["_gcl_aw"], clicks["_gcl_gb"], clicks["_ga"]),
            )
    except sqlite3.Error as error:
        logger.error("could not store attribution for enquiry %s: %s", cursor.lastrowid, error)

    return accepted(conversion_marker(reference, email_value, clean(phone, "phone")))
