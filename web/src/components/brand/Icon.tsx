/**
 * Small stroke icons (24px grid, currentColor), sized by font-size.
 */

import React from 'react';

const PATHS = {
  arrow: 'M5 12h14M13 6l6 6-6 6',
  up: 'M12 19V5M6 11l6-6 6 6',
  left: 'M15 6l-6 6 6 6',
  right: 'M9 6l6 6-6 6',
  pause: 'M8 5v14M16 5v14',
  play: 'M7 4v16l13-8z',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  more: '',
  code: 'M7 8l-4 4 4 4M17 8l4 4-4 4M14 4l-4 16',
  share: 'M8.7 10.7l6.6-3.4M8.7 13.3l6.6 3.4',
  copy: 'M9 9h10v10H9zM5 15V5h10',
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  className?: string;
}

export function Icon({ name, className }: IconProps): React.ReactElement {
  return (
    <svg
      className={`icon${className ? ` ${className}` : ''}`}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name] && <path d={PATHS[name]} />}
      {name === 'more' &&
        [5, 12, 19].map((cx) => (
          <circle key={cx} cx={cx} cy="12" r="1.6" fill="currentColor" stroke="none" />
        ))}
      {name === 'share' && (
        <>
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="6" r="3" />
          <circle cx="18" cy="18" r="3" />
        </>
      )}
    </svg>
  );
}
