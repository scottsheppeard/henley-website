import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';

/**
 * The RSS feed, built once and served at two addresses.
 *
 * WordPress published both `/feed/` (the site feed) and `/news/feed/` (the
 * category archive feed), both are live, both are in the migration manifest,
 * and both listed the same articles because the site has no other post type.
 * They stay two URLs with one body rather than one URL and a redirect: a feed
 * reader that has been polling `/news/feed/` since 2023 keeps working.
 *
 * The files that call this are named `index.xml.ts`, so they build to
 * `feed/index.xml` and `news/feed/index.xml`. That is what lets nginx answer
 * the directory address `/feed/` with XML — see the `index` directive in
 * deploy/nginx.conf. Named `feed.xml.ts` they would build to `/feed.xml` and
 * the address the world already has would 404.
 */
export async function buildFeed(site: URL | undefined) {
  const posts = (await getCollection('posts')).sort(
    (a, b) => b.data.date.getTime() - a.data.date.getTime(),
  );

  return rss({
    title: 'The Henley on Broadwater',
    description:
      'Life at The Henley on Broadwater, and guides to retirement living, aged care and downsizing on the Gold Coast.',
    site: site!,
    // `link` is the flat path the article is published at, not a /news/ one.
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.date,
      link: post.data.path,
    })),
    customData: '<language>en-au</language>',
  });
}
