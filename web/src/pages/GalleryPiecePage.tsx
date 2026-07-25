/**
 * Individual gallery piece page with full artwork display.
 */

import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { pathToSvgDScaled, type Path } from '@code-monet/shared';
import { getApiUrl } from '../config';
import type { GalleryPiece, PieceStrokes } from '../components/homepage/types';

interface GalleryPiecePageProps {
  userId: string;
  pieceId: string;
  initialPiece?: GalleryPiece;
  initialStrokes?: PieceStrokes;
}

export function GalleryPiecePage({
  userId,
  pieceId,
  initialPiece,
  initialStrokes,
}: GalleryPiecePageProps): React.ReactElement {
  const [piece, setPiece] = useState<GalleryPiece | undefined>(initialPiece);
  const [strokes, setStrokes] = useState<Path[]>((initialStrokes?.strokes ?? []) as Path[]);
  const [canvasSize, setCanvasSize] = useState({
    width: initialStrokes?.canvas_width ?? initialPiece?.width ?? 800,
    height: initialStrokes?.canvas_height ?? initialPiece?.height ?? 600,
  });
  const [loading, setLoading] = useState(!initialStrokes);
  const navigate = useNavigate();

  useEffect(() => {
    if (initialStrokes) return;

    const fetchStrokes = async (): Promise<void> => {
      try {
        const response = await fetch(`${getApiUrl()}/public/gallery/${userId}/${pieceId}/strokes`);
        if (response.ok) {
          const data: PieceStrokes = await response.json();
          setStrokes((data.strokes ?? []) as Path[]);
          setCanvasSize({
            width: data.canvas_width ?? 800,
            height: data.canvas_height ?? 600,
          });
          // Create a piece object from the response
          setPiece({
            id: data.id,
            user_id: userId,
            piece_number: data.piece_number,
            stroke_count: data.strokes?.length ?? 0,
            width: data.canvas_width,
            height: data.canvas_height,
            created_at: data.created_at,
          });
        }
      } catch {
        // Silently fail
      } finally {
        setLoading(false);
      }
    };

    fetchStrokes();
  }, [userId, pieceId, initialStrokes]);

  const pieceNumber = piece?.piece_number ?? parseInt(pieceId.replace('piece_', ''), 10);
  const title = `Piece No. ${String(pieceNumber).padStart(3, '0')}`;
  const createdDate = piece?.created_at
    ? new Date(piece.created_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : null;

  const handleEnterStudio = (): void => {
    navigate('/studio');
  };

  return (
    <div className="piece-page">
      <header className="piece-header">
        <Link to="/gallery" className="piece-back">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Gallery
        </Link>
      </header>

      <main className="piece-main">
        {loading ? (
          <div className="piece-loading">
            <div className="auth-spinner" />
          </div>
        ) : strokes.length === 0 ? (
          <div className="piece-not-found">
            <h2>Artwork not found</h2>
            <p>This piece may have been removed or doesn&apos;t exist.</p>
            <Link to="/gallery" className="cta-secondary">
              Browse the Gallery
            </Link>
          </div>
        ) : (
          <article className="piece-content">
            <div className="piece-canvas-container">
              <div className="piece-frame">
                <svg
                  viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
                  className="piece-artwork"
                  aria-label={title}
                >
                  <rect width={canvasSize.width} height={canvasSize.height} fill="#fffdf8" />
                  {strokes.map((stroke, i) => {
                    const strokeWidth = stroke.stroke_width ?? (stroke.author === 'human' ? 4 : 3);
                    const strokeColor =
                      strokeWidth > 0
                        ? (stroke.color ?? (stroke.author === 'human' ? '#5a9a70' : '#1f4d34'))
                        : 'none';
                    const fill = stroke.fill ?? 'none';
                    const fillOpacity = stroke.fill
                      ? (stroke.fill_opacity ?? stroke.opacity ?? 0.85)
                      : undefined;
                    return (
                      <path
                        key={i}
                        d={pathToSvgDScaled(stroke, 1)}
                        fill={fill}
                        fillOpacity={fillOpacity}
                        stroke={strokeColor}
                        strokeWidth={strokeWidth}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeOpacity={stroke.opacity ?? 0.85}
                      />
                    );
                  })}
                </svg>
              </div>
            </div>

            <div className="piece-info">
              <h1>{title}</h1>
              <dl className="piece-metadata">
                <div className="meta-item">
                  <dt>Artist</dt>
                  <dd>Code Monet</dd>
                </div>
                <div className="meta-item">
                  <dt>Medium</dt>
                  <dd>Digital / SVG</dd>
                </div>
                <div className="meta-item">
                  <dt>Strokes</dt>
                  <dd>{strokes.length}</dd>
                </div>
                {createdDate && (
                  <div className="meta-item">
                    <dt>Created</dt>
                    <dd>{createdDate}</dd>
                  </div>
                )}
              </dl>

              <p className="piece-description">
                This piece was created autonomously by Code Monet, an AI artist powered by Claude.
                Each brushstroke was deliberately placed through a process of observation,
                contemplation, and execution — no human prompts or guidance involved.
              </p>

              <div className="piece-actions">
                <button className="cta-primary" onClick={handleEnterStudio}>
                  Watch the Artist Live
                </button>
                <Link to="/gallery" className="cta-secondary">
                  View More Art
                </Link>
              </div>
            </div>
          </article>
        )}
      </main>

      <style>{`
        .piece-page {
          min-height: 100vh;
          background: var(--bg-page);
          color: var(--text-primary);
          padding: 2rem;
        }

        .piece-header {
          max-width: 1200px;
          margin: 0 auto 2rem;
        }

        .piece-back {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          color: var(--text-muted);
          text-decoration: none;
          transition: color 0.2s;
        }

        .piece-back:hover {
          color: var(--atelier-indigo);
        }

        .piece-back svg {
          width: 20px;
          height: 20px;
        }

        .piece-main {
          max-width: 1200px;
          margin: 0 auto;
        }

        .piece-content {
          display: grid;
          grid-template-columns: 1fr 400px;
          gap: 4rem;
          align-items: start;
        }

        .piece-canvas-container {
          position: sticky;
          top: 2rem;
        }

        .piece-frame {
          background: var(--atelier-prussian);
          padding: 1.5rem;
          border-radius: 4px;
          box-shadow:
            0 20px 40px rgba(16, 46, 30, 0.18),
            inset 0 1px 0 rgba(253, 251, 245, 0.08);
        }

        .piece-artwork {
          width: 100%;
          height: auto;
          display: block;
          border-radius: 2px;
        }

        .piece-info {
          padding-top: 1rem;
        }

        .piece-info h1 {
          font-size: 2.5rem;
          font-family: var(--font-display);
          font-weight: 500;
          letter-spacing: 0;
          margin-bottom: 2rem;
          color: var(--atelier-indigo);
          font-variation-settings: 'opsz' 72, 'SOFT' 50;
        }

        .piece-metadata {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 1.5rem;
          margin-bottom: 2rem;
          padding-bottom: 2rem;
          border-bottom: 1px solid var(--border-default);
        }

        .meta-item dt {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--text-muted);
          margin-bottom: 0.25rem;
        }

        .meta-item dd {
          font-size: 1rem;
          color: var(--text-primary);
          margin: 0;
        }

        .piece-description {
          color: var(--text-secondary);
          line-height: 1.7;
          margin-bottom: 2rem;
        }

        .piece-actions {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
        }

        .piece-loading,
        .piece-not-found {
          text-align: center;
          padding: 4rem;
        }

        .piece-not-found h2 {
          margin-bottom: 0.5rem;
        }

        .piece-not-found p {
          color: var(--text-muted);
          margin-bottom: 1.5rem;
        }

        @media (max-width: 1024px) {
          .piece-content {
            grid-template-columns: 1fr;
            gap: 2rem;
          }

          .piece-canvas-container {
            position: relative;
            top: 0;
          }
        }

        @media (max-width: 768px) {
          .piece-page {
            padding: 1rem;
          }

          .piece-info h1 {
            font-size: 1.75rem;
          }

          .piece-metadata {
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
          }

          .piece-actions {
            flex-direction: column;
          }

          .piece-actions .cta-primary,
          .piece-actions .cta-secondary {
            width: 100%;
            text-align: center;
          }
        }
      `}</style>
    </div>
  );
}
