/**
 * Overflow menu for the studio top bar: gallery, drawing, clear, debug, sign out.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { Icon } from '../brand/Icon';

interface StudioMenuProps {
  drawingEnabled: boolean;
  onToggleDrawing: () => void;
  onClear: () => void;
  /** Dev builds only. */
  debugVisible?: boolean;
  onToggleDebug?: () => void;
  onSignOut: () => void;
}

export function StudioMenu({
  drawingEnabled,
  onToggleDrawing,
  onClear,
  debugVisible,
  onToggleDebug,
  onSignOut,
}: StudioMenuProps): React.ReactElement {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent): void => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return (): void => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const run = (action: () => void) => (): void => {
    action();
    setOpen(false);
  };

  return (
    <div className="studio-menu" ref={rootRef}>
      <button
        type="button"
        className="btn btn-ghost btn-icon"
        aria-label="More"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="more" />
      </button>
      {open && (
        <div className="studio-menu-list" role="menu">
          <Link to="/gallery" role="menuitem" className="studio-menu-item">
            Gallery
          </Link>
          <button
            type="button"
            role="menuitemcheckbox"
            aria-checked={drawingEnabled}
            className="studio-menu-item"
            onClick={run(onToggleDrawing)}
          >
            Draw on canvas
            <span className="studio-menu-check">{drawingEnabled ? 'on' : 'off'}</span>
          </button>
          <button type="button" role="menuitem" className="studio-menu-item" onClick={run(onClear)}>
            Clear canvas
          </button>
          {onToggleDebug && (
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={Boolean(debugVisible)}
              className="studio-menu-item"
              onClick={run(onToggleDebug)}
            >
              Debug panel
              <span className="studio-menu-check">{debugVisible ? 'on' : 'off'}</span>
            </button>
          )}
          <div className="studio-menu-sep" role="separator" />
          <button
            type="button"
            role="menuitem"
            className="studio-menu-item"
            onClick={run(onSignOut)}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
