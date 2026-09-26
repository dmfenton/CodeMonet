/**
 * Code Monet brand: the lily-pad mark (same geometry as brand/mark.svg) and
 * the wordmark lockup — "code" in Plex Mono (accent), "Monet" in Fraunces italic.
 */

import React from 'react';

const VEIN_ENDS: ReadonlyArray<readonly [number, number]> = [
  [73.4, 36.5],
  [76.6, 54.7],
  [67.4, 70.7],
  [50, 77],
  [32.6, 70.7],
  [23.4, 54.7],
  [26.6, 36.5],
];

interface BrandMarkProps {
  size?: number;
  className?: string;
  /** Accessible name; omit when the mark sits next to visible text. */
  title?: string;
}

export function BrandMark({ size = 28, className, title }: BrandMarkProps): React.ReactElement {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      <path d="M50 50 L54.7 16.3 A34 34 0 1 1 45.3 16.3 Z" fill="#2a6243" />
      <g stroke="#94b89e" strokeWidth="1.8" strokeLinecap="round">
        {VEIN_ENDS.map(([x, y]) => (
          <line key={`${x}-${y}`} x1="50" y1="50" x2={x} y2={y} />
        ))}
      </g>
      <circle cx="50" cy="50" r="5.8" fill="#b85a2e" />
    </svg>
  );
}

interface WordmarkProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/** Mark + stacked wordmark. */
export function Wordmark({ size = 'md', className }: WordmarkProps): React.ReactElement {
  const markSize = size === 'lg' ? 40 : size === 'sm' ? 22 : 28;
  return (
    <span className={`wordmark wordmark-${size}${className ? ` ${className}` : ''}`}>
      <BrandMark size={markSize} />
      <span className="wordmark-text">
        <span className="wordmark-code">code</span>
        <span className="wordmark-monet">Monet</span>
      </span>
    </span>
  );
}
