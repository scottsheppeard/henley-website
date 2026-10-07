# Enquiry receiver

The internet-facing half of the enquiry pipeline. It accepts the website's
contact form and writes one row to a SQLite file. That is the whole job.

Everything that needs a credential happens elsewhere: the nightly henley-utils
job opens the same file read-only from inside the network and does the spam
classification, the Salesforce upsert and the reception digest. So this service
holds no Salesforce token, no corporate database password and no session state,
and there is nothing in the container worth stealing.

## Running it

```bash
# tests
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q

# locally
INTAKE_DB_PATH=/tmp/intake.sqlite .venv/bin/uvicorn app:app --reload
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `INTAKE_DB_PATH` | `/data/intake.sqlite` | The bind-mounted store. henley-utils reads this same path read-only. |
| `TRUSTED_PROXY_IPS` | *(empty)* | Comma-separated addresses or CIDR networks. `X-Forwarded-For` is believed **only** from peers inside them — anyone can send the header, and trusting it generally would make every rate limit bypassable by inventing an address per request. The deployed value is **this site's Docker network's subnet** (`deploy/.env.example`), not NPM's address: the receiver publishes no port, so only containers on that network (and the host, through its gateway) can reach it, and the subnet survives the reboots and NPM recreations that move individual addresses. The accepted cost is that any container on the network that reaches the receiver directly, or the host through the gateway, may assert a visitor address — today NPM and the static site's nginx ([docs/decisions.md](../docs/decisions.md), 2026-10-06). An entry that is neither an address nor a network stops the receiver starting. Empty is logged as a warning at startup, because an unset value looks exactly like a working deployment. |
| `MAX_PER_IP_PER_HOUR` | `3` | |
| `MAX_PER_DAY` | `100` | Counted from the database, so a restart cannot reset it. |
| `MAX_BODY_BYTES` | `16384` | Counted on the bytes actually received, not on `Content-Length`. It is a budget for the *encoded* request: form encoding and non-ASCII both cost more bytes than characters. |
| `CONTACT_PHONE`, `CONTACT_EMAIL` | site values | Shown on the error page, so a failed submission is still a way to get in touch. |

## Endpoints

- `POST /api/enquiry` — form-encoded. 303 to `/thank-you/?sent=1` on success,
  which for a legitimate submission means the row is stored.
  A stored enquiry's redirect also sets the `henley_enquiry` cookie, which is
  what the thank-you page counts as a conversion, and writes the Google click
  cookies that came with the post to `enquiry_attribution`. A honeypot hit gets
  the redirect and neither. See `docs/decisions.md`, "Enquiry conversions".
- `GET /healthz` — `{"status": "ok", "enquiries": n}`, or 503 if the store is unreadable.

No `/docs`, `/redoc` or `/openapi.json`: nothing public should describe its own
attack surface.

## Fields

Four visible: name and email (required), phone and a message (optional). Two
hidden interest checkboxes, pre-ticked from the page the visitor is on. See
[docs/decisions.md](../docs/decisions.md), "Enquiry form fields", for what was
dropped from the old Gravity Form and why.

## Three things that look incidental and are not

Each is pinned by a test, because each would break the nightly job in a way
that looks fine until someone checks Salesforce.

1. **Ids start at 100000.** henley-utils de-duplicates against the *full set* of
   ids it has already processed (currently 1674–5229 from the WordPress era),
   not a high-water mark, and the id is Salesforce's `WebFormID_c__c` external
   key. An id from that range is either silently skipped as already-processed
   or upserts onto a Lead belonging to somebody else.
2. **`created_at` is naive UTC, `YYYY-MM-DD HH:MM:SS`.** That is exactly what
   `_convert_date_to_brisbane()` parses with `strptime` before attaching UTC.
   ISO-8601 falls through it unconverted; SQLite's `localtime` would shift every
   enquiry by ten hours.
3. **WAL, and a uid that matches the host user.** The reader opens the file
   `mode=ro` while this service holds it open. Without WAL they block each
   other; if the `-wal` and `-shm` sidecars are not readable by the reader's
   user, it sees an empty database rather than an error.

## Bot protection

Honeypot, per-IP and daily caps, body-size limit. No CAPTCHA — see the decisions
document. The honeypot answers with the same 303 a real submission gets: telling
a bot why it failed only helps it tune. It is now the *only* thing that does, so
a 303 to a legitimate visitor means a stored row.

There was a minimum fill time as well, comparing the visitor's clock with ours.
A device five minutes fast lost a real enquiry behind the success redirect, so
it is gone — `MIN_FILL_SECONDS` and the `started_at` field with it. A cached
page still posting `started_at` is harmless: the receiver does not read it.

## Proxy trust

The receiver is the only thing that interprets `X-Forwarded-For`. The container
runs uvicorn with `--no-proxy-headers` on purpose: it previously ran
`--proxy-headers --forwarded-allow-ips '*'`, which rewrote `request.client` from
a header anyone could send, before `client_ip()` saw the real peer.

`client_ip()` takes the **last** field of the header, because the proxy appends
the address it observed and a client cannot write anything after it. (NPM's
`/api/enquiry` location goes further and *overwrites* the header with
`$remote_addr`, so it holds one address and nothing the client sent. The
last-field rule is correct either way.) That field
must parse as an IP address; if it does not, the peer is used and a warning is
logged, on the reasoning that a chain not ending in the proxy's own observation
means the proxy is not appending, and the earlier entries are the client's to
choose.

A peer outside `TRUSTED_PROXY_IPS` is never believed: the peer itself is taken
to be the visitor. If it sends `X-Forwarded-For` anyway, the receiver says so,
once per peer per process:

```text
untrusted peer 192.168.176.4 sent X-Forwarded-For (last hop 203.0.113.9); using the peer
```

That means a proxy the configuration does not cover is forwarding addresses,
and every visitor behind it is sharing one rate-limit bucket. It is the line
the 2026-09-27 drift would have logged, when a reboot moved NPM to `.4` and
nothing said so for nine days. Check the configured range against the network:
the startup line `X-Forwarded-For is believed from …` against
`docker network inspect henley-website-<env>-net -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'`.
The last hop is parsed, or reported as `malformed`; the header itself is never
logged, because it is whatever the client wrote.

`scripts/check-proxy-trust.sh` builds this image, runs it behind a real nginx
and checks all of that from outside, including a chunked oversized body. It
runs three scenarios: the proxy's own address configured, a network covering
the proxy, and a client inside that network reaching the receiver directly —
the property the network setting accepts. No in-process test can do this: the
defect it guards was in the Docker command.
