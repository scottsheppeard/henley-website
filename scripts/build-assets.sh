#!/usr/bin/env bash
#
# build-assets.sh — bring brand kit artwork and photography into the site.
#
# The kit is the source of truth and is not vendored wholesale; only what the
# site actually renders is copied in, so a reader can see at a glance which
# brand assets this site depends on. Rerun after the kit changes.
#
# Usage: scripts/build-assets.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="${HENLEY_BRAND_KIT:-/mnt/persistent/git/branding/henley}"

[[ -d "$KIT" ]] || { echo "brand kit not found: $KIT" >&2; exit 1; }

mkdir -p "$REPO_ROOT/src/assets" "$REPO_ROOT/src/images"

# ── Wordmark ────────────────────────────────────────────────────────────────
#
# The kit's currentColor SVG carries a <style> block containing a `:root`
# selector. Inlined into a page that rule is not scoped to the SVG at all — it
# sets the colour of the entire document. Strip it: the whole point of the
# currentColor variant is that the page decides the colour.
python3 - "$KIT/02_Logos/Vector_SVG/logo-vector-fill-currentcolor.svg" \
          "$REPO_ROOT/src/assets/wordmark.svg" <<'PY'
import re
import sys

source, target = sys.argv[1], sys.argv[2]
svg = open(source, encoding="utf-8").read()

# Drop the XML prolog, the <defs><style> block (see above) and the <title>;
# the component supplies its own accessible name.
svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
svg = re.sub(r"<defs>.*?</defs>\s*", "", svg, flags=re.S)
svg = re.sub(r"<title>.*?</title>\s*", "", svg, flags=re.S)
svg = svg.replace(' id="Layer_1" data-name="Layer 1"', "")

# The stripped <style> also defined .cls-1 { fill-rule: evenodd }. Put it back
# as an attribute so the artwork still renders correctly without any CSS.
svg = svg.replace('class="cls-1"', 'fill-rule="evenodd"')

assert ":root" not in svg, "a :root rule survived; it would recolour the page"
assert "currentColor" in svg, "the wordmark must inherit its colour from the page"

open(target, "w", encoding="utf-8").write(svg.strip() + "\n")
print(f"  wordmark.svg  {len(svg)} bytes")
PY

# ── Photography ─────────────────────────────────────────────────────────────
#
# The four approved 1920px web images. Astro's image pipeline does the
# resizing, AVIF/WebP encoding and srcset, so these are copied at full size
# and never hand-optimised.
echo "photography:"
for name in Henley-entry-web Henley-front-web Henley-vertical-web henley-wide-web; do
  source="$KIT/06_Imagery/Photography/$name.jpg"
  target="$REPO_ROOT/src/images/${name,,}.jpg"
  cp "$source" "$target"
  printf '  %-26s %8s bytes\n' "$(basename "$target")" "$(stat -c%s "$target")"
done

echo
echo "Done. Renders in the kit's Renovation_Renders/ are deliberately not copied:"
echo "they must be labelled as renders wherever they appear, which is a content"
echo "decision rather than an asset one (docs/brief.md, claims held for confirmation)."
