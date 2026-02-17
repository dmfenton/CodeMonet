/**
 * LiveCanvas - Real-time drawing preview with WebSocket or painting slideshow fallback
 * Shows actual user paintings when no WebSocket is connected
 */

import React, { useEffect, useState, useRef } from 'react';
import { pathToSvgDScaled, type Path } from '@code-monet/shared';
import { getApiUrl, getWebSocketUrl } from '../../config';
import type { GalleryPiece } from './types';

interface LiveCanvasProps {
  galleryPieces?: GalleryPiece[];
}

export function LiveCanvas({ galleryPieces }: LiveCanvasProps): React.ReactElement {
  const [realStrokes, setRealStrokes] = useState<Path[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  // Try to connect to WebSocket for live strokes
  useEffect(() => {
    const wsUrl = getWebSocketUrl();
    if (!wsUrl) return;

    const connectWs = (): void => {
      try {
        const ws = new WebSocket(wsUrl);

        ws.onopen = (): void => {
          setWsConnected(true);
        };

        ws.onmessage = (event): void => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'canvas_state' && msg.strokes) {
              setRealStrokes(msg.strokes);
            } else if (msg.type === 'stroke' || msg.type === 'new_stroke') {
              setRealStrokes((prev) => [...prev.slice(-50), msg.path || msg]);
            }
          } catch (e) {
            if (import.meta.env.DEV) {
              console.warn('[LiveCanvas] Failed to parse WebSocket message:', e);
            }
          }
        };

        ws.onclose = (): void => {
          setWsConnected(false);
          wsRef.current = null;
        };

        ws.onerror = (): void => {
          setWsConnected(false);
        };

        wsRef.current = ws;
      } catch {
        setWsConnected(false);
      }
    };

    connectWs();

    return (): void => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Rotate through paintings every 6 seconds
  const pieces = galleryPieces ?? [];
  useEffect(() => {
    if (wsConnected && realStrokes.length > 0) return;
    if (pieces.length <= 1) return;

    const interval = setInterval(() => {
      setTransitioning(true);
      // After fade-out, switch slide
      setTimeout(() => {
        setCurrentSlide((prev) => (prev + 1) % pieces.length);
        setImageLoaded(false);
        setTransitioning(false);
      }, 600);
    }, 6000);

    return (): void => clearInterval(interval);
  }, [wsConnected, realStrokes.length, pieces.length]);

  const showReal = wsConnected && realStrokes.length > 0;
  const currentPiece = pieces[currentSlide];
  const nextPieceIndex = pieces.length > 1 ? (currentSlide + 1) % pieces.length : -1;
  const nextPiece = nextPieceIndex >= 0 ? pieces[nextPieceIndex] : null;

  const getThumbnailUrl = (piece: GalleryPiece): string =>
    `${getApiUrl()}/public/gallery/${piece.user_id}/${piece.id}/thumbnail.png`;

  return (
    <div className="live-canvas-container">
      {showReal ? (
        <svg viewBox="0 0 400 300" className="live-canvas-svg">
          <rect width="400" height="300" fill="#fdfcf8" />
          {realStrokes.slice(-30).map((stroke, i) => (
            <path
              key={i}
              d={pathToSvgDScaled(stroke, 0.5)}
              fill="none"
              stroke={stroke.color ?? (stroke.author === 'human' ? '#6a9fb5' : '#2c3e50')}
              strokeWidth={(stroke.stroke_width ?? 8) * 0.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={stroke.opacity ?? 0.85}
            />
          ))}
          {/* Live indicator */}
          <g transform="translate(380, 16)">
            <circle r="4" fill="#6b9b6b" opacity="0.8">
              <animate
                attributeName="opacity"
                values="0.8;0.4;0.8"
                dur="3s"
                repeatCount="indefinite"
              />
            </circle>
          </g>
        </svg>
      ) : currentPiece ? (
        <div className="painting-slideshow">
          <img
            src={getThumbnailUrl(currentPiece)}
            alt={currentPiece.title || `Painting #${currentPiece.piece_number}`}
            className={`slideshow-image ${imageLoaded ? 'loaded' : ''} ${transitioning ? 'fading' : ''}`}
            onLoad={() => setImageLoaded(true)}
          />
          {/* Preload next image */}
          {nextPiece && (
            <img
              src={getThumbnailUrl(nextPiece)}
              alt=""
              className="slideshow-preload"
            />
          )}
          {currentPiece.title && (
            <div className={`slideshow-caption ${imageLoaded ? 'visible' : ''} ${transitioning ? 'fading' : ''}`}>
              {currentPiece.title}
            </div>
          )}
        </div>
      ) : (
        /* Ultimate fallback: empty canvas */
        <svg viewBox="0 0 400 300" className="live-canvas-svg">
          <rect width="400" height="300" fill="#fdfcf8" />
        </svg>
      )}
    </div>
  );
}
