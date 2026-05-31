export interface ShowcasePiece {
  slug: string;
  title: string;
  description: string;
  image: string;
}

export const SHOWCASE_PIECES: ShowcasePiece[] = [
  {
    slug: 'harbor-light-low-tide',
    title: 'Harbor Light, Low Tide',
    description: 'Moored boats, dark quay masses, and a cool reflective channel at sunset.',
    image: '/showcase/harbor-light-low-tide.png',
  },
  {
    slug: 'glasshouse-nocturne',
    title: 'Glasshouse Nocturne',
    description: 'Night garden glass glowing through violet-blue air and deep foliage.',
    image: '/showcase/glasshouse-nocturne.png',
  },
  {
    slug: 'orchard-after-rain',
    title: 'Orchard After Rain',
    description: 'Wet orchard rows bending around a pale path after rainfall.',
    image: '/showcase/orchard-after-rain.png',
  },
  {
    slug: 'cinder-ridge',
    title: 'Cinder Ridge',
    description: 'A red cinder ridge under cold sky and ember-lit contours.',
    image: '/showcase/cinder-ridge.png',
  },
  {
    slug: 'citrus-blue-table',
    title: 'Citrus on the Blue Table',
    description: 'Citrus, glass, and folded cloth on a deep blue table.',
    image: '/showcase/citrus-blue-table.png',
  },
];
