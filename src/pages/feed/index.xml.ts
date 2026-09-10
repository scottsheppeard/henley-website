import type { APIContext } from 'astro';
import { buildFeed } from '../../feed.ts';

/** The site feed, at /feed/. See src/feed.ts for why it is named index.xml. */
export const GET = ({ site }: APIContext) => buildFeed(site);
