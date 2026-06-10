export interface ShowcasePiece {
  slug: string;
  title: string;
  description: string;
  image: string;
}

export const SHOWCASE_PIECES: ShowcasePiece[] = [
  {
    slug: 'the-great-wave',
    title: 'The Great Wave, After Hokusai',
    description: 'A breaking curl with clawed foam over a pale hollow; Fuji small through the trough.',
    image: '/showcase/the-great-wave.png',
  },
  {
    slug: 'poplars-at-dusk',
    title: 'Poplars at Dusk',
    description: 'Four poplars against a sunset river, their reflections broken by the warm light lane.',
    image: '/showcase/poplars-at-dusk.png',
  },
  {
    slug: 'the-lily-pond',
    title: 'The Lily Pond',
    description: 'Drifting pad clusters and pink blossoms on water that reflects an unseen sky.',
    image: '/showcase/the-lily-pond.png',
  },
  {
    slug: 'village-nocturne',
    title: 'Village Nocturne',
    description: 'A swirling night sky over lit windows, a steeple, and one cypress flame.',
    image: '/showcase/village-nocturne.png',
  },
  {
    slug: 'field-of-poppies',
    title: 'Field of Poppies',
    description: 'Red drifts down a green hillside; a rose parasol anchors the walkers in the heat.',
    image: '/showcase/field-of-poppies.png',
  },
];
