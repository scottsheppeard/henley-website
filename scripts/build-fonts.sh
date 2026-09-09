#!/usr/bin/env bash
#
# build-fonts.sh — subset the brand kit's Avenir Next TTFs to Latin WOFF2.
#
# The kit ships desktop TTFs (556 glyphs, 372 codepoints, ~60 KB each) and no
# web format. Serving those directly would mean shipping a TrueType file no
# browser wants and paying for glyphs the site never renders. This produces the
# two faces the site uses, subset to the Latin range and Brotli-compressed.
#
# Rerun when the kit's fonts change. The outputs are committed, so an ordinary
# build — and the Docker build stage, which has no brand kit mounted — does not
# need fontTools or the kit.
#
# Usage: scripts/build-fonts.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="${HENLEY_BRAND_KIT:-/mnt/persistent/git/branding/henley}"
SRC="$KIT/05_Fonts"
OUT="$REPO_ROOT/src/fonts"
VENV="$REPO_ROOT/.venv-fonts"

# The Google Fonts "latin" subset: ASCII and Latin-1, the handful of Latin
# Extended-A characters real copy reaches for, combining marks, general
# punctuation (curly quotes, dashes, ellipsis), the currency and maths signs.
# Australian English needs nothing beyond this; resident names occasionally do,
# and Latin-1 covers the accents they use.
UNICODES="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,\
U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,\
U+2215,U+FEFF,U+FFFD"

[[ -d "$SRC" ]] || { echo "brand kit fonts not found: $SRC" >&2; exit 1; }

if [[ ! -x "$VENV/bin/pyftsubset" ]]; then
  echo "creating $VENV (fontTools + brotli) ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check fonttools brotli
fi

mkdir -p "$OUT"

subset() {
  local input="$1" output="$2"
  "$VENV/bin/pyftsubset" "$SRC/$input" \
    --output-file="$OUT/$output" \
    --flavor=woff2 \
    --unicodes="$UNICODES" \
    --layout-features='kern,liga,clig,calt' \
    --desubroutinize \
    --no-hinting \
    --drop-tables+=DSIG
  printf '  %-34s %7s bytes  (from %s bytes)\n' \
    "$output" "$(stat -c%s "$OUT/$output")" "$(stat -c%s "$SRC/$input")"
}

echo "subsetting to Latin WOFF2:"
subset AvenirNextLTPro-Regular.ttf avenir-next-400.woff2
subset AvenirNextLTPro-Demi.ttf    avenir-next-600.woff2

cat <<'EOF'

Done. src/styles/fonts.css declares these two faces; both are committed.

Licensing: the TTFs carry fsType=4 (preview & print embedding) and no licence
string. That bit governs embedding in documents and neither grants nor denies
web-font use, so it settles nothing either way. This build proceeds on Scott's
statement that a web licence came with the design package — see docs/decisions.md.
EOF
