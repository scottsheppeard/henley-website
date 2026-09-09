// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

/**
 * thehenley.com.au — a static site.
 *
 * `site` is the production origin even when building for nonprod: canonical
 * URLs, the sitemap and JSON-LD all have to name the address the content is
 * published at, and nonprod is served `noindex` so nothing it emits competes.
 *
 * WordPress serves every page with a trailing slash and 301s the unslashed
 * form to it, so `trailingSlash: 'always'` plus `format: 'directory'` keeps
 * all 27 existing URLs byte-identical. Changing either would silently move
 * every address on the site.
 */
export default defineConfig({
  site: 'https://thehenley.com.au',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
  integrations: [
    sitemap({
      // /thank-you/ is the form confirmation and exists only to be redirected
      // to; indexing it invites it into results as a stray landing page.
      filter: (page) => !page.endsWith('/thank-you/'),
    }),
  ],
  image: {
    // Everything is local; no remote image domains are authorised.
    domains: [],
    remotePatterns: [],
  },
});
