/**
 * Code Monet - Analog Atelier Homepage
 * An artist's studio aesthetic inspired by Monet's world
 */

import React, { useEffect } from 'react';
import { Link } from 'react-router';
import { HeroPainting } from './homepage/index';
import { SHOWCASE_PIECES } from './homepage/showcase';

interface HomepageProps {
  onEnter: () => void;
}

export function Homepage({ onEnter }: HomepageProps): React.ReactElement {
  const [mounted, setMounted] = React.useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className={`homepage ${mounted ? 'mounted' : ''}`}>
      {/* Hero section - full viewport */}
      <section className="hero-section">
        <div className="hero-content">
          <div className="hero-text">
            <div className="title-container">
              <span className="title-prefix">Introducing</span>
              <h1 className="hero-title">
                <span className="title-word code">Code</span>
                <span className="title-word monet">Monet</span>
              </h1>
            </div>

            <p className="hero-tagline">An autonomous AI artist</p>

            <p className="hero-description">
              Watch artificial intelligence create original artwork in real-time. No prompts. No
              guidance. Just pure, autonomous creativity — stroke by stroke, thought by thought.
            </p>

            <div className="cta-container">
              <button className="cta-primary" onClick={onEnter}>
                <span>Enter the Studio</span>
                <svg className="cta-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M5 12h14M12 5l7 7-7 7" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
              <a href="#watch" className="cta-secondary">
                Watch it paint
              </a>
            </div>
          </div>

          <div className="hero-canvas">
            <HeroPainting />
          </div>
        </div>
      </section>

      {/* How it works - Editorial narrative */}
      <section className="how-section" id="watch">
        <div className="section-content">
          <h2 className="section-title">
            <span className="title-accent" />
            The Creative Process
          </h2>

          <div className="process-narrative">
            <div className="process-step">
              <div className="step-marker">
                <div className="step-number">I</div>
                <div className="step-line" />
              </div>
              <div className="step-content">
                <h3>Observe</h3>
                <p>
                  The artist examines its canvas with patient attention, understanding the marks
                  already made and sensing the possibilities that remain. Like Monet studying the
                  light on his water lilies, it considers composition, balance, and the emotional
                  weight of empty space.
                </p>
              </div>
            </div>

            <div className="process-step">
              <div className="step-marker">
                <div className="step-number">II</div>
                <div className="step-line" />
              </div>
              <div className="step-content">
                <h3>Contemplate</h3>
                <p>
                  In moments of visible thought, the AI reasons about color theory, movement, and
                  meaning. It shares its creative deliberations in real-time — not as explanation,
                  but as an invitation into the artistic mind at work.
                </p>
              </div>
            </div>

            <div className="process-step">
              <div className="step-marker">
                <div className="step-number">III</div>
                <div className="step-line" />
              </div>
              <div className="step-content">
                <h3>Create</h3>
                <p>
                  With intention behind every gesture, the artist writes code that becomes
                  brushstrokes on canvas. Each mark is deliberate — placed not by chance or
                  algorithm, but by something closer to aesthetic judgment.
                </p>
              </div>
            </div>

            <div className="process-step">
              <div className="step-marker">
                <div className="step-number">IV</div>
                <div className="step-line" />
              </div>
              <div className="step-content">
                <h3>Evolve</h3>
                <p>
                  Each piece informs the next. The artist develops preferences, refines its visual
                  language, builds on what came before. Over time, a style emerges — not programmed,
                  but discovered through the act of making.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* About the Artist */}
      <section className="about-section about-artist">
        <div className="section-content">
          <div className="about-layout">
            <div className="about-visual">
              <div className="artist-avatar">
                <svg viewBox="0 0 120 120" className="avatar-svg">
                  <defs>
                    <linearGradient id="brushGrad1" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#e8c98a" />
                      <stop offset="100%" stopColor="#1f4d34" />
                    </linearGradient>
                    <linearGradient id="brushGrad2" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#5a9a70" />
                      <stop offset="100%" stopColor="#6a8a78" />
                    </linearGradient>
                    <linearGradient id="brushGrad3" x1="0%" y1="100%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#9b4f45" />
                      <stop offset="100%" stopColor="#90b0a0" />
                    </linearGradient>
                  </defs>
                  {/* Abstract brush strokes representing the AI artist */}
                  <path
                    d="M 20 80 Q 40 40, 70 60 T 100 50"
                    fill="none"
                    stroke="url(#brushGrad1)"
                    strokeWidth="8"
                    strokeLinecap="round"
                    opacity="0.9"
                  />
                  <path
                    d="M 30 30 Q 60 50, 90 35"
                    fill="none"
                    stroke="url(#brushGrad2)"
                    strokeWidth="6"
                    strokeLinecap="round"
                    opacity="0.8"
                  />
                  <path
                    d="M 15 60 Q 45 80, 80 90"
                    fill="none"
                    stroke="url(#brushGrad3)"
                    strokeWidth="5"
                    strokeLinecap="round"
                    opacity="0.7"
                  />
                  <circle cx="55" cy="55" r="3" fill="#1f4d34" opacity="0.6" />
                </svg>
              </div>
            </div>
            <div className="about-text">
              <h2 className="section-title">
                <span className="title-accent" />
                About the Artist
              </h2>
              <p className="about-intro">
                Code Monet is an autonomous AI artist powered by Claude, Anthropic&apos;s most
                capable model.
              </p>
              <p>
                Unlike typical AI art tools that generate images from prompts, Code Monet operates
                independently — deciding what to create, when to create it, and how each piece
                should evolve. It writes actual drawing code, executing brushstrokes one at a time
                while sharing its creative reasoning in real-time.
              </p>
              <p>
                The artist maintains persistent memory across sessions, developing artistic
                preferences and building on previous work. Each piece is genuinely novel — not
                retrieved from a database, but conceived and executed in the moment.
              </p>
              <p className="about-highlight">
                This is not image generation. This is artificial creativity.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* About the Creator */}
      <section className="about-section about-creator">
        <div className="section-content">
          <div className="about-layout reverse">
            <div className="about-text">
              <h2 className="section-title">
                <span className="title-accent" />
                About the Creator
              </h2>
              <p className="about-intro">
                Built by Daniel Fenton, a software engineer exploring the boundaries of AI
                creativity.
              </p>
              <p>
                Code Monet began as an experiment: what happens when you give an AI the tools to
                create art autonomously, rather than on demand? The result is a system that blurs
                the line between tool and artist — raising questions about creativity, intention,
                and what it means to make something beautiful.
              </p>
              <p>
                The project is built with the Claude Agent SDK, FastAPI, React Native, and a lot of
                curiosity about where human and machine creativity intersect.
              </p>
              <div className="creator-links">
                <a
                  href="https://github.com/dmfenton"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="creator-link"
                >
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                  </svg>
                  GitHub
                </a>
                <a
                  href="https://linkedin.com/in/dmfenton"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="creator-link"
                >
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                  </svg>
                  LinkedIn
                </a>
              </div>
            </div>
            <div className="about-visual">
              <div className="creator-avatar">
                <div className="avatar-placeholder">
                  <span>DF</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Gallery preview */}
      <section className="gallery-section">
        <div className="section-content">
          <h2 className="section-title">
            <span className="title-accent" />
            Public Showcase
          </h2>
          <p className="section-subtitle">Five agent-made studies selected for the public showcase</p>

          <div className="gallery-wall showcase-wall">
            {SHOWCASE_PIECES.map((piece, i) => (
              <a
                key={piece.slug}
                href={piece.image}
                target="_blank"
                rel="noopener noreferrer"
                className="gallery-wall-link"
                aria-label={`Open ${piece.title}`}
              >
                <article
                  className="gallery-item showcase-item"
                  style={{ animationDelay: `${i * 0.15}s` }}
                >
                  <div className="gallery-frame">
                    <img
                      src={piece.image}
                      alt={piece.title}
                      className="gallery-artwork gallery-showcase-image"
                    />
                  </div>
                  <span className="gallery-label" title={piece.title}>
                    {piece.title}
                  </span>
                  <p className="showcase-description">{piece.description}</p>
                </article>
              </a>
            ))}
          </div>

          <Link to="/gallery" className="gallery-cta">
            View full gallery
          </Link>
        </div>
      </section>

      {/* Final CTA */}
      <section className="final-section">
        <div className="final-content">
          <h2>Ready to witness creativity unfold?</h2>
          <button className="cta-final" onClick={onEnter}>
            <span>Enter the Studio</span>
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="homepage-footer">
        <div className="footer-content">
          <div className="footer-brand">
            <svg className="footer-logo" viewBox="0 0 40 40">
              <path
                d="M 10 30 Q 20 10, 30 30"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
              <circle cx="20" cy="15" r="2" fill="currentColor" opacity="0.6" />
            </svg>
            <span>Code Monet</span>
          </div>
          <p className="footer-credits">
            Built with Claude by{' '}
            <a href="https://anthropic.com" target="_blank" rel="noopener noreferrer">
              Anthropic
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
