# Replica of thehenley.com.au

A static copy of the WordPress site, served by nginx in place of WordPress so
the public sees no change. Spec: `docs/superpowers/specs/2026-09-16-legacy-replica-design.md`.

## Refresh the export

    forms/.venv/bin/python replica/export.py
    git diff --stat replica/

Review the diff before committing: it should show only what changed on the
live site since the last export.

## Tests

    forms/.venv/bin/python -m pytest replica/tests -q
