/**
 * LiveCanvas - Real-time drawing preview with WebSocket or simulation fallback
 * Uses Monet-inspired color palette for a warm, artistic aesthetic
 */

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { pathToSvgDScaled, type Path } from '@code-monet/shared';
import { getWebSocketUrl } from '../../config';
import { SimulatedStroke, STROKE_COLORS } from './types';
import { generateArtisticPath, pointsToPath } from './utils';

export function LiveCanvas(): React.ReactElement {
  const [realStrokes, setRealStrokes] = useState<Path[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [simStrokes, setSimStrokes] = useState<SimulatedStroke[]>([]);
  const [currentStroke, setCurrentStroke] = useState<SimulatedStroke | null>(null);
  const strokeIdRef = useRef(0);
  const animationRef = useRef<number>();
  const wsRef = useRef<WebSocket | null>(null);

  // Try to connect to WebSocket for live strokes
  useEffect(() => {
    const connectWs = (): void => {
      try {
        const ws = new WebSocket(getWebSocketUrl());

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

  // Fallback simulation when no WebSocket
  const createNewStroke = useCallback((): void => {
    const newStroke: SimulatedStroke = {
      id: strokeIdRef.current++,
      points: generateArtisticPath(),
      color: STROKE_COLORS[Math.floor(Math.random() * STROKE_COLORS.length)],
      width: Math.random() * 4 + 2,
      progress: 0,
    };
    setCurrentStroke(newStroke);
  }, []);

  useEffect(() => {
    if (wsConnected && realStrokes.length > 0) {
      return;
    }

    createNewStroke();

    const animate = (): void => {
      setCurrentStroke((prev) => {
        if (!prev) return prev;

        const newProgress = prev.progress + 0.015; // Slightly slower for elegance

        if (newProgress >= 1) {
          setSimStrokes((s) => [...s.slice(-12), { ...prev, progress: 1 }]);
          setTimeout(createNewStroke, 800 + Math.random() * 1200);
          return null;
        }

        return { ...prev, progress: newProgress };
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);

    return (): void => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [createNewStroke, wsConnected, realStrokes.length]);

  const showReal = wsConnected && realStrokes.length > 0;

  return (
    <svg viewBox="0 0 400 300" className="live-canvas-svg">
      <defs>
        {/* Subtle paper texture filter */}
        <filter id="paperTexture">
          <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="3" result="noise" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="0.8" />
        </filter>
      </defs>

      {/* Warm off-white canvas background */}
      <rect width="400" height="300" fill="#fdfcf8" />

      {showReal ? (
        realStrokes
          .slice(-30)
          .map((stroke, i) => (
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
          ))
      ) : (
        <>
          {simStrokes.map((stroke) => (
            <path
              key={stroke.id}
              d={pointsToPath(stroke.points, stroke.progress)}
              fill="none"
              stroke={stroke.color}
              strokeWidth={stroke.width}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.8}
              filter="url(#paperTexture)"
            />
          ))}

          {currentStroke && (
            <path
              d={pointsToPath(currentStroke.points, currentStroke.progress)}
              fill="none"
              stroke={currentStroke.color}
              strokeWidth={currentStroke.width}
              strokeLinecap="round"
              strokeLinejoin="round"
              filter="url(#paperTexture)"
            />
          )}

          {/* Brush tip indicator */}
          {currentStroke && currentStroke.progress > 0 && (
            <g
              transform={`translate(${currentStroke.points[Math.floor(currentStroke.points.length * currentStroke.progress)]?.x || 0}, ${currentStroke.points[Math.floor(currentStroke.points.length * currentStroke.progress)]?.y || 0})`}
            >
              <circle r="3" fill={currentStroke.color} opacity="0.6">
                <animate attributeName="r" values="3;4;3" dur="0.8s" repeatCount="indefinite" />
              </circle>
            </g>
          )}
        </>
      )}

      {/* Live indicator - subtle sage green */}
      {showReal && (
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
      )}
    </svg>
  );
}
