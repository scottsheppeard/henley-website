"""
Tests for the enquiry receiver.

Run: forms/.venv/bin/python -m pytest forms/tests -q

Several of these look like they are testing SQLite rather than our code. They
are not: they pin the three properties henley-utils depends on and that a
plausible-looking change would quietly break — the id floor, the timestamp
format, and a reader being able to see rows while the writer holds the file.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

FORMS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORMS_DIR))


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    """A receiver with its own database, reloaded so module config is re-read."""
    monkeypatch.setenv("INTAKE_DB_PATH", str(tmp_path / "intake.sqlite"))
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.1")
    monkeypatch.setenv("MAX_PER_IP_PER_HOUR", "3")
    monkeypatch.setenv("MAX_PER_DAY", "100")

    import app as app_module

    app_module = importlib.reload(app_module)
    app_module._reset_rate_limits()

    with TestClient(app_module.app) as client:
        yield client, app_module


def submit(client, **overrides):
    payload = {
        "name": "Margaret Hale",
        "email": "margaret@example.com",
        "phone": "0400 000 000",
        "enquiry_text": "I would like to see a two-bedroom apartment.",
        "interest_apartment": "Apartment Living",
        "page_path": "/luxury-retirement-living/",
    }
    payload.update(overrides)
    return client.post("/api/enquiry", data=payload, follow_redirects=False)


def rows(app_module):
    with sqlite3.connect(app_module.DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(r) for r in connection.execute("SELECT * FROM enquiries ORDER BY id")]


def attribution(app_module):
    with sqlite3.connect(app_module.DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(r) for r in connection.execute(
            "SELECT * FROM enquiry_attribution ORDER BY enquiry_id")]


def marker(response):
    """The conversion cookie on a response, as (attributes, value parts)."""
    header = response.headers["set-cookie"]
    value, _, attributes = header.partition(";")
    name, _, value = value.partition("=")
    assert name == "henley_enquiry"
    return attributes, value.strip('"').split(".")


# ── The contract with henley-utils ───────────────────────────────────────────


def test_first_enquiry_gets_id_100000(receiver):
    """A fresh store must not hand back ids henley-utils has already processed.

    Its de-duplication is the full set of ids in data/forms.db (1674..5229),
    not a high-water mark, and the id is Salesforce's WebFormID_c__c external
    key — so a low id is either silently skipped or overwrites a stranger's Lead.
    """
    client, app_module = receiver
    assert submit(client).status_code == 303
    assert submit(client, email="second@example.com").status_code == 303

    stored = rows(app_module)
    assert [r["id"] for r in stored] == [100000, 100001]


def test_ids_are_not_reused_after_deletion(receiver):
    """AUTOINCREMENT, not a bare rowid key: deleting the last row must not free its id."""
    client, app_module = receiver
    submit(client)
    with sqlite3.connect(app_module.DB_PATH) as connection:
        connection.execute("DELETE FROM enquiries")
    submit(client, email="after@example.com")

    assert [r["id"] for r in rows(app_module)] == [100001]


def test_created_at_is_naive_utc_in_the_format_the_reader_parses(receiver):
    """henley-utils' _convert_date_to_brisbane strptimes '%Y-%m-%d %H:%M:%S' as UTC.

    An ISO-8601 string falls through that parser and is passed to Salesforce
    unconverted; SQLite's 'localtime' default would shift every enquiry by the
    ten hours between UTC and Brisbane.
    """
    client, app_module = receiver
    before = datetime.now(timezone.utc)
    submit(client)
    after = datetime.now(timezone.utc)

    created = rows(app_module)[0]["created_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", created), created

    parsed = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    assert before.replace(microsecond=0) <= parsed <= after


def test_the_stored_row_carries_every_field_the_reader_selects(receiver):
    client, app_module = receiver
    submit(client, interest_aged_care="Private Aged Care")

    row = rows(app_module)[0]
    assert row["name"] == "Margaret Hale"
    assert row["email"] == "margaret@example.com"
    assert row["phone"] == "0400 000 000"
    assert row["enquiry_text"] == "I would like to see a two-bedroom apartment."
    assert row["interest_apartment"] == 1
    assert row["interest_aged_care"] == 1
    assert row["page_path"] == "/luxury-retirement-living/"


def test_the_four_field_form_is_a_complete_submission(receiver):
    """The form asks name, email, phone and a message. Nothing else is needed.

    "How did you hear about us?" was dropped for completion rate; this pins that
    its absence is a normal submission rather than a validation failure.
    """
    client, app_module = receiver
    response = client.post(
        "/api/enquiry",
        data={
            "name": "John Thornton",
            "email": "john@example.com",
            "phone": "07 5555 1234",
            "enquiry_text": "Could I arrange a visit for my mother?",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    row = rows(app_module)[0]
    assert row["referral_source"] is None
    assert (row["interest_apartment"], row["interest_aged_care"]) == (0, 0)


def test_referral_source_is_still_stored_if_the_question_ever_returns(receiver):
    """The column outlives the question, so bringing it back needs no migration."""
    client, app_module = receiver
    submit(client, referral_source="A friend who lives there")

    assert rows(app_module)[0]["referral_source"] == "A friend who lives there"


def test_phone_is_optional_but_email_is_not(receiver):
    """Sales rings people, so phone is encouraged — but email is what Salesforce
    matches on first, and is the reply channel that always works."""
    client, app_module = receiver

    assert submit(client, phone="").status_code == 303
    assert rows(app_module)[0]["phone"] is None
    assert submit(client, email="", phone="0400 111 222").status_code == 400


def test_unticked_checkboxes_are_stored_as_zero(receiver):
    """An HTML checkbox sends nothing when unticked; that must not read as true."""
    client, app_module = receiver
    submit(client, interest_apartment="", interest_aged_care="")

    row = rows(app_module)[0]
    assert (row["interest_apartment"], row["interest_aged_care"]) == (0, 0)


def test_a_read_only_reader_sees_rows_while_the_writer_holds_the_file(receiver):
    """The nightly job opens the same file mode=ro while the receiver is running.

    Without WAL, its reads and the receiver's writes would block each other;
    without the -wal sidecar being readable, it would see nothing at all.
    """
    client, app_module = receiver
    submit(client)

    writer = app_module.connect()  # deliberately left open, as the service does
    try:
        uri = f"file:{app_module.DB_PATH}?mode=ro"
        reader = sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            (mode,) = reader.execute("PRAGMA journal_mode").fetchone()
            assert mode.lower() == "wal"
            (count,) = reader.execute("SELECT COUNT(*) FROM enquiries").fetchone()
            assert count == 1

            # And a row written after the reader connected is visible to it.
            submit(client, email="later@example.com")
            (count,) = reader.execute("SELECT COUNT(*) FROM enquiries").fetchone()
            assert count == 2

            with pytest.raises(sqlite3.OperationalError):
                reader.execute("DELETE FROM enquiries")
        finally:
            reader.close()
    finally:
        writer.close()


# ── Bot protection ───────────────────────────────────────────────────────────


def test_honeypot_is_dropped_but_answered_as_success(receiver):
    """Telling a bot why it failed only helps it tune."""
    client, app_module = receiver
    response = submit(client, company="Acme Pty Ltd")

    assert response.status_code == 303
    assert rows(app_module) == []


def test_honeypot_gets_the_redirect_but_nothing_for_the_page_to_count(receiver):
    """The thank-you page counts a lead only when the receiver's cookie arrives.

    A spam-trap hit must look like success and must not be a conversion: counted
    in Google Ads, it teaches the bidding to go and find more of them.
    """
    client, app_module = receiver
    response = submit(client, company="Acme Pty Ltd")

    assert response.headers["location"] == "/thank-you/?sent=1"
    assert "set-cookie" not in response.headers
    assert attribution(app_module) == []


# The minimum-fill-time check is gone. It subtracted the visitor's clock from
# ours, so a device a few minutes fast produced a negative elapsed time, and the
# receiver answered with the success redirect while storing nothing. Whatever it
# caught, it was not worth telling somebody their enquiry had reached us when it
# had not. These tests pin that it cannot come back by accident.


@pytest.mark.parametrize(
    "skew_seconds",
    [300, -300, 86_400, -86_400],
    ids=["five minutes fast", "five minutes slow", "a day fast", "a day slow"],
)
def test_a_wrong_device_clock_cannot_lose_an_enquiry(receiver, skew_seconds):
    client, app_module = receiver
    started = (time.time() + skew_seconds) * 1000

    assert submit(client, email="skewed@example.com", started_at=str(started)).status_code == 303
    assert len(rows(app_module)) == 1


def test_an_instant_submission_is_stored(receiver):
    """Autofill, a password manager and a screen reader all submit fast."""
    client, app_module = receiver
    assert submit(client, started_at=str(time.time() * 1000)).status_code == 303
    assert len(rows(app_module)) == 1


def test_no_javascript_submissions_are_stored(receiver):
    """With JS off the field never existed. It must not have mattered."""
    client, app_module = receiver
    assert submit(client, started_at="").status_code == 303
    assert len(rows(app_module)) == 1


@pytest.mark.parametrize("legacy", ["not-a-number", "-1", "99999999999999999999", ""])
def test_a_legacy_timing_field_from_a_cached_page_is_ignored(receiver, legacy):
    """A browser holding yesterday's HTML still posts started_at. It is inert."""
    client, app_module = receiver
    assert submit(client, started_at=legacy).status_code == 303
    assert len(rows(app_module)) == 1


def test_the_timing_configuration_is_gone_entirely(receiver):
    """Not merely unused: a stray MIN_FILL_SECONDS invites the check back."""
    _, app_module = receiver
    assert not hasattr(app_module, "MIN_FILL_SECONDS")


def test_per_ip_limit_stops_the_fourth_submission_in_an_hour(receiver):
    client, app_module = receiver
    for i in range(3):
        assert submit(client, email=f"person{i}@example.com").status_code == 303

    response = submit(client, email="fourth@example.com")
    assert response.status_code == 429
    assert len(rows(app_module)) == 3
    # The refusal is still a way to get in touch.
    assert "5591 2111" in response.text


def test_daily_cap_refuses_rather_than_silently_dropping(receiver, monkeypatch):
    client, app_module = receiver
    monkeypatch.setattr(app_module, "MAX_PER_DAY", 1)
    monkeypatch.setattr(app_module, "MAX_PER_IP_PER_HOUR", 10)

    assert submit(client).status_code == 303
    response = submit(client, email="second@example.com")

    assert response.status_code == 503
    assert len(rows(app_module)) == 1


# ── The body limit ───────────────────────────────────────────────────────────
#
# Content-Length is a claim, not a measurement. Checking only the declared
# length meant a chunked request — which carries no length at all — was parsed
# and stored however large it was. The limit is now counted on the bytes that
# actually arrive, at the ASGI boundary, before anything parses them.


def form_body(**fields) -> bytes:
    return urlencode(fields).encode()


def post_raw(client, body, *, chunked=False, headers=None):
    """A POST whose body bypasses the test client's form encoding.

    `chunked=True` sends it as an iterator, which is how httpx produces a
    request with no Content-Length — the case the old check could not see.
    """
    sent = (chunk for chunk in [body]) if chunked else body
    return client.post(
        "/api/enquiry",
        content=sent,
        headers={"content-type": "application/x-www-form-urlencoded", **(headers or {})},
        follow_redirects=False,
    )


def test_an_oversized_body_is_refused(receiver):
    client, app_module = receiver
    response = submit(client, enquiry_text="x" * 20_000)

    assert response.status_code == 413
    assert rows(app_module) == []


def test_an_oversized_chunked_body_is_refused_without_a_declared_length(receiver):
    """The reproduction: 20,050 bytes in chunks, no Content-Length, stored anyway."""
    client, app_module = receiver
    body = form_body(name="Bot", email="bot@example.com", enquiry_text="x" * 20_000)
    assert len(body) > app_module.MAX_BODY_BYTES

    response = post_raw(client, body, chunked=True)

    assert response.status_code == 413
    assert rows(app_module) == []


def test_a_body_that_crosses_the_limit_midway_is_refused(receiver):
    """Refused when the running total passes the limit, not after the last chunk."""
    client, app_module = receiver
    limit = app_module.MAX_BODY_BYTES
    body = form_body(name="Bot", email="bot@example.com", enquiry_text="x" * (limit * 4))

    def chunks():
        for start in range(0, len(body), 1024):
            yield body[start : start + 1024]

    response = client.post(
        "/api/enquiry",
        content=chunks(),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    assert response.status_code == 413
    assert rows(app_module) == []


def test_a_body_exactly_at_the_limit_is_accepted(receiver):
    client, app_module = receiver
    limit = app_module.MAX_BODY_BYTES

    padding = "y" * (limit - len(form_body(name="Margaret Hale", email="m@example.com", enquiry_text="")))
    body = form_body(name="Margaret Hale", email="m@example.com", enquiry_text=padding)
    assert len(body) == limit

    response = post_raw(client, body)

    assert response.status_code == 303
    assert len(rows(app_module)) == 1


def test_the_budget_is_encoded_bytes_not_typed_characters(receiver):
    """Percent-encoding and non-ASCII both cost more bytes than characters."""
    client, app_module = receiver
    limit = app_module.MAX_BODY_BYTES

    # Well under the 5,000-character field limit, and over the byte budget:
    # each of these characters is three bytes of UTF-8 and nine of form encoding.
    message = "\u4e2d" * 2_000
    assert len(message) < app_module.LIMITS["enquiry_text"]
    assert len(form_body(name="A", email="a@example.com", enquiry_text=message)) > limit

    response = submit(client, enquiry_text=message)

    assert response.status_code == 413
    assert rows(app_module) == []


def test_normal_non_ascii_enquiries_still_go_through(receiver):
    """The budget must not become a de facto ban on accented names."""
    client, app_module = receiver
    response = submit(client, name="Renée Müller", enquiry_text="Trois chambres, s’il vous plaît.")

    assert response.status_code == 303
    assert rows(app_module)[0]["name"] == "Renée Müller"


def test_a_plain_no_javascript_form_post_is_unaffected(receiver):
    """The ordinary case: a browser form, a declared length, well under the limit."""
    client, app_module = receiver
    response = post_raw(client, form_body(name="John Thornton", email="john@example.com"))

    assert response.status_code == 303
    assert len(rows(app_module)) == 1


def drive(middleware, *, headers, chunks):
    """Run one request straight through the ASGI middleware and collect the reply.

    Below the test client, because the cases worth pinning here are the ones a
    well-behaved HTTP client will not produce: a malformed Content-Length, and a
    disconnect part-way through a body.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/enquiry",
        "raw_path": b"/api/enquiry",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "headers": headers,
        "client": ("198.51.100.7", 51234),
        "server": ("testserver", 80),
    }

    incoming = list(chunks)
    sent = []

    async def receive():
        return incoming.pop(0) if incoming else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


def test_a_malformed_content_length_falls_through_to_counting_real_bytes(receiver):
    """h11 would reject this; the boundary must not depend on that being true."""
    _, app_module = receiver
    limit = app_module.MAX_BODY_BYTES
    reached = []

    async def downstream(scope, receive, send):
        reached.append(True)

    middleware = app_module.LimitBodySize(downstream)
    sent = drive(
        middleware,
        headers=[(b"content-type", b"application/x-www-form-urlencoded"),
                 (b"content-length", b"not-a-number")],
        chunks=[{"type": "http.request", "body": b"z" * (limit + 1), "more_body": False}],
    )

    assert reached == []
    assert sent[0]["status"] == 413
    assert len([m for m in sent if m["type"] == "http.response.start"]) == 1


def test_a_disconnect_part_way_through_a_body_sends_no_second_response(receiver):
    _, app_module = receiver
    seen = []

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            seen.append(message["type"])
            if message["type"] == "http.disconnect":
                return

    middleware = app_module.LimitBodySize(downstream)
    sent = drive(
        middleware,
        headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        chunks=[{"type": "http.request", "body": b"name=A", "more_body": True},
                {"type": "http.disconnect"}],
    )

    assert seen == ["http.disconnect"]
    assert sent == []


def test_an_accepted_body_is_replayed_whole_and_once(receiver):
    _, app_module = receiver
    received = []

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            received.append(message["body"])
            if not message.get("more_body", False):
                return

    middleware = app_module.LimitBodySize(downstream)
    drive(
        middleware,
        headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        chunks=[{"type": "http.request", "body": b"name=Marg", "more_body": True},
                {"type": "http.request", "body": b"aret", "more_body": False}],
    )

    assert received == [b"name=Margaret"]


# ── Validation ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"email": ""},
        {"email": "not-an-address"},
        {"email": "missing@domain"},
    ],
)
def test_an_enquiry_we_could_not_reply_to_is_refused(receiver, overrides):
    client, app_module = receiver
    response = submit(client, **overrides)

    assert response.status_code == 400
    assert rows(app_module) == []
    assert "5591 2111" in response.text


# The error page quotes the address the visitor typed back at them, and an
# email field is a plain text field on the server whatever the browser did with
# it. So every one of these arrived as an actual element on a page we served,
# from our own origin, at 400.

# Everything problem() writes itself. Anything else in a rendered response came
# from a value, which is the whole failure.
TEMPLATE_ELEMENTS = {
    "html", "head", "meta", "title", "style", "body", "main", "h1", "p", "div", "a",
}


def markup(page: str) -> tuple[set[str], set[str]]:
    """The elements and attribute names a browser would actually find."""

    class Collector(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.elements: set[str] = set()
            self.attributes: set[str] = set()

        def handle_starttag(self, tag, attrs):
            self.elements.add(tag)
            self.attributes.update(name.lower() for name, _ in attrs)

        handle_startendtag = handle_starttag

    collector = Collector()
    collector.feed(page)
    collector.close()
    return collector.elements, collector.attributes



@pytest.mark.parametrize(
    "hostile",
    [
        "<script>window.__henleyReview=1</script>",
        '"><script>alert(1)</script>',
        "<img src=x onerror=alert(1)>",
        "\'onmouseover=\'alert(1)",
        "<svg/onload=alert(1)>",
        "a&b<c>d\"e\'f@example",
    ],
)
def test_an_invalid_address_is_shown_as_text_not_rendered_as_markup(receiver, hostile):
    client, app_module = receiver
    response = submit(client, email=hostile)

    assert response.status_code == 400
    assert rows(app_module) == []

    # Parsed, not string-matched: the escaped text legitimately *contains*
    # "onerror=" as characters. What matters is that no element and no
    # attribute came into existence, which only a parser can tell you.
    elements, attributes = markup(response.text)

    assert elements <= TEMPLATE_ELEMENTS, f"the value created {elements - TEMPLATE_ELEMENTS}"
    assert not [name for name in attributes if name.startswith("on")]
    # And it is still shown, escaped, so the visitor can see what was rejected.
    assert "does not look like an email address" in response.text
    assert hostile not in response.text


def test_the_error_page_is_still_a_way_to_get_in_touch(receiver):
    """Escaping must not cost the visitor the phone number and the email link."""
    client, _ = receiver
    response = submit(client, email="<script>x</script>")

    assert response.status_code == 400
    assert '<a href="tel:0755912111">07 5591 2111</a>' in response.text
    assert '<a href="mailto:info@thehenley.com.au">info@thehenley.com.au</a>' in response.text
    assert '<meta name="robots" content="noindex">' in response.text


def test_configured_contact_details_are_escaped_too(receiver, monkeypatch):
    """They are environment values, and the template is the wrong place to trust."""
    client, app_module = receiver
    monkeypatch.setattr(app_module, "CONTACT_EMAIL", 'x" onclick="alert(1)')
    monkeypatch.setattr(app_module, "CONTACT_PHONE", '07 <b>5591</b> 2111')

    response = submit(client, email="")

    assert response.status_code == 400
    assert 'onclick="alert(1)"' not in response.text
    assert "<b>" not in response.text


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"email": "<script>x</script>"}, 400),
        ({"name": ""}, 400),
        ({"enquiry_text": "x" * 20_000}, 413),
    ],
)
def test_escaping_did_not_change_any_status_code(receiver, overrides, status):
    client, _ = receiver
    assert submit(client, **overrides).status_code == status


def test_the_hostile_value_is_not_written_to_the_log(receiver, caplog):
    """A rejected enquiry is still somebody's typing. It does not go in the log."""
    client, _ = receiver
    with caplog.at_level("DEBUG", logger="henley.forms"):
        submit(client, email="<script>window.__henleyReview=1</script>")

    assert "__henleyReview" not in caplog.text


def test_long_fields_are_truncated_not_rejected(receiver):
    """A visitor who pastes an essay should not lose their enquiry over it."""
    client, app_module = receiver
    submit(client, enquiry_text="y" * 4_000, name="N" * 300)

    row = rows(app_module)[0]
    assert len(row["name"]) == app_module.LIMITS["name"]
    assert len(row["enquiry_text"]) == 4_000


def test_optional_fields_left_blank_are_stored_as_null(receiver):
    client, app_module = receiver
    submit(client, phone="", enquiry_text="")

    row = rows(app_module)[0]
    assert row["phone"] is None
    assert row["referral_source"] is None
    assert row["enquiry_text"] is None


# ── Proxy handling ───────────────────────────────────────────────────────────
#
# Two mechanisms used to decide who the visitor was. Uvicorn ran with
# --proxy-headers --forwarded-allow-ips '*' and rewrote request.client from a
# header anybody could send, before the logic below ever saw the real peer. So
# four submissions carrying four invented first hops counted as four different
# visitors, and the per-IP limit was decoration. The receiver owns the decision
# now, and the Dockerfile says --no-proxy-headers.


def client_from(app, host):
    """A test client whose connection comes from `host`, as a container's would."""
    return TestClient(app, client=(host, 50000))


@pytest.fixture
def behind_proxy(receiver):
    """The receiver reached through the trusted proxy, as NPM reaches it in production.

    A real peer address — the one the `receiver` fixture trusts — not a name
    patched into the trusted set, so it goes through the same parsing and the
    same check a deployed request does.
    """
    _, app_module = receiver
    with client_from(app_module.app, "10.0.0.1") as client:
        yield client, app_module


def trusting(monkeypatch, value):
    """The receiver module reloaded with TRUSTED_PROXY_IPS set to `value`."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", value)
    import app as app_module

    return importlib.reload(app_module)


def test_forwarded_for_is_believed_only_from_the_configured_proxy(receiver, caplog):
    """Anyone can send the header; trusting it generally makes rate limits moot."""
    client, app_module = receiver

    submit(client, email="a@example.com")
    assert rows(app_module)[0]["remote_ip"] == "testclient"

    with caplog.at_level("INFO", logger="henley.forms"):
        monkeypatched = client.post(
            "/api/enquiry",
            data={"name": "B", "email": "b@example.com"},
            headers={"x-forwarded-for": "203.0.113.9"},
            follow_redirects=False,
        )
    assert monkeypatched.status_code == 303
    # TestClient's peer is "testclient", which is not an address at all and so
    # never trusted: the claimed address is ignored.
    assert rows(app_module)[1]["remote_ip"] == "testclient"

    # And it says so. The header's value is in that line only, as the parsed hop.
    assert (
        "untrusted peer testclient sent X-Forwarded-For (last hop 203.0.113.9); using the peer"
        in caplog.messages
    )
    assert caplog.text.count("203.0.113.9") == 1


def test_forwarded_for_takes_the_last_hop_from_a_trusted_proxy(behind_proxy):
    client, app_module = behind_proxy

    client.post(
        "/api/enquiry",
        data={"name": "C", "email": "c@example.com"},
        headers={"x-forwarded-for": "198.51.100.7, 203.0.113.9"},
        follow_redirects=False,
    )
    # The proxy appends the peer it actually saw, so the last hop is the
    # trustworthy one; earlier entries are whatever the client claimed.
    assert rows(app_module)[0]["remote_ip"] == "203.0.113.9"


def test_a_spoofed_leading_hop_cannot_change_the_stored_address(behind_proxy):
    """The reproduction: four submissions, four invented first hops, one visitor."""
    client, app_module = behind_proxy

    spoofed = ["10.1.1.1", "10.2.2.2", "10.3.3.3", "10.4.4.4"]
    statuses = [
        client.post(
            "/api/enquiry",
            data={"name": "D", "email": f"d{i}@example.com"},
            headers={"x-forwarded-for": f"{claim}, 203.0.113.9"},
            follow_redirects=False,
        ).status_code
        for i, claim in enumerate(spoofed)
    ]

    assert statuses == [303, 303, 303, 429]
    stored = rows(app_module)
    assert len(stored) == 3
    assert {row["remote_ip"] for row in stored} == {"203.0.113.9"}


def test_independent_visitors_behind_the_proxy_are_counted_independently(behind_proxy):
    client, app_module = behind_proxy

    for i in range(3):
        response = client.post(
            "/api/enquiry",
            data={"name": "E", "email": f"e{i}@example.com"},
            headers={"x-forwarded-for": "203.0.113.9"},
            follow_redirects=False,
        )
        assert response.status_code == 303

    other = client.post(
        "/api/enquiry",
        data={"name": "F", "email": "f@example.com"},
        headers={"x-forwarded-for": "198.51.100.20"},
        follow_redirects=False,
    )

    assert other.status_code == 303
    assert rows(app_module)[3]["remote_ip"] == "198.51.100.20"


def test_an_untrusted_peer_cannot_choose_its_own_rate_limit_bucket(receiver):
    """Without this, three submissions is three per invented address, forever."""
    client, app_module = receiver

    statuses = [
        client.post(
            "/api/enquiry",
            data={"name": "G", "email": f"g{i}@example.com"},
            headers={"x-forwarded-for": f"10.9.9.{i}"},
            follow_redirects=False,
        ).status_code
        for i in range(4)
    ]

    assert statuses == [303, 303, 303, 429]
    assert {row["remote_ip"] for row in rows(app_module)} == {"testclient"}


def test_an_untrusted_peer_sending_the_header_is_reported_once(receiver, caplog):
    """What a proxy whose address drifted looks like, said once rather than per request.

    From 27 September every visitor arrived through a peer the receiver no
    longer trusted, and nothing said so. One line per peer is enough to notice;
    one per request would be a bot flood written into the log.
    """
    client, _ = receiver

    with caplog.at_level("INFO", logger="henley.forms"):
        statuses = [
            client.post(
                "/api/enquiry",
                data={"name": "M", "email": f"m{i}@example.com"},
                headers={"x-forwarded-for": "198.51.100.7, 203.0.113.9:44321"},
                follow_redirects=False,
            ).status_code
            for i in range(3)
        ]

    assert statuses == [303, 303, 303]
    reported = [message for message in caplog.messages if "sent X-Forwarded-For" in message]
    assert reported == [
        "untrusted peer testclient sent X-Forwarded-For (last hop 203.0.113.9); using the peer"
    ]
    # The parsed hop, not the header: neither the client's claim nor the port.
    assert "198.51.100.7" not in caplog.text
    assert "44321" not in caplog.text


def test_a_malformed_last_hop_is_reported_without_repeating_it(receiver, caplog):
    """The header is whatever the client wrote, so none of it is copied into the log."""
    client, _ = receiver

    with caplog.at_level("INFO", logger="henley.forms"):
        response = client.post(
            "/api/enquiry",
            data={"name": "N", "email": "n@example.com"},
            headers={"x-forwarded-for": "203.0.113.9, not-an-ip"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert (
        "untrusted peer testclient sent X-Forwarded-For (last hop malformed); using the peer"
        in caplog.messages
    )
    assert "not-an-ip" not in caplog.text


@pytest.mark.parametrize(
    "header",
    ["not-an-address", "203.0.113.9, ", "203.0.113.9, banana", "   ", "; DROP TABLE enquiries"],
)
def test_a_malformed_forwarded_header_falls_back_to_the_peer(behind_proxy, header):
    """The documented fallback. Never the client's value, never a stored non-address."""
    client, app_module = behind_proxy

    response = client.post(
        "/api/enquiry",
        data={"name": "H", "email": "h@example.com"},
        headers={"x-forwarded-for": header},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert rows(app_module)[0]["remote_ip"] == "10.0.0.1"


@pytest.mark.parametrize(
    ("sent", "stored"),
    [
        ("203.0.113.9:44321", "203.0.113.9"),
        ("[2001:db8::1]:44321", "2001:db8::1"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        (" 203.0.113.9 ", "203.0.113.9"),
    ],
)
def test_addresses_are_normalised_so_one_visitor_is_one_bucket(behind_proxy, sent, stored):
    client, app_module = behind_proxy

    client.post(
        "/api/enquiry",
        data={"name": "I", "email": "i@example.com"},
        headers={"x-forwarded-for": f"10.0.0.5, {sent}"},
        follow_redirects=False,
    )

    assert rows(app_module)[0]["remote_ip"] == stored


def test_a_network_entry_trusts_every_peer_inside_it_and_no_other(receiver, monkeypatch):
    """The deployed value is the website network's subnet, not the proxy's address.

    Docker hands out addresses on that network in start order, so a reboot can
    move the proxy to another one. The subnet stays where it is.
    """
    app_module = trusting(monkeypatch, "10.0.0.0/24")

    for peer in ("10.0.0.77", "10.0.1.77"):
        with client_from(app_module.app, peer) as client:
            response = client.post(
                "/api/enquiry",
                data={"name": "K", "email": "k@example.com"},
                headers={"x-forwarded-for": "203.0.113.9"},
                follow_redirects=False,
            )
        assert response.status_code == 303

    assert [row["remote_ip"] for row in rows(app_module)] == ["203.0.113.9", "10.0.1.77"]


def test_ipv6_addresses_and_networks_are_accepted_too(receiver, monkeypatch):
    """A dual-stack network would hand the proxy an IPv6 peer address."""
    app_module = trusting(monkeypatch, "2001:db8::1, 2001:db8::/32")
    assert app_module.TRUSTED_PROXY_NETWORKS == [
        ip_network("2001:db8::1/128"),
        ip_network("2001:db8::/32"),
    ]

    with client_from(app_module.app, "2001:db8::9") as client:
        client.post(
            "/api/enquiry",
            data={"name": "L", "email": "l@example.com"},
            headers={"x-forwarded-for": "203.0.113.9"},
            follow_redirects=False,
        )

    # Not the single host, so it is the network entry that trusted this peer.
    assert rows(app_module)[0]["remote_ip"] == "203.0.113.9"


@pytest.mark.parametrize(
    ("configured", "networks", "line"),
    [
        # A bare address, as every deployment before networks wrote it: a
        # network of one host, printed exactly as the old line printed it.
        ("10.0.0.1", [ip_network("10.0.0.1/32")], "X-Forwarded-For is believed from 10.0.0.1"),
        (
            "192.168.176.0/20,10.0.0.1",
            [ip_network("192.168.176.0/20"), ip_network("10.0.0.1/32")],
            "X-Forwarded-For is believed from 10.0.0.1, 192.168.176.0/20",
        ),
    ],
    ids=["a bare address", "a network and an address"],
)
def test_startup_says_out_loud_which_proxies_it_believes(
    receiver, monkeypatch, caplog, configured, networks, line
):
    """Silence is not confirmation.

    Uvicorn configures its own loggers and leaves the root one without a
    handler, so this module's INFO went nowhere at all: a correct deployment
    printed nothing at startup, and so did a broken one. `docker logs … | head`
    is the documented check, and it has to have something to read.
    """
    app_module = trusting(monkeypatch, configured)
    assert app_module.TRUSTED_PROXY_NETWORKS == networks

    with caplog.at_level("INFO", logger="henley.forms"):
        with TestClient(app_module.app):
            pass

    assert line in caplog.messages
    assert app_module.logger.getEffectiveLevel() <= 20, "INFO would be dropped"


def test_an_empty_trusted_proxy_list_is_a_warning_not_a_default(tmp_path, monkeypatch, caplog):
    """It is what a missed deployment step looks like, and it looks like success.

    It is also what the documented compose command actually produced: Compose
    reads `.env` from the directory it runs in, not from deploy/, so
    TRUSTED_PROXY_IPS arrived empty and nothing about the deployment looked
    wrong. See deploy/.env.example.
    """
    monkeypatch.setenv("INTAKE_DB_PATH", str(tmp_path / "intake.sqlite"))
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "")

    import app as app_module

    reloaded = importlib.reload(app_module)
    with caplog.at_level("WARNING", logger="henley.forms"):
        with TestClient(reloaded.app):
            pass

    assert reloaded.TRUSTED_PROXY_NETWORKS == []
    assert "TRUSTED_PROXY_IPS is empty" in caplog.text
    # The subnet, not the proxy's address: that address is what a reboot moved.
    assert (
        "Set it to this Docker network's subnet (see deploy/.env.example) and "
        "recreate this container." in caplog.text
    )


def test_an_entry_that_is_not_an_address_stops_the_receiver_starting(tmp_path, monkeypatch):
    """A container that will not start is noticed; a skipped entry is not.

    Ignoring the entry would fail closed into the same silent site-wide limit
    a stale proxy address produced, and look exactly like a working deployment.
    """
    monkeypatch.setenv("INTAKE_DB_PATH", str(tmp_path / "intake.sqlite"))
    message = "TRUSTED_PROXY_IPS entry 'not-an-address' is not an IP address or network"
    try:
        with pytest.raises(ValueError, match=re.escape(message)):
            trusting(monkeypatch, "not-an-address")
    finally:
        # The failed reload left the module half-run; later tests import it.
        trusting(monkeypatch, "10.0.0.1")


def test_the_container_does_not_let_uvicorn_rewrite_the_client_address(receiver):
    """The defect was in the Docker command, which no in-process test exercised.

    So this one reads it. --proxy-headers with --forwarded-allow-ips '*' is the
    exact configuration that made every check above meaningless in production
    while all of them passed here.
    """
    dockerfile = (FORMS_DIR / "Dockerfile").read_text()
    command = [line for line in dockerfile.splitlines() if "uvicorn" in line and "CMD" in line]
    assert command, "no uvicorn CMD found in forms/Dockerfile"

    start = dockerfile.index("CMD [")
    cmd = dockerfile[start : dockerfile.index("]", start)]
    assert "--no-proxy-headers" in cmd
    assert "--forwarded-allow-ips" not in cmd
    assert '"--proxy-headers"' not in cmd


def test_uvicorns_rewriting_is_what_made_spoofing_work(receiver):
    """Why the flag matters, pinned rather than described.

    This wraps the app in the middleware the old Docker command turned on. It
    asserts the broken behaviour on purpose: if someone puts --proxy-headers
    back, this is what they get, and the assertion above is what stops them.
    """
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    _, app_module = receiver

    # Reached from the trusted proxy's address, as in production: the middleware
    # replaces that peer with the first hop before the receiver ever sees it.
    rewriting = ProxyHeadersMiddleware(app_module.app, trusted_hosts="*")
    with client_from(rewriting, "10.0.0.1") as proxied:
        for i, claim in enumerate(["10.1.1.1", "10.2.2.2", "10.3.3.3", "10.4.4.4"]):
            response = proxied.post(
                "/api/enquiry",
                data={"name": "J", "email": f"j{i}@example.com"},
                headers={"x-forwarded-for": f"{claim}, 203.0.113.9"},
                follow_redirects=False,
            )
            assert response.status_code == 303, "all four accepted: the limit is bypassed"

    assert [row["remote_ip"] for row in rows(app_module)] == [
        "10.1.1.1", "10.2.2.2", "10.3.3.3", "10.4.4.4",
    ]


# ── Rate-limit bookkeeping ───────────────────────────────────────────────────


def test_an_address_that_never_returns_is_eventually_forgotten(receiver):
    """The table only pruned the address in front of it, so quiet ones stayed.

    Its "drop empty queues" pass could not help: a queue nobody touches never
    becomes empty. Simulated time, so the test is deterministic.
    """
    _, app_module = receiver

    assert app_module.within_ip_limit("203.0.113.1", now=0.0)
    assert "203.0.113.1" in app_module._recent

    assert app_module.within_ip_limit("203.0.113.2", now=7200.0)

    assert "203.0.113.1" not in app_module._recent
    assert "203.0.113.2" in app_module._recent


def test_expiry_keeps_the_windows_that_are_still_open(receiver):
    """A sweep that forgets an active visitor hands them a fresh three an hour."""
    _, app_module = receiver

    for offset in (0.0, 1.0, 2.0):
        assert app_module.within_ip_limit("203.0.113.3", now=7200.0 + offset)

    # Force the next call to sweep, while that visitor's hour is still running.
    app_module._last_sweep = 0.0
    assert app_module.within_ip_limit("203.0.113.9", now=7203.0)

    assert len(app_module._recent["203.0.113.3"]) == 3
    assert app_module.within_ip_limit("203.0.113.3", now=7204.0) is False


def test_expiry_does_not_walk_every_address_ever_seen_on_every_request(receiver):
    """Bounded work per request: a full pass at most once an interval.

    A sweep that ran on every submission would be O(every address seen in the
    last hour) per request — the wrong shape for the one code path an outsider
    can call as often as they like.
    """
    _, app_module = receiver

    for second in range(200):
        app_module.within_ip_limit(f"198.51.100.{second}", now=float(second))

    assert app_module._last_sweep == 0.0, "swept during a burst inside one interval"
    assert len(app_module._recent) == 200

    # And the first request past the interval collects all 200 at once.
    app_module.within_ip_limit("203.0.113.50", now=4000.0)
    assert app_module._last_sweep == 4000.0
    assert list(app_module._recent) == ["203.0.113.50"]


# ── Success path and health ──────────────────────────────────────────────────


def test_success_redirects_with_303_so_a_refresh_cannot_resubmit(receiver):
    client, _ = receiver
    response = submit(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/thank-you/?sent=1"


def test_a_storage_failure_gives_the_visitor_a_way_to_reach_us(receiver, monkeypatch):
    client, app_module = receiver

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(app_module, "connect", broken)
    response = submit(client)

    assert response.status_code == 500
    assert "5591 2111" in response.text
    assert "info@thehenley.com.au" in response.text


def test_healthz_reports_the_row_count(receiver):
    client, _ = receiver
    submit(client)

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "enquiries": 1}


def test_the_service_exposes_no_api_documentation(receiver):
    """Nothing on the public receiver should describe its own surface."""
    client, _ = receiver
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# ── Conversion measurement ───────────────────────────────────────────────────


def test_a_stored_enquiry_sets_the_marker_the_thank_you_page_counts(receiver):
    client, app_module = receiver
    response = submit(client, email="Margaret@Example.com ", phone="0400 000 000")

    attributes, parts = marker(response)
    stored = attribution(app_module)[0]

    assert parts[0] == "v1"
    assert parts[1] == stored["conversion_ref"]
    assert stored["enquiry_id"] == rows(app_module)[0]["id"]
    assert parts[2] == hashlib.sha256(b"margaret@example.com").hexdigest()
    assert parts[3] == hashlib.sha256(b"+61400000000").hexdigest()


def test_the_marker_is_short_lived_scoped_to_the_page_and_readable_by_it(receiver):
    client, _ = receiver
    attributes, _ = marker(submit(client))
    attributes = attributes.lower()

    assert "max-age=600" in attributes
    assert "path=/thank-you/" in attributes
    assert "secure" in attributes
    assert "samesite=lax" in attributes
    # The page's script is the only consumer, so it has to be able to read it.
    assert "httponly" not in attributes


def test_the_marker_never_carries_what_the_visitor_typed(receiver):
    client, _ = receiver
    response = submit(client, name="Margaret Hale", email="margaret@example.com",
                      phone="0400 000 000")

    header = response.headers["set-cookie"].lower()
    for typed in ("margaret", "example.com", "0400", "61400000000", "100000"):
        assert typed not in header


def test_the_reference_is_random_not_the_enquiry_id(receiver):
    """The id is sequential and is the Salesforce key; neither belongs with Google."""
    client, app_module = receiver
    references = [marker(submit(client, email=f"m{n}@example.com"))[1][1] for n in range(3)]

    assert len(set(references)) == 3
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{16}", r) for r in references)
    assert [a["conversion_ref"] for a in attribution(app_module)] == references


@pytest.mark.parametrize("typed, e164", [
    ("0400 000 000", "+61400000000"),
    ("(07) 5591 2111", "+61755912111"),
    ("+61 400 000 000", "+61400000000"),
    ("61400000000", "+61400000000"),
    ("0011 44 20 7946 0958", "+442079460958"),
    ("+44 20 7946 0958", "+442079460958"),
    ("+61 (0)400 000 000", "+61400000000"),
    ("+61 0400 000 000", "+61400000000"),
    ("+61 (07) 5591 2111", "+61755912111"),
    ("+44 (0)20 7946 0958", "+442079460958"),
    ("07-5591.2111", "+61755912111"),
])
def test_phone_numbers_are_hashed_in_e164(receiver, typed, e164):
    _, app_module = receiver
    assert app_module.hashed_phone(typed) == hashlib.sha256(e164.encode()).hexdigest()


@pytest.mark.parametrize("typed", [
    None, "", "call me", "5591 2111", "12345", "0" * 20,
    "+61 400 000 000 x2",          # an extension is not part of the number
    "0400 000 000 after 5pm",
    "+\u0666\u0661\u0664\u0660\u0660\u0660\u0660\u0660\u0660\u0660\u0660",  # not ASCII digits
    "0500 000 000",                # not an Australian area or mobile prefix
    "+61 400 000 00",              # an Australian number is nine digits after 61
])
def test_a_number_that_cannot_be_put_in_e164_is_left_out(receiver, typed):
    """A hash of the wrong number matches nobody and looks like success."""
    _, app_module = receiver
    assert app_module.hashed_phone(typed) is None


def test_an_enquiry_without_a_usable_phone_still_gets_its_email_hash(receiver):
    client, _ = receiver
    _, parts = marker(submit(client, phone="after 5pm please"))

    assert len(parts) == 4
    assert re.fullmatch(r"[0-9a-f]{64}", parts[2])
    assert parts[3] == ""


@pytest.mark.parametrize("typed, normalised", [
    ("  Margaret@Example.COM ", "margaret@example.com"),
    ("m.hale@gmail.com", "mhale@gmail.com"),
    ("M.Hale@GoogleMail.com", "mhale@googlemail.com"),
    ("m.hale@example.com", "m.hale@example.com"),
])
def test_email_is_hashed_as_google_normalises_it(receiver, typed, normalised):
    _, app_module = receiver
    assert app_module.hashed_email(typed) == hashlib.sha256(normalised.encode()).hexdigest()


def test_the_google_click_is_stored_beside_the_enquiry(receiver):
    """Read from the cookies the Google tags set, so the form needs no field for it."""
    client, app_module = receiver
    client.cookies.set("_gcl_aw", "GCL.1790000000.Cj0KCQjw-test_GCLID123")
    client.cookies.set("_gcl_gb", "GCL.1790000000.0AAAAAtestGBRAID")
    client.cookies.set("_ga", "GA1.1.1234567890.1790000000")
    submit(client)

    stored = attribution(app_module)[0]
    assert stored["gclid"] == "Cj0KCQjw-test_GCLID123"
    assert stored["gcl_aw"] == "GCL.1790000000.Cj0KCQjw-test_GCLID123"
    assert stored["gcl_gb"] == "GCL.1790000000.0AAAAAtestGBRAID"
    assert stored["ga_client"] == "GA1.1.1234567890.1790000000"


def test_an_enquiry_with_no_google_cookies_is_stored_all_the_same(receiver):
    client, app_module = receiver
    assert submit(client).status_code == 303

    stored = attribution(app_module)[0]
    assert (stored["gclid"], stored["gcl_aw"], stored["gcl_gb"], stored["ga_client"]) == (None,) * 4


def test_a_click_cookie_in_a_shape_we_do_not_know_is_kept_raw_and_not_guessed(receiver):
    client, app_module = receiver
    client.cookies.set("_gcl_aw", "2.1.k1$i1790000000$u12345")
    submit(client)

    stored = attribution(app_module)[0]
    assert stored["gcl_aw"] == "2.1.k1$i1790000000$u12345"
    assert stored["gclid"] is None


def test_an_oversized_click_cookie_is_truncated(receiver):
    client, app_module = receiver
    client.cookies.set("_ga", "x" * 2000)
    submit(client)

    assert len(attribution(app_module)[0]["ga_client"]) == 300


def test_attribution_failing_never_costs_the_enquiry_or_the_conversion(receiver):
    """A lead without its attribution is still a lead, and still a conversion."""
    client, app_module = receiver
    with sqlite3.connect(app_module.DB_PATH) as connection:
        connection.execute("DROP TABLE enquiry_attribution")

    response = submit(client)

    assert response.status_code == 303
    assert len(rows(app_module)) == 1
    assert marker(response)[1][0] == "v1"


def test_the_attribution_table_appears_in_a_store_that_already_has_enquiries(receiver):
    """The live stores predate this table; starting the receiver must add it."""
    client, app_module = receiver
    submit(client)
    with sqlite3.connect(app_module.DB_PATH) as connection:
        connection.execute("DROP TABLE enquiry_attribution")

    app_module.initialise()
    submit(client, email="second@example.com")

    assert [r["id"] for r in rows(app_module)] == [100000, 100001]
    assert [a["enquiry_id"] for a in attribution(app_module)] == [100001]


def test_the_enquiries_table_keeps_the_shape_henley_utils_reads(receiver):
    """Attribution lives in its own table precisely so this one does not change."""
    _, app_module = receiver
    with sqlite3.connect(app_module.DB_PATH) as connection:
        columns = [r[1] for r in connection.execute("PRAGMA table_info(enquiries)")]

    assert columns == ["id", "created_at", "name", "email", "phone", "referral_source",
                       "interest_apartment", "interest_aged_care", "enquiry_text",
                       "remote_ip", "user_agent", "page_path"]


def test_deleting_a_test_enquiry_takes_its_attribution_with_it(receiver):
    """Through the receiver's own connection, which turns foreign keys on.

    The sqlite3 command line does not, so a delete by hand has to remove the
    attribution row itself; schema.sql says so.
    """
    client, app_module = receiver
    submit(client)
    with app_module.connect() as connection:
        connection.execute("DELETE FROM enquiries")

    assert attribution(app_module) == []
