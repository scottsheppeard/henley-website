import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'zod';

/**
 * The posts collection.
 *
 * One typed source for the three things that have to agree about the articles:
 * the index at /news/, the two feeds, and the article pages themselves. Before
 * this they would have been three globs with three ideas of what a post is, and
 * the failure mode is silent — a post that appears in the feed and not the
 * index, or vice versa, and nobody notices for a month.
 *
 * `news.md` is excluded by the pattern. It is the *captured index page*, not an
 * article: the old site's /news/ with its list of post titles. It stays in the
 * directory as the record of what that page said, and the real index is
 * generated from the collection.
 *
 * The schema is strict about what the site consumes and deliberately loose
 * about `legacy`, which is the migration's archive of what WordPress published
 * — shapes vary across the capture and nothing renders from it. Making it
 * strict would mean the build fails over a field no page reads.
 */
const posts = defineCollection({
  loader: glob({
    base: './src/content/posts',
    pattern: ['*.md', '!news.md'],
  }),
  schema: z.object({
    /**
     * `reviewed` means a person has been through the file and
     * scripts/export-content.ts must leave it alone. Every published post is
     * reviewed: a re-export would otherwise undo the corrections Stage 3 made,
     * starting with twenty-one suites.
     */
    status: z.enum(['needs-review', 'reviewed']),

    /**
     * The URL this post is published at — a flat path with no /news/ prefix,
     * because that is where WordPress served it and where the links, the
     * shortlink redirects and the search results all point.
     */
    path: z.string().startsWith('/').endsWith('/'),

    type: z.literal('post'),
    title: z.string(),

    /**
     * Required, unlike the captured front matter where it was usually null:
     * this is both the meta description and the extract on the index, and a
     * post without one leaves a hole in the index and a generated snippet in
     * search results. All fifteen were written during Stage 3.
     */
    description: z.string().min(1),

    /**
     * Publication date, as WordPress recorded it. Honest dates, per the brief.
     * Parsed here so the index, the feeds and the articles all sort and format
     * one Date rather than three interpretations of a string.
     */
    date: z.string().transform((value) => new Date(value)),

    ogImage: z.string().nullable().optional(),
    legacy: z.record(z.string(), z.unknown()).optional(),
  }),
});

export const collections = { posts };
