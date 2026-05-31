/**
 * GalleryItem - Individual gallery piece with server-rendered thumbnail
 * Uses PNG thumbnails from server for consistent rendering with mobile
 */

import React, { useState, useRef } from 'react';
import { getApiUrl } from '../../config';
import { GalleryPiece, STROKE_COLORS } from './types';

export interface GalleryItemProps {
  piece?: GalleryPiece;
  index: number;
  delay: number;
}

interface FallbackStroke {
  d: string;
  color: string;
  width: number;
}

export function GalleryItem({ piece, index, delay }: GalleryItemProps): React.ReactElement {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  // Fallback generated strokes with Monet palette (shown while loading or on error)
  const fallbackStrokes = useRef<FallbackStroke[]>(
    Array.from({ length: 8 }, () => ({
      d: `M ${20 + Math.random() * 60} ${20 + Math.random() * 60} Q ${Math.random() * 100} ${Math.random() * 100}, ${40 + Math.random() * 60} ${40 + Math.random() * 60}`,
      color: STROKE_COLORS[Math.floor(Math.random() * STROKE_COLORS.length)],
      width: Math.random() * 3 + 1.5,
    }))
  ).current;

  const displayNumber = piece?.piece_number ?? index + 1;
  const thumbnailUrl = piece
    ? `${getApiUrl()}/public/gallery/${piece.user_id}/${piece.id}/thumbnail.png`
    : null;

  return (
    <div className="gallery-item" style={{ animationDelay: `${delay}s` }}>
      <div className="gallery-frame">
        {thumbnailUrl && !imageError ? (
          <>
            {/* Show fallback while loading */}
            {!imageLoaded && (
              <svg viewBox="0 0 100 100" className="gallery-artwork gallery-loading">
                <rect width="100" height="100" fill="#fffdf8" />
                {fallbackStrokes.map((stroke, i) => (
                  <path
                    key={i}
                    d={stroke.d}
                    fill="none"
                    stroke={stroke.color}
                    strokeWidth={stroke.width}
                    strokeLinecap="round"
                    opacity={0.3}
                  />
                ))}
              </svg>
            )}
            <img
              src={thumbnailUrl}
              alt={piece?.title || `Piece #${displayNumber}`}
              className={`gallery-artwork gallery-thumbnail ${imageLoaded ? 'loaded' : ''}`}
              onLoad={() => setImageLoaded(true)}
              onError={() => setImageError(true)}
            />
          </>
        ) : (
          <svg viewBox="0 0 100 100" className="gallery-artwork">
            {/* Warm canvas background */}
            <rect width="100" height="100" fill="#fffdf8" />
            {fallbackStrokes.map((stroke, i) => (
              <path
                key={i}
                d={stroke.d}
                fill="none"
                stroke={stroke.color}
                strokeWidth={stroke.width}
                strokeLinecap="round"
                opacity={0.75}
              />
            ))}
          </svg>
        )}
      </div>
      <span className="gallery-label" title={piece?.title || `No. ${String(displayNumber).padStart(3, '0')}`}>
        {piece?.title || `No. ${String(displayNumber).padStart(3, '0')}`}
      </span>
    </div>
  );
}
