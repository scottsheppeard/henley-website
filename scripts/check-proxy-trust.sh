#!/usr/bin/env bash
#
# check-proxy-trust.sh — prove the receiver's rate limit survives contact with
# a real proxy and a real HTTP client.
#
# Every in-process test of X-Forwarded-For passed while production was wide
# open, because the defect was not in app.py. It was in the Docker command:
# uvicorn ran with --proxy-headers --forwarded-allow-ips '*', rewrote
# request.client from a header anyone could send, and did it before app.py's
# own trusted-proxy logic ever saw the peer. So four submissions carrying four
# invented first hops were four different visitors, and three-an-hour meant
# nothing.
#
# TestClient cannot see that, and neither can `uvicorn app:app` run by hand.
# This builds the actual image, runs it behind an actual nginx, and asks the
# questions from outside: can a client choose its own rate-limit bucket, and
# can it get a 20 KB body past a 16 KB limit by not declaring a length.
#
# Client addresses are pinned rather than left to Docker, which reuses them
# from a pool — two "different" clients on the same address is the one thing
# that would make this whole check lie.
#
# Everything it creates is disposable and is removed on exit. It never touches
# a deployed container, a deployed network or a real intake database.
#
# Usage: scripts/check-proxy-trust.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TAG="henley-forms-proxycheck:$$"
NET="henley-proxycheck-$$"
RECEIVER="henley-proxycheck-forms-$$"
PROXY="henley-proxycheck-nginx-$$"
CLIENT_IMAGE="curlimages/curl:latest"
WORK="$(mktemp -d)"
# mktemp gives 0700, and the curl image runs as its own unprivileged user, so
# without this it cannot traverse into the mount and silently sends no body.
chmod 755 "$WORK"

# A subnet of our own, so the addresses below are ours to assign.
SUBNET="10.177.0.0/24"
RECEIVER_IP="10.177.0.10"
PROXY_IP="10.177.0.20"
CLIENT_A="10.177.0.101"      # the spoofing client
CLIENT_B="10.177.0.102"      # a second, unrelated visitor
CLIENT_C="10.177.0.103"      # reaches the receiver directly, past the proxy
CLIENT_D="10.177.0.104"      # sends the oversized streamed body

cleanup() {
  docker rm -f "$PROXY" "$RECEIVER" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker image rm -f "$TAG" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }

failures=0
check() {
  if [[ "$1" == "ok" ]]; then
    printf '  PASS  %s\n' "$2"
  else
    printf '  FAIL  %s\n' "$2"
    failures=$((failures + 1))
  fi
}

echo "building the receiver image ..."
docker build -q -t "$TAG" forms >/dev/null

docker network create --subnet "$SUBNET" "$NET" >/dev/null

# The intake store is a throwaway directory owned by this run. The image runs
# as uid 1000, which is this user, so the bind mount is writable.
mkdir -p "$WORK/data"

# TRUSTED_PROXY_IPS is the proxy's address on this network — read the same way
# the runbook reads npm-attachment's, and known in advance here only because we
# assigned it.
docker run -d --name "$RECEIVER" --network "$NET" --ip "$RECEIVER_IP" \
  --network-alias receiver \
  -e INTAKE_DB_PATH=/data/intake.sqlite \
  -e TRUSTED_PROXY_IPS="$PROXY_IP" \
  -e MAX_PER_IP_PER_HOUR=3 \
  -e MAX_BODY_BYTES=16384 \
  -v "$WORK/data:/data" \
  "$TAG" >/dev/null

# nginx as NPM is: it appends the peer it actually saw to whatever the client
# claimed, which is what makes the *last* hop the trustworthy one.
# proxy_request_buffering off so an oversized body reaches the receiver as a
# stream rather than being collected by nginx first.
cat >"$WORK/nginx.conf" <<'CONF'
events {}
http {
  server {
    listen 8080;
    client_max_body_size 0;
    location / {
      proxy_pass http://receiver:8000;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_http_version 1.1;
      proxy_request_buffering off;
    }
  }
}
CONF

docker run -d --name "$PROXY" --network "$NET" --ip "$PROXY_IP" \
  --network-alias proxy \
  -v "$WORK/nginx.conf:/etc/nginx/nginx.conf:ro" \
  nginx:alpine >/dev/null

client() {
  # client <fixed-ip> <curl args...>
  #
  # $WORK is mounted so a request body can be a file rather than stdin: a
  # `docker run` without -i has no stdin, and curl then sends an empty body
  # perfectly happily, which looks like a passing check for the wrong reason.
  local ip="$1"; shift
  docker run --rm --network "$NET" --ip "$ip" -v "$WORK:/payload:ro" "$CLIENT_IMAGE" "$@"
}

for _ in $(seq 1 60); do
  client "$CLIENT_B" -sf --max-time 2 http://proxy:8080/healthz >/dev/null 2>&1 && break
  sleep 0.5
done
client "$CLIENT_B" -sf --max-time 5 http://proxy:8080/healthz >/dev/null \
  || { echo "the receiver never became healthy" >&2; docker logs "$RECEIVER" >&2; exit 1; }

echo
echo "the deployed command:"
docker inspect -f '  {{json .Config.Cmd}}' "$RECEIVER"
docker logs "$RECEIVER" 2>&1 | grep -i 'x-forwarded-for is believed\|TRUSTED_PROXY_IPS is empty' \
  | sed 's/^/  /' || true

rows() {
  docker exec "$RECEIVER" python -c "
import sqlite3
connection = sqlite3.connect('file:/data/intake.sqlite?mode=ro', uri=True)
for row in connection.execute('SELECT id, email, remote_ip FROM enquiries ORDER BY id'):
    print('%s\t%s\t%s' % row)
"
}

echo
echo "four submissions from one client ($CLIENT_A), each claiming a different first hop:"
statuses=()
for i in 0 1 2 3; do
  statuses+=("$(client "$CLIENT_A" -sS -o /dev/null -w '%{http_code}' --max-time 10 \
    -H "X-Forwarded-For: 10.$i.$i.$i" \
    --data "name=Spoof$i&email=spoof$i@example.com" http://proxy:8080/api/enquiry)")
done
echo "  statuses: ${statuses[*]}"

[[ "${statuses[*]}" == "303 303 303 429" ]] \
  && check ok "the fourth is refused: a spoofed hop cannot buy a new bucket" \
  || check no "expected 303 303 303 429, got ${statuses[*]}"

stored_ips="$(rows | cut -f3 | sort -u | tr '\n' ' ')"
echo "  stored addresses: $stored_ips"
[[ "$(rows | wc -l)" -eq 3 ]] \
  && check ok "three rows stored, not four" \
  || check no "expected 3 rows, got $(rows | wc -l)"
[[ "$stored_ips" == "$CLIENT_A " ]] \
  && check ok "all three carry the address the proxy actually observed" \
  || check no "expected only $CLIENT_A stored, got: $stored_ips"

echo
echo "a second, unrelated visitor ($CLIENT_B) while the first is over its limit:"
second="$(client "$CLIENT_B" -sS -o /dev/null -w '%{http_code}' --max-time 10 \
  -H 'X-Forwarded-For: 10.9.9.9' \
  --data 'name=Second&email=second@example.com' http://proxy:8080/api/enquiry)"
echo "  status: $second"
[[ "$second" == "303" ]] \
  && check ok "independent addresses are counted independently" \
  || check no "expected 303 for an unrelated visitor, got $second"
rows | grep -q "	$CLIENT_B$" \
  && check ok "and it was stored against its own address" \
  || check no "the second visitor was not stored against $CLIENT_B"

echo
echo "a client reaching the receiver directly ($CLIENT_C), past the proxy:"
direct="$(client "$CLIENT_C" -sS -o /dev/null -w '%{http_code}' --max-time 10 \
  -H 'X-Forwarded-For: 203.0.113.77' \
  --data 'name=Direct&email=direct@example.com' http://receiver:8000/api/enquiry)"
echo "  status: $direct"
[[ "$direct" == "303" ]] \
  && check ok "an untrusted peer is accepted" \
  || check no "expected 303 from a direct client, got $direct"
rows | grep -q "203.0.113.77" \
  && check no "an untrusted peer chose its own identity with a header" \
  || check ok "an untrusted peer cannot choose its own identity with a header"
rows | grep -q "	$CLIENT_C$" \
  && check ok "it was stored against the address it actually came from" \
  || check no "the direct client was not stored against $CLIENT_C"

echo
echo "a 20 KB body sent in chunks by $CLIENT_D, with no Content-Length:"
before="$(rows | wc -l)"
printf 'name=Big&email=big@example.com&enquiry_text=%s' \
  "$(head -c 20000 /dev/zero | tr '\0' 'x')" >"$WORK/oversized"
chmod 644 "$WORK/oversized"

# -v so the request headers are visible: this check is worthless if curl
# quietly declared a length, because that is the case the old code caught.
oversized_out="$(client "$CLIENT_D" -sS -v -o /dev/null -w '%{http_code}' --max-time 20 \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Transfer-Encoding: chunked' \
  --data-binary @/payload/oversized http://proxy:8080/api/enquiry 2>"$WORK/curl.log" || true)"
echo "  status: $oversized_out"
grep -qi '^> Transfer-Encoding: chunked' "$WORK/curl.log" \
  && check ok "the request really was chunked" \
  || check no "curl did not send it chunked; this check proves nothing"
grep -qi '^> Content-Length:' "$WORK/curl.log" \
  && check no "a Content-Length was declared, so the old shortcut would have caught it" \
  || check ok "no Content-Length was declared"
if grep -qi 'upload completely sent off\|Send failure\|^} \[' "$WORK/curl.log"; then
  check ok "the client actually sent the payload"
else
  check no "the client sent no body; this check proves nothing"
  sed 's/^/    /' "$WORK/curl.log" | head -5
fi
[[ "$oversized_out" == "413" ]] \
  && check ok "the streamed oversized body is refused with 413" \
  || check no "expected 413 for a chunked 20 KB body, got $oversized_out"
[[ "$(rows | wc -l)" -eq "$before" ]] \
  && check ok "no row was stored for it" \
  || check no "an oversized streamed body reached the insert path"

echo
echo "and the ordinary cases:"
under="$(client "$CLIENT_D" -sS -o /dev/null -w '%{http_code}' --max-time 10 \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'name=Ordinary&email=ordinary@example.com&enquiry_text=Could I see a two-bedroom apartment?' \
  http://proxy:8080/api/enquiry)"
[[ "$under" == "303" ]] \
  && check ok "an ordinary under-limit submission is accepted" \
  || check no "expected 303 for an ordinary submission, got $under"

health="$(client "$CLIENT_B" -sS -o /dev/null -w '%{http_code}' --max-time 5 \
  http://proxy:8080/healthz)"
[[ "$health" == "200" ]] \
  && check ok "the health check still answers through the proxy" \
  || check no "expected 200 from /healthz, got $health"

container_health="$(docker inspect -f '{{.State.Health.Status}}' "$RECEIVER" 2>/dev/null || echo none)"
[[ "$container_health" == "healthy" || "$container_health" == "starting" ]] \
  && check ok "the container's own HEALTHCHECK is $container_health" \
  || check no "the container's HEALTHCHECK reports $container_health"

echo
echo "everything stored:"
rows | sed 's/^/  /'

echo
if (( failures )); then
  echo "$failures check(s) failed"
  docker logs "$RECEIVER" 2>&1 | tail -30
  exit 1
fi
echo "proxy trust: the receiver owns the client address, and the body limit is enforced on bytes received"
