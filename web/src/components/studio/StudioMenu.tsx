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
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const items = (): HTMLElement[] =>
    Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? []);

  const close = (refocus: boolean): void => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    items()[0]?.focus();
    const onPointer = (e: PointerEvent): void => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    return (): void => document.removeEventListener('pointerdown', onPointer);
  }, [open]);

  // WAI-ARIA menu keys: arrows/Home/End move, Escape closes, Tab leaves.
  const onMenuKey = (e: React.KeyboardEvent): void => {
    const list = items();
    const index = list.indexOf(document.activeElement as HTMLElement);
    const move = (to: number): void => {
      e.preventDefault();
      list[(to + list.length) % list.length]?.focus();
    };
    switch (e.key) {
      case 'ArrowDown':
        return move(index + 1);
      case 'ArrowUp':
        return move(index - 1);
      case 'Home':
        return move(0);
      case 'End':
        return move(list.length - 1);
      case 'Escape':
        e.preventDefault();
        return close(true);
      case 'Tab':
        return close(false);
    }
  };

  const run = (action: () => void) => (): void => {
    action();
    close(true);
  };

  return (
    <div className="studio-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn-ghost btn-icon"
        aria-label="More"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        <Icon name="more" />
      </button>
      {open && (
        <div
          className="studio-menu-list"
          role="menu"
          aria-label="Studio"
          ref={listRef}
          onKeyDown={onMenuKey}
        >
          <Link to="/gallery" role="menuitem" tabIndex={-1} className="studio-menu-item">
            Gallery
          </Link>
          <button
            type="button"
            role="menuitemcheckbox"
            tabIndex={-1}
            aria-checked={drawingEnabled}
            className="studio-menu-item"
            onClick={run(onToggleDrawing)}
          >
            Draw on canvas
            <span className="studio-menu-check">{drawingEnabled ? 'on' : 'off'}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            className="studio-menu-item"
            onClick={run(onClear)}
          >
            Clear canvas
          </button>
          {onToggleDebug && (
            <button
              type="button"
              role="menuitemcheckbox"
              tabIndex={-1}
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
            tabIndex={-1}
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
