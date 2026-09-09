---
version: "test-fixture"
name: Fixture
description: >
  A miniature stand-in for the brand kit's DESIGN.md, holding one token of each
  shape the generator has to handle. Kept small on purpose: the snapshot below
  it is meant to be read in a diff, so a real change to the generator's output
  is obvious rather than buried in 174 lines.

colors:
  primary: "#0E5B70"
  on-primary: "#FFFFFF"
  surface: "#FAF9F6"
  on-surface: "#1E2427"
  surface-raised: "#FFFFFF"
  surface-sunk: "#F5F1EA"
  on-surface-secondary: "#4B5458"
  dark-surface: "#083B4A"
  dark-on-surface: "#F5F1EA"
  primary-hover: "#083B4A"
  primary-active: "#072C38"
  chart-1: "#0E5B70"
  cortex-primary: "#0E5B70"
  henley-care-ink: "#183145"

typography:
  body-md:
    fontFamily: "Avenir Next LT Pro, Calibri, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  button-label:
    fontFamily: "Avenir Next LT Pro, Calibri, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.43
    letterSpacing: "0.02em"
  title-lg:
    fontFamily: "Avenir Next LT Pro, Calibri, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.33
    letterSpacing: "0em"
  label-md:
    fontFamily: "Avenir Next LT Pro, Calibri, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.43
    letterSpacing: "0em"
  code-sm:
    fontFamily: "ui-monospace, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0em"

rounded:
  md: "4px"
  lg: "8px"

spacing:
  base: "4px"
  space-xs: "8px"
  space-sm: "12px"
  space-lg: "24px"
  touch-target: "44px"

components:
  page:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
  page-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    typography: "{typography.body-md}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-label}"
    rounded: "{rounded.md}"
    padding: "{spacing.space-sm}"
    height: "{spacing.touch-target}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-label}"
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-label}"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.primary}"
    typography: "{typography.button-label}"
    rounded: "{rounded.md}"
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.button-label}"
    padding: "{spacing.space-xs}"
  input:
    backgroundColor: "{colors.surface-sunk}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.space-sm}"
    height: "{spacing.touch-target}"
  card:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    padding: "{spacing.space-lg}"
  card-title:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface}"
    typography: "{typography.title-lg}"
  nav-top:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface-secondary}"
    typography: "{typography.label-md}"
    height: "64px"
  nav-link-active:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.primary}"
    typography: "{typography.label-md}"
  table-row:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
---

# Fixture

Everything above the second `---` is what `scripts/build-tokens.ts` reads.
This prose exists to prove the generator stops at the front-matter.

`table-row` is here to prove the opposite of the component allow-list: the kit
defines it, the site does not use it, and it must not appear in the output.
