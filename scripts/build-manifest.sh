#!/usr/bin/env bash
#
# build-manifest.sh — generate source/migration-manifest.json
#
# The manifest is the URL contract the rebuilt site has to honour: every address
# the WordPress site answers today, the title/description/canonical it answers
# with, the shortlink and legacy redirects pointing at it, and the documents it
# links to. scripts/check-urls.sh asserts a deployed environment against it.
#
# Page metadata comes from the committed capture in source/live-capture-*, so the
# contract is pinned to the snapshot we are migrating rather than to whatever the
# old site serves at the moment. Status codes and redirect targets are evidence
# about live behaviour and can only come from the live site, so those are probed
# over the network; --offline skips them and leaves the previous probe results in
# place, which is what you want once WordPress is switched off.
#
# Usage: scripts/build-manifest.sh [--offline]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAPTURE_DIR="$REPO_ROOT/source/live-capture-2026-09-09"
OUTPUT="$REPO_ROOT/source/migration-manifest.json"
ORIGIN="https://thehenley.com.au"

OFFLINE=0
[[ "${1:-}" == "--offline" ]] && OFFLINE=1

[[ -d "$CAPTURE_DIR" ]] || { echo "capture not found: $CAPTURE_DIR" >&2; exit 1; }

PROBES="$(mktemp)"
trap 'rm -f "$PROBES"' EXIT

# Probe one URL, recording "<url> <status> <redirect-target>" without following
# the redirect, so a 301 chain is described a hop at a time.
probe() {
  local url="$1" line
  line="$(curl -sS --max-time 20 -o /dev/null -w '%{http_code} %{redirect_url}' "$url" 2>/dev/null)" || line="000 "
  printf '%s\t%s\n' "$url" "$line" >>"$PROBES"
}

if (( OFFLINE )); then
  echo "offline: skipping live probes"
else
  echo "probing $ORIGIN ..."
  # Every sitemap URL, so the manifest records that each one answers 200 today.
  while read -r url; do probe "$url"; done < <(
    grep -o 'https://[^[:space:]]*' "$CAPTURE_DIR/sitemap.txt"
  )
  # Addresses the sitemaps omit but that are live and must be accounted for.
  for path in /news/page/2/ /news/page/3/ /feed/ /news/feed/ /robots.txt \
              /sitemap_index.xml /page-sitemap.xml /post-sitemap.xml; do
    probe "$ORIGIN$path"
  done
  # Canonicalisation: host, scheme and trailing slash all fold to one address.
  probe "https://www.thehenley.com.au/contact/"
  probe "http://thehenley.com.au/contact/"
  probe "$ORIGIN/contact"
  # The two WordPress Redirection rules.
  probe "$ORIGIN/luxury-resort-living/"
  probe "$ORIGIN/latest-articles/top-10-questions-to-ask-your-sales-manager/"
  # A 404, to record what "not found" looks like today.
  probe "$ORIGIN/no-such-page-please-404/"
  # Every shortlink id found in the capture.
  while read -r id; do probe "$ORIGIN/?p=$id"; done < <(
    grep -ho "rel=['\"]shortlink['\"] href=['\"][^'\"]*[?]p=[0-9]*" "$CAPTURE_DIR"/pages/*.html |
      grep -o '[0-9]*$' | sort -un
  )
fi

CAPTURE_DIR="$CAPTURE_DIR" OUTPUT="$OUTPUT" ORIGIN="$ORIGIN" \
PROBES="$PROBES" OFFLINE="$OFFLINE" python3 - <<'PY'
import html, json, os, re, sys
from pathlib import Path

capture = Path(os.environ["CAPTURE_DIR"])
output = Path(os.environ["OUTPUT"])
origin = os.environ["ORIGIN"]
offline = os.environ["OFFLINE"] == "1"

# --- live probe results -------------------------------------------------------
probes = {}
for line in Path(os.environ["PROBES"]).read_text().splitlines():
    url, _, rest = line.partition("\t")
    status, _, target = rest.partition(" ")
    probes[url] = {"status": int(status), "redirect_to": target or None}

if offline and output.exists():
    # Keep the probe evidence from the last online run rather than blanking it.
    for entry in json.loads(output.read_text()).get("urls", []):
        if entry.get("live") is not None:
            probes[origin + entry["path"]] = entry["live"]

def live_for(url):
    return probes.get(url)

# --- capture parsing ----------------------------------------------------------
TAGS = {
    "title": re.compile(r"<title>(.*?)</title>", re.S | re.I),
    "description": re.compile(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>', re.S | re.I),
    "canonical": re.compile(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', re.S | re.I),
    "shortlink": re.compile(r'<link\s+rel=["\']shortlink["\']\s+href=["\'](.*?)["\']', re.S | re.I),
    "og_image": re.compile(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', re.S | re.I),
    "robots": re.compile(r'<meta\s+name=["\']robots["\']\s+content=["\'](.*?)["\']', re.S | re.I),
}

def capture_file_for(path):
    """/ -> pages/home.html ; /some-slug/ -> pages/some-slug.html"""
    slug = path.strip("/").split("/")[-1] or "home"
    return capture / "pages" / f"{slug}.html"

def parse(file):
    text = file.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key, pattern in TAGS.items():
        match = pattern.search(text)
        out[key] = html.unescape(match.group(1)).strip() if match else None
    return out

# --- sitemap ------------------------------------------------------------------
urls, kind = [], None
for line in (capture / "sitemap.txt").read_text().splitlines():
    line = line.strip()
    if line.startswith("== "):
        kind = line[3:].strip()
    elif line.startswith("https://"):
        url, _, lastmod = line.partition("\t") if "\t" in line else line.partition(" ")
        urls.append((kind, url.strip(), lastmod.strip()))

entries, shortlinks, missing = [], {}, []
for kind, url, lastmod in urls:
    path = url[len(origin):] or "/"
    file = capture_file_for(path)
    if not file.exists():
        missing.append(path)
        continue
    meta = parse(file)
    short_id = None
    if meta["shortlink"]:
        match = re.search(r"[?]p=(\d+)", meta["shortlink"])
        if match:
            short_id = int(match.group(1))
            shortlinks[str(short_id)] = path
    entries.append({
        "path": path,
        "type": kind,
        "lastmod": lastmod or None,
        "title": meta["title"],
        "description": meta["description"],
        "canonical": meta["canonical"],
        "og_image": meta["og_image"],
        "robots": meta["robots"],
        "shortlink_id": short_id,
        "capture": str(file.relative_to(capture.parent.parent)),
        "live": live_for(url),
    })

if missing:
    sys.exit(f"sitemap URLs with no capture file: {missing}")

# --- URLs the sitemaps omit ---------------------------------------------------
def extra(path, note, expect):
    return {"path": path, "note": note, "expect": expect, "live": live_for(origin + path)}

extras = [
    extra("/news/page/2/", "Second page of the news index; live and self-canonicalising. "
                           "Keep as a real page, or redirect it deliberately to /news/.", "200 or intended 301"),
    extra("/news/page/3/", "Does not exist today — the index is two pages long.", "404"),
    extra("/feed/", "Site RSS feed, live and linked from every page's <head>.", "200"),
    extra("/news/feed/", "Blog archive feed, also live.", "200"),
    extra("/robots.txt", "Yoast-generated; allows all.", "200"),
    extra("/sitemap_index.xml", "Yoast sitemap index — redirect to the new /sitemap.xml.", "200"),
    extra("/page-sitemap.xml", "Yoast page sitemap — redirect to the new /sitemap.xml.", "200"),
    extra("/post-sitemap.xml", "Yoast post sitemap — redirect to the new /sitemap.xml.", "200"),
    extra("/no-such-page-please-404/", "Reference 404 behaviour.", "404"),
]

# --- redirects ----------------------------------------------------------------
redirects = [
    {"from": "/luxury-resort-living/", "to": "/luxury-retirement-living/", "status": 301,
     "source": "WordPress Redirection rule (737 hits)", "live": live_for(origin + "/luxury-resort-living/")},
    {"from": "/latest-articles/(.*)", "to": "/$1", "status": 301, "pattern": True,
     "source": "WordPress Redirection rule (3,072 hits)",
     "live": live_for(origin + "/latest-articles/top-10-questions-to-ask-your-sales-manager/")},
    {"from": "/sitemap_index.xml", "to": "/sitemap.xml", "status": 301, "source": "new site"},
    {"from": "/page-sitemap.xml", "to": "/sitemap.xml", "status": 301, "source": "new site"},
    {"from": "/post-sitemap.xml", "to": "/sitemap.xml", "status": 301, "source": "new site"},
]

canonicalisation = [
    {"rule": "www to apex", "example": "https://www.thehenley.com.au/contact/",
     "live": live_for("https://www.thehenley.com.au/contact/")},
    {"rule": "http to https", "example": "http://thehenley.com.au/contact/",
     "live": live_for("http://thehenley.com.au/contact/")},
    {"rule": "add trailing slash", "example": origin + "/contact",
     "live": live_for(origin + "/contact")},
]

# --- documents ----------------------------------------------------------------
pdf_pattern = re.compile(r'https://thehenley\.com\.au(/wp-content/uploads/[^"\'\s<>]+\.pdf)', re.I)
documents = {}
for file in sorted((capture / "pages").glob("*.html")):
    for path in pdf_pattern.findall(file.read_text(encoding="utf-8", errors="replace")):
        documents.setdefault(path, set()).add("/" if file.stem == "home" else f"/{file.stem}/")

aliases = {
    "Henley-Form-3-VCD": "/documents/village-comparison-document.pdf",
    "SCHEDULE-OF-FEES": "/documents/schedule-of-fees.pdf",
}
document_entries = []
for path in sorted(documents):
    alias = next((a for key, a in aliases.items() if key in path), None)
    document_entries.append({
        "path": path,
        "alias": alias,
        "linked_from": sorted(documents[path]),
        "note": "Dated file stays immutable and long-cached; the alias always points at the "
                "current revision and must revalidate." if alias else None,
    })

manifest = {
    "$comment": "Generated by scripts/build-manifest.sh — do not edit by hand. "
                "Page metadata comes from the committed capture; 'live' fields are probe "
                "evidence from the WordPress site and are historical once it is switched off.",
    "generated_from_capture": str(capture.relative_to(capture.parent.parent)),
    "origin": origin,
    "probed_live": not offline,
    "counts": {
        "sitemap_urls": len(entries),
        "pages": sum(1 for e in entries if e["type"] == "page"),
        "posts": sum(1 for e in entries if e["type"] == "post"),
        "extra_urls": len(extras),
        "shortlinks": len(shortlinks),
        "documents": len(document_entries),
    },
    "canonicalisation": canonicalisation,
    "urls": entries,
    "extra_urls": extras,
    "shortlinks": shortlinks,
    "redirects": redirects,
    "documents": document_entries,
}

output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
print(f"wrote {output.relative_to(capture.parent.parent)}: "
      f"{manifest['counts']['sitemap_urls']} sitemap URLs "
      f"({manifest['counts']['pages']} pages, {manifest['counts']['posts']} posts), "
      f"{manifest['counts']['extra_urls']} extra URLs, "
      f"{manifest['counts']['shortlinks']} shortlinks, "
      f"{manifest['counts']['documents']} documents")
PY
