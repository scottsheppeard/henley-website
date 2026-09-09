/**
 * build-tokens.ts — generate src/styles/tokens.css from the brand kit.
 *
 * The canonical design tokens live in the brand repo, in the YAML front-matter
 * of /mnt/persistent/git/branding/henley/DESIGN.md. This turns the slice of them
 * the website uses into CSS custom properties, so the site never restates a
 * colour or a type scale and a change to the kit reaches the site by rebuilding
 * rather than by hand-editing stylesheets.
 *
 * Two rules make that worth having:
 *
 *   1. References resolve to `var(--other-token)`, never to the literal value.
 *      A component alias that inlined `#0E5B70` would be a copy that silently
 *      goes stale; pointing at `--color-primary` keeps one definition and lets
 *      a media query or a page-level override reach every alias built on it.
 *   2. A reference that names something the kit does not define is a hard
 *      error. Silently emitting an empty value would ship a page with an
 *      invisible button.
 *
 * The kit also carries tokens for Cortex, Henley Care and chart palettes. They
 * are deliberately skipped: this site has no charts and is not those brands.
 *
 * Run: npm run tokens  (also runs automatically before build and check)
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { load } from 'js-yaml';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DESIGN_MD = process.env.HENLEY_DESIGN_MD
  ?? '/mnt/persistent/git/branding/henley/DESIGN.md';
const OUTPUT = resolve(REPO_ROOT, 'src/styles/tokens.css');

/** Colour groups that belong to other brands or to UI this site does not have. */
const SKIP_COLOR = /^(cortex-|henley-care-|chart-)/;

/**
 * The component aliases the site actually consumes. The kit defines ~37; most
 * are for Cortex's application UI (tables, modals, badges, alerts) and would be
 * dead CSS here. Add a name when a component starts using it — the generator
 * throws if a name is not in the kit, so this list cannot rot silently.
 */
const COMPONENTS = [
  'page',
  'page-dark',
  'button-primary',
  'button-primary-hover',
  'button-primary-active',
  'button-secondary',
  'button-ghost',
  'input',
  'card',
  'card-title',
  'nav-top',
  'nav-link-active',
  'footer',
] as const;

/** Names allowed to be absent from the kit. `footer` has no recipe there yet. */
const OPTIONAL_COMPONENTS = new Set<string>(['footer']);

/** Component property name in the kit -> the CSS custom property suffix. */
const COMPONENT_PROPS: Record<string, string> = {
  backgroundColor: 'bg',
  textColor: 'text',
  typography: 'font',
  rounded: 'radius',
  padding: 'padding',
  height: 'height',
  width: 'width',
};

interface TypeScale {
  fontFamily: string;
  fontSize: string;
  fontWeight: number;
  lineHeight: number;
  letterSpacing: string;
}

interface Design {
  version?: string;
  colors: Record<string, string>;
  typography: Record<string, TypeScale>;
  rounded: Record<string, string>;
  spacing: Record<string, string>;
  components: Record<string, Record<string, string>>;
}

/** Pull the YAML front-matter out of a Markdown file. */
function frontMatter(markdown: string): string {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(markdown);
  if (!match?.[1]) {
    throw new Error(`${DESIGN_MD}: no YAML front-matter found at the top of the file`);
  }
  return match[1];
}

/**
 * Turn `{colors.primary}` into `var(--color-primary)`, checking as we go that
 * the kit really defines it. Values with no reference are passed through.
 */
function resolveReference(value: string, design: Design, context: string): string {
  const match = /^\{([a-z]+)\.([A-Za-z0-9-]+)\}$/.exec(value);
  if (!match) return value;

  const [, group, name] = match as unknown as [string, string, string];
  const exists =
    (group === 'colors' && name in design.colors) ||
    (group === 'typography' && name in design.typography) ||
    (group === 'rounded' && name in design.rounded) ||
    (group === 'spacing' && name in design.spacing);

  if (!exists) {
    throw new Error(
      `${context}: "${value}" does not resolve — the brand kit has no ${group}.${name}. ` +
        `Fix the reference in DESIGN.md, or the token name here.`,
    );
  }

  if (group === 'spacing') return `var(${spacingToken(name)})`;
  const prefix = { colors: 'color', typography: 'type', rounded: 'radius' }[group];
  return `var(--${prefix}-${name})`;
}

/**
 * Most spacing keys in the kit are already written `space-lg`, `space-2xl`;
 * two (`base`, `touch-target`) are not. Strip the redundant prefix so the CSS
 * reads `--space-lg` rather than `--space-space-lg`, and keep the untouched
 * names as they are. Both the emitter and the reference resolver go through
 * here, so the two can never disagree about what a spacing token is called.
 */
function spacingToken(name: string): string {
  return `--space-${name.replace(/^space-/, '')}`;
}

function section(title: string, note: string, lines: string[]): string {
  return [`  /* ${title} — ${note} */`, ...lines.map((l) => `  ${l}`), ''].join('\n');
}

export function generate(markdown: string): string {
  const design = load(frontMatter(markdown)) as Design;

  for (const key of ['colors', 'typography', 'rounded', 'spacing', 'components'] as const) {
    if (!design[key] || typeof design[key] !== 'object') {
      throw new Error(`${DESIGN_MD}: front-matter has no "${key}" map`);
    }
  }

  const colors = Object.entries(design.colors)
    .filter(([name]) => !SKIP_COLOR.test(name))
    .map(([name, value]) => `--color-${name}: ${value};`);

  const skipped = Object.keys(design.colors).filter((name) => SKIP_COLOR.test(name)).length;

  // Families first, so every scale can point at one declaration.
  const families = new Map<string, string>();
  for (const scale of Object.values(design.typography)) {
    if (!families.has(scale.fontFamily)) {
      families.set(scale.fontFamily, families.size === 0 ? 'sans' : `alt-${families.size}`);
    }
  }
  // The monospace scale is the only alternate the kit carries; name it usefully.
  for (const [family, alias] of families) {
    if (alias !== 'sans' && /mono/i.test(family)) families.set(family, 'mono');
  }

  const familyLines = [...families].map(([family, alias]) => `--family-${alias}: ${family};`);

  const typography: string[] = [];
  for (const [name, scale] of Object.entries(design.typography)) {
    const family = `var(--family-${families.get(scale.fontFamily)})`;
    // The CSS `font` shorthand carries weight, size, line-height and family in
    // one custom property, so a rule is `font: var(--type-body-md)`.
    // letter-spacing is not part of the shorthand and stays its own token.
    typography.push(
      `--type-${name}: ${scale.fontWeight} ${scale.fontSize}/${scale.lineHeight} ${family};`,
      `--type-${name}-size: ${scale.fontSize};`,
      `--type-${name}-letter-spacing: ${scale.letterSpacing};`,
    );
  }

  const spacing = Object.entries(design.spacing).map(([name, value]) => `${spacingToken(name)}: ${value};`);
  const rounded = Object.entries(design.rounded).map(([name, value]) => `--radius-${name}: ${value};`);

  const components: string[] = [];
  for (const name of COMPONENTS) {
    const recipe = design.components[name];
    if (!recipe) {
      if (OPTIONAL_COMPONENTS.has(name)) continue;
      throw new Error(
        `the brand kit has no component "${name}" — remove it from COMPONENTS in ` +
          `scripts/build-tokens.ts, or add the recipe to DESIGN.md`,
      );
    }
    for (const [property, value] of Object.entries(recipe)) {
      const suffix = COMPONENT_PROPS[property];
      if (!suffix) continue; // a property the site has no use for
      components.push(
        `--${name}-${suffix}: ${resolveReference(value, design, `components.${name}.${property}`)};`,
      );
    }
  }

  const header = `/*
 * GENERATED FILE — DO NOT EDIT.
 *
 * Written by scripts/build-tokens.ts from the YAML front-matter of
 * ${DESIGN_MD}
 * (brand kit version: ${design.version ?? 'unspecified'}).
 *
 * To change a colour, a type scale or a component recipe, change the brand kit
 * and rebuild. To expose a token the kit already defines, add its name to
 * COMPONENTS in the generator. This file is gitignored for that reason.
 */
:root {
`;

  return (
    header +
    section('Colour', `${colors.length} tokens; ${skipped} Cortex/Henley Care/chart tokens skipped`, colors) +
    section('Type families', 'one declaration per family, referenced by every scale below', familyLines) +
    section('Type scales', 'font shorthand: weight size/line-height family', typography) +
    section('Spacing', '4px grid', spacing) +
    section('Radius', '4px on buttons and inputs, 8px on cards', rounded) +
    section('Components', 'aliases the site consumes, pointing at the tokens above', components) +
    '}\n'
  );
}

function main(): void {
  const css = generate(readFileSync(DESIGN_MD, 'utf8'));
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, css);
  const count = (css.match(/^\s+--/gm) ?? []).length;
  console.log(`tokens: wrote ${OUTPUT.replace(`${REPO_ROOT}/`, '')} (${count} custom properties)`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
