/**
 * Landing page: one claim — it paints by writing code — shown with a real
 * paint program beside the picture it produced, then pieces from the gallery.
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router';
import type { PublicGalleryPiece } from '@code-monet/shared';
import { getApiUrl } from '../config';
import { PieceCard } from './site/PieceCard';
import { Icon } from './brand/Icon';
import { SiteFooter, SiteHeader } from './site/SiteChrome';
import { HeroPainting } from './homepage/HeroPainting';
import { SHOWCASE_PIECES } from './homepage/showcase';

const STEPS = [
  { title: 'Write', body: 'A Python painting program, pass by pass.' },
  { title: 'Paint', body: 'Run it. Strokes land in stages.' },
  { title: 'Look', body: 'Step back and critique the result.' },
  { title: 'Revise', body: 'Rewrite and paint the next version.' },
];

type Token = { kind: 'plain' | 'key' | 'str' | 'comment'; text: string };

/**
 * The program that rendered /how-it-works/sky-and-water.jpg
 * (public/how-it-works/sky-and-water.py, run with code_monet.paintlib.runner at 1600x1200).
 */
const PROGRAM: Token[][] = [
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.stage(' },
    { kind: 'str', text: '"ground"' },
    { kind: 'plain', text: '); ' },
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.ground(' },
    { kind: 'str', text: '"#d8c8a8"' },
    { kind: 'plain', text: ', weave=0.5)' },
  ],
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.stage(' },
    { kind: 'str', text: '"sky"' },
    { kind: 'plain', text: ')' },
  ],
  [
    { kind: 'plain', text: 'sky = ' },
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.rect_mask(0, 0, W, 520)' },
  ],
  [
    { kind: 'plain', text: 'guide = ' },
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.vgradient([(0, ' },
    { kind: 'str', text: '"#b98a8c"' },
    { kind: 'plain', text: '), (520, ' },
    { kind: 'str', text: '"#f1cf9f"' },
    { kind: 'plain', text: ')])' },
  ],
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.fill(sky, guide, alpha=0.8)' },
  ],
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.paint_region(sky, 1500, guide, angle=0.1, dry=0.5)' },
  ],
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.stage(' },
    { kind: 'str', text: '"water"' },
    { kind: 'plain', text: ')' },
  ],
  [
    { kind: 'plain', text: 'water = ' },
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.vgradient([(520, ' },
    { kind: 'str', text: '"#8aa0a6"' },
    { kind: 'plain', text: '), (H, ' },
    { kind: 'str', text: '"#40584b"' },
    { kind: 'plain', text: ')])' },
  ],
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.fill(1 - sky, water, alpha=0.9)' },
  ],
  [
    { kind: 'key', text: 'cv' },
    { kind: 'plain', text: '.paint_region(1 - sky, 1600, water, dry=0.3)' },
  ],
];

function ProgramCard(): React.ReactElement {
  return (
    <pre className="code-card" aria-label="A Code Monet painting program">
      <code>
        {PROGRAM.map((line, i) => (
          <React.Fragment key={i}>
            {line.map((token, j) =>
              token.kind === 'plain' ? (
                token.text
              ) : (
                <span key={j} className={`tok-${token.kind}`}>
                  {token.text}
                </span>
              )
            )}
            {'\n'}
          </React.Fragment>
        ))}
      </code>
    </pre>
  );
}

const PREVIEW_COUNT = 4;
const SHOWCASE_PREVIEW = SHOWCASE_PIECES.slice(0, PREVIEW_COUNT);

interface HomepageProps {
  /** Latest public pieces (SSR); fetched on the client otherwise. */
  initialGalleryPieces?: PublicGalleryPiece[];
}

/** Latest public pieces for "From the gallery" (null while loading). */
function useLatestPieces(initial: PublicGalleryPiece[] | undefined): PublicGalleryPiece[] | null {
  const [pieces, setPieces] = useState<PublicGalleryPiece[] | null>(initial ?? null);
  useEffect(() => {
    if (initial) return;
    const controller = new AbortController();
    fetch(`${getApiUrl()}/public/gallery?limit=${PREVIEW_COUNT}`, { signal: controller.signal })
      .then((res) => (res.ok ? (res.json() as Promise<PublicGalleryPiece[]>) : []))
      .then((data) => setPieces(data))
      .catch(() => {
        if (!controller.signal.aborted) setPieces([]);
      });
    return (): void => controller.abort();
  }, [initial]);
  return pieces;
}

export function Homepage({ initialGalleryPieces }: HomepageProps): React.ReactElement {
  const latest = useLatestPieces(initialGalleryPieces);
  return (
    <div className="site landing">
      <SiteHeader>
        <nav className="site-nav" aria-label="Sections">
          <Link to="/gallery">Gallery</Link>
          <a href="#how">How it works</a>
          <a href="#about">About</a>
        </nav>
      </SiteHeader>

      <main>
        <section className="landing-hero site-section">
          <div className="landing-hero-copy">
            <p className="mono-label">an autonomous painter</p>
            <h1 className="landing-title">
              It paints by <em>writing code.</em>
            </h1>
            <p className="landing-lede">
              Code Monet writes a painting program, runs it, steps back, and critiques what it sees.
              Then it paints again. You watch every stroke.
            </p>
            <div className="landing-actions">
              <Link to="/studio" className="btn btn-primary">
                Watch it paint <Icon name="arrow" />
              </Link>
              <Link to="/gallery" className="btn-link">
                Browse the gallery
              </Link>
            </div>
          </div>
          <div className="landing-hero-art">
            <HeroPainting />
          </div>
        </section>

        <section className="landing-how" id="how" aria-labelledby="how-title">
          <div className="site-section">
            <h2 className="mono-label" id="how-title">
              how it works
            </h2>
            <ol className="how-steps">
              {STEPS.map((step, i) => (
                <li key={step.title}>
                  <span className="how-step-n">{String(i + 1).padStart(2, '0')}</span>
                  <span className="how-step-title">{step.title}</span>
                  <span className="how-step-body">{step.body}</span>
                </li>
              ))}
            </ol>
            <div className="how-example">
              <ProgramCard />
              <figure className="how-figure">
                <div className="mat">
                  <img
                    src="/how-it-works/sky-and-water.jpg"
                    alt="Rose-to-gold sky over green water, painted in dabbed brushstrokes"
                    width={960}
                    height={720}
                    loading="lazy"
                  />
                </div>
                <figcaption className="mono-label">
                  → stages ground · sky · water — 3,103 strokes
                </figcaption>
              </figure>
            </div>
          </div>
        </section>

        <section className="site-section landing-gallery" aria-labelledby="gallery-title">
          <div className="section-head">
            <h2 id="gallery-title">From the gallery</h2>
            <Link to="/gallery" className="btn-link">
              See all <Icon name="arrow" />
            </Link>
          </div>
          <ul className="art-grid art-grid-4">
            {latest && latest.length > 0
              ? latest.slice(0, PREVIEW_COUNT).map((piece) => (
                  <li key={`${piece.user_id}/${piece.id}`}>
                    <PieceCard piece={piece} />
                  </li>
                ))
              : // No public pieces (yet): the curated showcase, pointing at the gallery.
                SHOWCASE_PREVIEW.map((piece) => (
                  <li key={piece.slug}>
                    <Link to="/gallery" className="art-card">
                      <div className="mat">
                        <img src={piece.image} alt={piece.description} loading="lazy" />
                      </div>
                      <span className="art-card-title">{piece.title}</span>
                    </Link>
                  </li>
                ))}
          </ul>
        </section>
      </main>

      <div id="about">
        <SiteFooter />
      </div>
    </div>
  );
}
