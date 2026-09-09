"""
Tests for the enquiry receiver.

Run: forms/.venv/bin/python -m pytest forms/tests -q

Several of these look like they are testing SQLite rather than our code. They
are not: they pin the three properties henley-utils depends on and that a
plausible-looking change would quietly break — the id floor, the timestamp
format, and a reader being able to see rows while the writer holds the file.
"""

from __future__ import annotations

import importlib
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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


def test_a_submission_faster_than_a_person_is_dropped(receiver):
    client, app_module = receiver
    response = submit(client, started_at=str(time.time() * 1000))

    assert response.status_code == 303
    assert rows(app_module) == []


def test_a_realistic_fill_time_is_accepted(receiver):
    client, app_module = receiver
    started = (time.time() - 45) * 1000
    assert submit(client, started_at=str(started)).status_code == 303
    assert len(rows(app_module)) == 1


def test_no_javascript_means_no_fill_time_check(receiver):
    """With JS off the field is absent; that must not fail a real visitor."""
    client, app_module = receiver
    assert submit(client, started_at="").status_code == 303
    assert len(rows(app_module)) == 1


def test_an_unparseable_fill_time_is_ignored_rather_than_trusted(receiver):
    client, app_module = receiver
    assert submit(client, started_at="not-a-number").status_code == 303
    assert len(rows(app_module)) == 1


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


def test_an_oversized_body_is_refused(receiver):
    client, app_module = receiver
    response = submit(client, enquiry_text="x" * 20_000)

    assert response.status_code == 413
    assert rows(app_module) == []


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


def test_forwarded_for_is_believed_only_from_the_configured_proxy(receiver):
    """Anyone can send the header; trusting it generally makes rate limits moot."""
    client, app_module = receiver

    submit(client, email="a@example.com")
    assert rows(app_module)[0]["remote_ip"] == "testclient"

    monkeypatched = client.post(
        "/api/enquiry",
        data={"name": "B", "email": "b@example.com"},
        headers={"x-forwarded-for": "203.0.113.9"},
        follow_redirects=False,
    )
    assert monkeypatched.status_code == 303
    # TestClient's peer is "testclient", which is not in TRUSTED_PROXY_IPS,
    # so the claimed address is ignored.
    assert rows(app_module)[1]["remote_ip"] == "testclient"


def test_forwarded_for_takes_the_last_hop_from_a_trusted_proxy(receiver, monkeypatch):
    client, app_module = receiver
    monkeypatch.setattr(app_module, "TRUSTED_PROXIES", {"testclient"})

    client.post(
        "/api/enquiry",
        data={"name": "C", "email": "c@example.com"},
        headers={"x-forwarded-for": "198.51.100.7, 203.0.113.9"},
        follow_redirects=False,
    )
    # The proxy appends the peer it actually saw, so the last hop is the
    # trustworthy one; earlier entries are whatever the client claimed.
    assert rows(app_module)[0]["remote_ip"] == "203.0.113.9"


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
