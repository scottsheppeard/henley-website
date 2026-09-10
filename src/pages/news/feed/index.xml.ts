import type { APIContext } from 'astro';
import { buildFeed } from '../../../feed.ts';

/**
 * The archive feed, at /news/feed/ — the same body as /feed/, because
 * WordPress published both and readers are subscribed to both.
 */
export const GET = ({ site }: APIContext) => buildFeed(site);
