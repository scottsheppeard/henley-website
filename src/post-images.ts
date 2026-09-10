import type { ImageMetadata } from 'astro';

import advantage from './images/post-advantage.jpg';
import agedCareApproach from './images/post-aged-care-approach.jpg';
import artClasses from './images/post-art-classes.jpg';
import artPaints from './images/post-art-paints.jpg';
import artTable from './images/post-art-table.jpg';
import careTailored from './images/post-care-tailored.jpg';
import connections from './images/post-connections.jpg';
import costs from './images/post-costs.jpg';
import dietitian from './images/post-dietitian.jpg';
import dietitianPlatters from './images/post-dietitian-platters.jpg';
import dietitianTalk from './images/post-dietitian-talk.jpg';
import downsizing from './images/post-downsizing.jpg';
import fashion from './images/post-fashion.jpg';
import fashionGreen from './images/post-fashion-green.jpg';
import fashionPresenter from './images/post-fashion-presenter.jpg';
import fashionThree from './images/post-fashion-three.jpg';
import health from './images/post-health.jpg';
import highTea from './images/post-high-tea.jpg';
import highTeaGroup from './images/post-high-tea-group.jpg';
import highTeaWindow from './images/post-high-tea-window.jpg';
import homeCare from './images/post-home-care.jpg';
import lego from './images/post-lego.jpg';
import legoBigBen from './images/post-lego-bigben.jpg';
import legoTaj from './images/post-lego-taj.jpg';
import legoTypewriter from './images/post-lego-typewriter.jpg';
import questions from './images/post-questions.jpg';

interface Photo {
  image: ImageMetadata;
  alt: string;
  caption: string;
}

interface PostImages {
  /** Runs above the article and as the thumbnail on the index. */
  header: Photo;
  /**
   * The photographs that ran inside the post on the old site.
   *
   * They are here rather than in the Markdown because the capture did not
   * preserve them usefully: five posts stored WordPress's lazy-load `data:`
   * placeholder instead of a file, and the two that kept real references
   * pointed at a 4032px original and a 225px thumbnail, both with empty alt
   * text. Held here they get alt text, a caption, and the image pipeline.
   */
  gallery?: Photo[];
}

/**
 * A photograph for every article, keyed by slug.
 *
 * There is no fallback and the article page asserts the entry exists: a post
 * added later without an image should fail the build rather than publish a
 * silent gap in the index. Sources and the consent position for each of these
 * are recorded in docs/decisions.md.
 */
export const POST_IMAGES: Record<string, PostImages> = {
  amazingartists: {
    header: {
      image: lego,
      alt: 'A resident beside a grand piano built from Lego in the lounge',
      caption: 'Cora with the piano — which plays',
    },
    gallery: [
      { image: legoTypewriter, alt: 'A typewriter built from Lego', caption: 'The typewriter' },
      { image: legoTaj, alt: 'The Taj Mahal built from Lego', caption: 'The Taj Mahal' },
      { image: legoBigBen, alt: 'Big Ben and the Houses of Parliament built from Lego, on a table in the lounge', caption: 'Big Ben and Parliament' },
    ],
  },

  art_classes: {
    header: {
      image: artClasses,
      alt: 'Three residents smiling over their paintings at the art class',
      caption: 'Friday morning, and the week’s work',
    },
    gallery: [
      { image: artTable, alt: 'Residents painting around a long table in the lounge', caption: 'The long table' },
      { image: artPaints, alt: 'Three residents working with paints at the art class', caption: 'Mid-class' },
    ],
  },

  dietician: {
    header: {
      image: dietitian,
      alt: 'The dietitian talking with a resident in the lounge',
      caption: 'Jessica, at the healthy morning tea',
    },
    gallery: [
      { image: dietitianTalk, alt: 'The dietitian presenting “Eating well for life” on the lounge screen', caption: 'Eating well for life' },
      { image: dietitianPlatters, alt: 'Platters of sandwiches and sliders laid out for morning tea', caption: 'Morning tea, prepared by the kitchen' },
    ],
  },

  'fashionista-the-henley': {
    header: {
      image: fashion,
      alt: 'A presenter showing yellow outfits to residents seated in the lounge',
      caption: 'The parade, in the lounge',
    },
    gallery: [
      { image: fashionGreen, alt: 'A model in a green outfit walking through the lounge', caption: 'Margot Mott’s designs' },
      { image: fashionPresenter, alt: 'Two residents talking with the presenter at the fashion parade', caption: 'Front row' },
      { image: fashionThree, alt: 'Three residents smiling at the fashion parade', caption: 'The point of the afternoon' },
    ],
  },

  'how-it-works-the-costs-of-retirement-living': {
    header: {
      image: costs,
      alt: 'A display apartment living and dining room with the Broadwater through floor-to-ceiling glass',
      caption: 'A display apartment at The Henley',
    },
  },

  internationalwomensday: {
    header: {
      image: highTea,
      alt: 'Two residents at high tea against a patterned wall in the bistro',
      caption: 'High tea in the bistro',
    },
    gallery: [
      { image: highTeaWindow, alt: 'Residents at high tea at the bistro window', caption: 'At the window' },
      { image: highTeaGroup, alt: 'A group of residents and a staff member at high tea', caption: 'The whole table' },
    ],
  },

  'making-the-most-of-your-homecare-package': {
    header: {
      image: homeCare,
      alt: 'A staff member serving lunch to a couple in a household kitchen and dining area',
      caption: 'Support in the household at The Henley',
    },
  },

  'retirement-living-how-to-make-the-connections-that-count': {
    header: {
      image: connections,
      alt: 'Residents gathered around a roulette table at a casino night',
      caption: 'Casino night — one of the ways people meet here',
    },
  },

  'the-henley-advantage-its-about-making-life-easier-for-you': {
    header: {
      image: advantage,
      alt: 'Two residents having tea together in a lounge',
      caption: 'An afternoon at The Henley',
    },
  },

  'the-henley-private-aged-care-its-our-approach-that-sets-us-apart': {
    header: {
      image: agedCareApproach,
      alt: 'A carer laughing with a resident in her room',
      caption: 'In the private aged care household',
    },
  },

  'the-upside-of-downsizing-and-5-tips-to-make-the-move-easier-for-retirees': {
    header: {
      image: downsizing,
      alt: 'An apartment balcony looking north over the Broadwater towards the Spit',
      caption: 'What you downsize to',
    },
  },

  'top-10-questions-to-ask-your-sales-manager': {
    header: {
      image: questions,
      alt: 'Residents chatting in the lounge beside the piano',
      caption: 'The lounge at The Henley',
    },
  },

  'whatever-care-you-need-we-can-provide-it': {
    header: {
      image: careTailored,
      alt: 'A resident reading on a sofa beside the balcony door in her suite',
      caption: 'A private suite in the household',
    },
  },

  'why-health-is-the-best-gift-you-can-give-yourself': {
    header: {
      image: health,
      alt: 'Residents and a trainer using equipment in The Henley Health Club',
      caption: 'The health club',
    },
  },

  'why-retirement-living-is-good-for-you': {
    header: {
      image: costs,
      alt: 'A display apartment living and dining room with the Broadwater through floor-to-ceiling glass',
      caption: 'A display apartment at The Henley',
    },
  },
};
