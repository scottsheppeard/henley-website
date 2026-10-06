# Plan: the enquiry receiver trusts the website network, not the proxy's address

Date: 2026-10-06. Stream `replica`. Spec: the reviewed plan at
`~/.claude/plans/henley-website-proxy-trust-2026-10-06.md` (Codex-reviewed
once; its "Changes from Codex review" section is binding).

## Why

`TRUSTED_PROXY_IPS` holds the literal address Docker gave `npm-attachment`
on the website network the day the env file was written. Docker allocates
addresses on a user-defined network in container start order and does not
remember who had what. The 2026-09-27 07:26 host reboot reshuffled
`henley-website-prod-net`: `henley-website-prod` took `.2`, the receiver
`.3`, `npm-attachment` `.4`. The receiver kept trusting `.2`, so from
27 Sep 10:46 AEST every visitor was attributed to `192.168.176.4`, the
3-per-hour per-visitor cap became a site-wide cap, 758 POSTs were refused
with 429 across four bot-flood hours, and rows 100016 onward store the
proxy's address. Nonprod drifted the same way (`.4` to `.3`).

The receiver publishes no port. The only peers that can reach it are
containers on its network: NPM, the static site nginx, and itself. Keystone's
`docs/network-segmentation.md` already makes that network the trust
boundary. So the setting accepts networks, and the deployed value becomes
the network's subnet, which Docker keeps across reboots and NPM recreations.

**Accepted property.** A container on the website network that reaches the
receiver directly may assert a visitor address with `X-Forwarded-For`. Today
that set is NPM and one read-only static nginx. Stated in `docs/decisions.md`
and proven, not assumed, by the shell check.

## Global Constraints

- The environment variable keeps its name, `TRUSTED_PROXY_IPS`, and keeps
  accepting a comma-separated list. Every existing value (bare addresses)
  must keep working unchanged.
- Each entry is parsed with `ipaddress.ip_network(entry, strict=False)`.
  A bare address becomes a single-host network. The module-level name is
  `TRUSTED_PROXY_NETWORKS` (a list); `TRUSTED_PROXIES` goes away.
- An entry that does not parse raises `ValueError` at import with the
  message `TRUSTED_PROXY_IPS entry {entry!r} is not an IP address or network`,
  so the container refuses to start. An ignored entry would fail closed into
  the same silent site-wide limit this plan removes.
- The empty-value startup WARNING keeps its existing text
  (`TRUSTED_PROXY_IPS is empty. …`).
- Startup INFO line format: `X-Forwarded-For is believed from <entries>`
  where entries are joined by `, ` in sorted order, a single-host network is
  printed as the bare address (`10.0.0.1`, not `10.0.0.1/32`) and any other
  network as CIDR (`192.168.176.0/20`). The existing assertion
  `"X-Forwarded-For is believed from 10.0.0.1"` must keep passing.
- A peer is trusted when `normalise_ip(peer)` parses and the parsed address
  is inside any configured network. A peer that is not an address literal
  (for example `testclient`) is never trusted.
- Detection WARNING, logged at most once per distinct peer per process,
  when an untrusted peer presents a non-empty `X-Forwarded-For`:
  `untrusted peer {peer} sent X-Forwarded-For (last hop {hop}); using the peer`
  where `{hop}` is the parsed last-hop address via `normalise_ip`, or the
  literal word `malformed` if it does not parse. The raw header value is
  never logged. The existing malformed-last-hop warning from a *trusted*
  peer is unchanged.
- Tests use real peers: `TestClient(app_module.app, client=("10.0.0.1", 50000))`
  (Starlette 0.49.3 supports `client=`). No production seam exists for a
  fake peer name.
- Tests run with `forms/.venv/bin/python -m pytest forms/tests -q` from the
  repo root; all existing tests keep passing.
- Nothing in this plan touches a deployed container, a deployed network, a
  live env file (`deploy/.env`, `deploy/.env.prod`, both gitignored) or
  `/home/admin/henley-aws`. Deployment is a separate, hand-run step after
  landing.
- Commit style: this repo's history (`replica: …`, `docs: …`,
  `check-proxy-trust: …`), imperative, one coherent change per commit.

## Task 1: the receiver accepts networks, and warns about untrusted peers

Files: `forms/app.py`, `forms/tests/test_app.py`. TDD: write each failing
test first, then the smallest change that passes it.

Current state in `forms/app.py`:

- Lines ~72–82: the comment block and `TRUSTED_PROXIES = {ip.strip() for ip in os.environ.get("TRUSTED_PROXY_IPS", "").split(",") if ip.strip()}`.
- `normalise_ip(value) -> str | None` (around line 137) strips a port or
  brackets and returns the canonical address string, or `None`.
- `client_ip(request)` (around line 155): `peer = request.client.host`;
  `if peer not in TRUSTED_PROXIES: return peer`; then reads the header,
  takes the last field, warns if it does not parse.
- `lifespan()` (around line 403) logs the believed set or the empty warning.

Changes:

1. Replace `TRUSTED_PROXIES` with `TRUSTED_PROXY_NETWORKS`, built by a small
   module-level function `parse_trusted_proxies(value: str) -> list[IPv4Network | IPv6Network]`
   that raises the `ValueError` from Global Constraints on a bad entry.
   Rewrite the comment block above it: trust is a set of networks; on the
   live hosts it is the website Docker network's subnet, because the
   receiver has no published port and the network is the boundary; a bare
   address still works; the 2026-09-27 reboot is why (one sentence).
2. `client_ip()`: compute `observed_peer = normalise_ip(peer)`; trusted iff
   it is not `None` and `ipaddress.ip_address(observed_peer)` is in any
   network. If untrusted and the header is non-empty, emit the detection
   WARNING once per peer per process (a module-level `set`, reset by
   `_reset_rate_limits()` so tests start clean), then return the peer.
3. `lifespan()`: the startup line per Global Constraints; a helper
   `describe_network(net) -> str` returns the bare address for a
   single-host network and CIDR otherwise.
4. Tests (`forms/tests/test_app.py`):
   - Change `behind_proxy()` and every test that uses it to make the test
     client's peer a real trusted address. The simplest shape: a second
     fixture or helper that opens `TestClient(app_module.app, client=("10.0.0.1", 50000))`;
     the `receiver` fixture already sets `TRUSTED_PROXY_IPS=10.0.0.1`.
     Delete the `monkeypatch.setattr(app_module, "TRUSTED_PROXIES", …)`
     pattern entirely.
   - `test_forwarded_for_is_believed_only_from_the_configured_proxy`: the
     untrusted peer is `TestClient`'s default `testclient`; its stored
     `remote_ip` stays `testclient`. Keep it, and add the assertion that the
     detection warning was logged with `last hop 203.0.113.9` and that the
     raw header value appears nowhere else in `caplog.text` for that call.
   - New: a CIDR entry (`TRUSTED_PROXY_IPS=10.0.0.0/24`) trusts peer
     `10.0.0.77` (its header's last hop is stored) and does not trust
     `10.0.1.77` (its own address is stored).
   - New: a bare address entry still works as a `/32` (the existing
     fixture value proves it; assert `TRUSTED_PROXY_NETWORKS == [ip_network("10.0.0.1/32")]`
     in the startup test instead of the old `TRUSTED_PROXIES` assertion).
   - New: an IPv6 bare address (`2001:db8::1`) and an IPv6 network
     (`2001:db8::/32`) parse, and a peer `2001:db8::9` is trusted by the
     network entry. (`TestClient` `client=` accepts an IPv6 string.)
   - New: `TRUSTED_PROXY_IPS=not-an-address` makes `importlib.reload(app)`
     raise `ValueError` matching the Global Constraints message. Reload the
     module again with a valid value in a `finally` so later tests are not
     poisoned.
   - New: the detection warning fires once for three requests from the same
     untrusted peer, names a parsed address, and for a header whose last hop
     is `not-an-ip` says `last hop malformed` with `not-an-ip` absent from
     `caplog.text`.
   - Startup line test: add a case with `TRUSTED_PROXY_IPS=192.168.176.0/20,10.0.0.1`
     expecting `X-Forwarded-For is believed from 10.0.0.1, 192.168.176.0/20`.
5. Run the whole suite; it must be green. Commit as
   `replica: the receiver trusts networks, and says when an untrusted peer forwards an address`.

## Task 2: the shell check runs three isolated scenarios

File: `scripts/check-proxy-trust.sh`. Depends on Task 1 (the image it builds
must contain the CIDR support).

Current shape: one network `10.177.0.0/24`, receiver `.10`, nginx proxy
`.20`, clients `.101`–`.104`, one receiver started with
`TRUSTED_PROXY_IPS="$PROXY_IP"`, checks in sequence, `trap cleanup EXIT`.
It builds the image once (`docker build -q -t "$TAG" forms`) and uses
`curlimages/curl:latest` clients with pinned `--ip`.

Changes:

1. Restructure into `scenario NAME TRUSTED_VALUE` which, per call: creates a
   fresh network (`henley-proxycheck-$$-NAME`, same subnet), a fresh data
   directory, a fresh receiver and proxy, waits for health, prints the
   deployed command and the believed line, runs that scenario's checks,
   then removes its containers and network. The image is built once, up
   front, and removed at exit. `cleanup` on `trap EXIT` must remove whatever
   scenario is live plus the image, so a failed scenario cannot leak a
   network. The `check`, `client` and `rows` helpers stay; `rows` and
   `client` take the current scenario's receiver/network from variables set
   by `scenario`.
2. Scenario **literal** (`TRUSTED_PROXY_IPS=10.177.0.20`): every existing
   check, unchanged in substance: four spoofed submissions give
   `303 303 303 429`, three rows all carrying `$CLIENT_A`; the unrelated
   visitor is accepted and stored against `$CLIENT_B`; the direct client
   `$CLIENT_C` is accepted, cannot choose its identity, is stored against
   its own address; the chunked 20 KB body is refused 413 with no row; the
   ordinary submission 303; `/healthz` 200; container HEALTHCHECK.
3. Scenario **cidr-covering** (`TRUSTED_PROXY_IPS=10.177.0.16/28`, which
   contains `.16`–`.31`: the proxy at `.20` but none of the clients at
   `.101`–`.104`): the believed line names `10.177.0.16/28`; the four
   spoofed submissions through the proxy give `303 303 303 429` with rows
   carrying `$CLIENT_A`; the direct client `$CLIENT_C` cannot choose its
   identity and is stored against its own address; and the receiver log
   contains exactly one line matching `untrusted peer 10.177.0.103 sent X-Forwarded-For`
   after two direct requests from `$CLIENT_C` (send two, so "once per
   peer" is what is checked). The body-size checks are not repeated here.
4. Scenario **cidr-inside** (same range): a direct client at `CLIENT_E=10.177.0.21`,
   inside the range, sends `X-Forwarded-For: 203.0.113.77` to
   `http://receiver:8000/api/enquiry` and the row is stored against
   `203.0.113.77`. Print, before the check, the sentence: `a peer inside the
   trusted range may assert a visitor address: on the live networks that
   set is NPM and the static site nginx (docs/decisions.md, 2026-10-06)`.
   The check line reads `an in-range peer's forwarded address is believed (the accepted property)`.
5. The header comment of the script gains a paragraph on the three
   scenarios and why the third exists. The final success line becomes
   `proxy trust: the receiver owns the client address, networks are honoured, and the body limit is enforced on bytes received`.
6. Run the script; all checks PASS. Commit as
   `check-proxy-trust: three isolated scenarios, including the in-range peer the network model allows`.

## Task 3: configuration examples and documentation

Files: `deploy/.env.example`, `deploy/compose.prod.yml`,
`deploy/compose.nonprod.yml`, `forms/README.md`, `docs/runbook-cutover.md`,
`docs/decisions.md`, `docs/2026-09-24-cutover-record.md`. No code. Depends
on Tasks 1 and 2 only for the exact log-line wording, which is fixed in
Global Constraints.

1. `deploy/.env.example`: the value is the website Docker network's
   subnet, read with
   `docker network inspect henley-website-<env>-net -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'`
   (prod `henley-website-prod-net` = `192.168.176.0/20`, nonprod
   `henley-website-nonprod-net` = `192.168.160.0/20`, as of 2026-10-06).
   Remove the `docker inspect … npm-attachment` block and the sentence
   "it changes whenever npm-attachment is recreated". Say: the subnet
   survives reboots and NPM recreations and changes only if the network
   itself is deleted and recreated; a bare address still works; the check
   is still `docker logs henley-website-forms-<env> | head`.
2. `deploy/compose.prod.yml` and `deploy/compose.nonprod.yml`: the comment
   block above `TRUSTED_PROXY_IPS: ${TRUSTED_PROXY_IPS:-}` says the same,
   replacing the npm-attachment inspect command with the network inspect
   command, and one sentence on why the network is the boundary (no
   published port; NPM is the only multi-homed container).
3. `forms/README.md`: the `TRUSTED_PROXY_IPS` row in "Configuration"
   (comma-separated addresses or CIDR networks; the deployed value is the
   network's subnet; why; the accepted property in one sentence; a bad
   entry refuses to start). In "Proxy trust", add the detection warning
   and what it means (a peer the configuration does not cover is forwarding
   addresses: check the configured range against the network).
4. `docs/runbook-cutover.md`: in cutover step 2, replace the
   `prod_npm_ip` / `nonprod_npm_ip` inspect-and-sed block with the two
   `docker network inspect … .Subnet` reads and the matching `sed` lines,
   and reword the paragraph after it. In "Trusted proxy address", replace
   the two `docker inspect … npm-attachment` commands and the "Both
   addresses can change when npm-attachment is recreated" paragraph with
   the network-subnet rule. Add a short dated note that the 2026-09-27
   reboot reassigned addresses and this is why.
5. `docs/decisions.md`: under "X-Forwarded-For has one owner (2026-09-10)",
   add `### The trusted proxy is a network, not an address (2026-10-06)`:
   what changed, the reboot that forced it, why the network is the
   boundary, the accepted property, the step-up (an NPM-injected shared
   secret) and why it was not taken (a recreated proxy host that forgets
   the header fails the same silent way).
6. `docs/2026-09-24-cutover-record.md`: a new section
   `## Proxy address drift, found 2026-10-06` with the facts in "Why"
   above (dates and times AEST, the counts, the row range, that the
   stored addresses for rows 100016 onward are not recoverable, that
   nonprod drifted too), and the line that drain step 5c was executed
   2026-10-06 10:36 AEST (`db-prod-henley` stopped, restart policy `no`)
   with "tonight's 00:30 run is the check". Leave a final bullet
   `Deployed: (to be recorded)` for the controller to fill after the
   production redeploy. Update "Still open" accordingly.
7. Commit as `docs: the trusted proxy is the website network's subnet, and the 27 September drift`.
