/**
 * Full gallery page showing all artwork.
 */

import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getApiUrl } from '../config';
import type { GalleryPiece } from '../components/homepage/types';
import { GalleryItem } from '../components/homepage/GalleryItem';

interface GalleryPageProps {
  initialGalleryPieces?: GalleryPiece[];
}

export function GalleryPage({ initialGalleryPieces }: GalleryPageProps): React.ReactElement {
  const [pieces, setPieces] = useState<GalleryPiece[]>(initialGalleryPieces ?? []);
  const [loading, setLoading] = useState(!initialGalleryPieces);
  const navigate = useNavigate();

  useEffect(() => {
    if (initialGalleryPieces) return;

    const fetchGallery = async (): Promise<void> => {
      try {
        const response = await fetch(`${getApiUrl()}/public/gallery?limit=50`);
        if (response.ok) {
          const data: GalleryPiece[] = await response.json();
          setPieces(data);
        }
      } catch {
        // Silently fail
      } finally {
        setLoading(false);
      }
    };

    fetchGallery();
  }, [initialGalleryPieces]);

  const handleEnterStudio = (): void => {
    navigate('/studio');
  };

  return (
    <div className="gallery-page">
      <header className="gallery-header">
        <Link to="/" className="gallery-back">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Home
        </Link>
        <h1>The Gallery</h1>
        <p className="gallery-intro">
          Every piece in this collection was conceived and executed autonomously by Code Monet. No
          human prompts, no guidance — just artificial creativity at work.
        </p>
      </header>

      <main className="gallery-main">
        {loading ? (
          <div className="gallery-loading">
            <div className="auth-spinner" />
          </div>
        ) : pieces.length === 0 ? (
          <div className="gallery-empty">
            <p>The gallery is empty. Watch the artist create the first piece.</p>
            <button className="cta-primary" onClick={handleEnterStudio}>
              Enter the Studio
            </button>
          </div>
        ) : (
          <div className="gallery-grid">
            {pieces.map((piece, index) => (
              <Link
                key={piece.id}
                to={`/gallery/${piece.user_id}/${piece.id}`}
                className="gallery-grid-item"
              >
                <GalleryItem piece={piece} index={index} delay={0} />
              </Link>
            ))}
          </div>
        )}
      </main>

      <footer className="gallery-footer">
        <button className="cta-secondary" onClick={handleEnterStudio}>
          Watch the artist live
        </button>
      </footer>

      <style>{`
        .gallery-page {
          min-height: 100vh;
          background: var(--bg-page);
          color: var(--text-primary);
          padding: 2rem;
        }

        .gallery-header {
          max-width: 1200px;
          margin: 0 auto 3rem;
          text-align: center;
        }

        .gallery-back {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          color: var(--text-muted);
          text-decoration: none;
          margin-bottom: 2rem;
          transition: color 0.2s;
        }

        .gallery-back:hover {
          color: var(--atelier-indigo);
        }

        .gallery-back svg {
          width: 20px;
          height: 20px;
        }

        .gallery-header h1 {
          font-size: 3rem;
          font-family: var(--font-display);
          font-weight: 500;
          letter-spacing: 0;
          margin-bottom: 1rem;
          color: var(--atelier-indigo);
          font-variation-settings: 'opsz' 72, 'SOFT' 50;
        }

        .gallery-intro {
          max-width: 600px;
          margin: 0 auto;
          color: var(--text-muted);
          line-height: 1.6;
        }

        .gallery-main {
          max-width: 1200px;
          margin: 0 auto;
        }

        .gallery-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 2rem;
        }

        .gallery-grid-item {
          text-decoration: none;
          transition: transform 0.3s ease;
        }

        .gallery-grid-item:hover {
          transform: translateY(-4px);
        }

        .gallery-loading,
        .gallery-empty {
          text-align: center;
          padding: 4rem;
        }

        .gallery-empty p {
          color: var(--text-muted);
          margin-bottom: 1.5rem;
        }

        .gallery-footer {
          max-width: 1200px;
          margin: 4rem auto 0;
          text-align: center;
        }

        @media (max-width: 768px) {
          .gallery-page {
            padding: 1rem;
          }

          .gallery-header h1 {
            font-size: 2rem;
          }

          .gallery-grid {
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 1rem;
          }
        }
      `}</style>
    </div>
  );
}
