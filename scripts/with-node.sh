#!/usr/bin/env bash
#
# with-node.sh — run a command with this repo's Node, whatever the caller's PATH.
#
#   scripts/with-node.sh npm run check
#   scripts/with-node.sh npm ci
#
# The host's default Node is 20 and has to stay that way: raceimages-webapp's
# node_modules holds native modules (sharp) built against its ABI. This repo
# needs 22 — Astro 7 requires >= 22.12 — so the version is pinned per-repo in
# .node-version and selected here through fnm rather than by putting 22 on the
# PATH globally.
#
# Interactive shells get the same thing from fnm's --use-on-cd hook in ~/.bashrc.
# This wrapper is for everything that is not an interactive shell: the stream
# tooling's landing checks, agent shells, cron, CI. It resolves the version
# itself, so it does not care whether fnm has been loaded into the environment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$REPO_ROOT/.node-version"

[[ -f "$VERSION_FILE" ]] || {
  echo "with-node.sh: no .node-version at $VERSION_FILE" >&2
  exit 1
}
[[ $# -gt 0 ]] || {
  echo "usage: scripts/with-node.sh <command> [args...]" >&2
  exit 2
}

export FNM_DIR="${FNM_DIR:-$HOME/.local/share/fnm}"
FNM="$(command -v fnm || true)"
[[ -n "$FNM" ]] || FNM="$HOME/.local/bin/fnm"

if [[ ! -x "$FNM" ]]; then
  cat >&2 <<EOF
with-node.sh: fnm not found at \$FNM_DIR=$FNM_DIR or on PATH.

This repo needs Node $(cat "$VERSION_FILE") and the host default is $(node --version 2>/dev/null || echo "not installed").
Install fnm into ~/.local/bin and the version this repo pins:

  fnm install \$(cat .node-version)

See docs/decisions.md, "Node version".
EOF
  exit 127
fi

exec "$FNM" exec --using="$VERSION_FILE" -- "$@"
