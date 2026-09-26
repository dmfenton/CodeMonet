/**
 * New piece: optional direction, style (Paint / Plotter) and canvas shape.
 */

import React, { useEffect, useRef, useState } from 'react';
import type { DrawingStyleType } from '@code-monet/shared';

export interface CanvasDimensions {
  canvas_width: number;
  canvas_height: number;
}

interface CanvasProfile {
  id: string;
  label: string;
  width: number;
  height: number;
}

export const CANVAS_PROFILES: CanvasProfile[] = [
  { id: 'standard', label: '4:3', width: 800, height: 600 },
  { id: 'wide', label: 'Wide', width: 1200, height: 600 },
  { id: 'masthead', label: 'Masthead', width: 1200, height: 420 },
  { id: 'square', label: 'Square', width: 800, height: 800 },
  { id: 'portrait', label: 'Portrait', width: 600, height: 900 },
];

const STYLES: { id: DrawingStyleType; label: string; hint: string }[] = [
  { id: 'paint', label: 'Paint', hint: 'Full-color painting program' },
  { id: 'plotter', label: 'Plotter', hint: 'Monochrome pen lines' },
];

interface NewPieceDialogProps {
  initialStyle: DrawingStyleType;
  onCancel: () => void;
  onStart: (
    direction: string | undefined,
    style: DrawingStyleType,
    canvas: CanvasDimensions
  ) => void;
}

export function NewPieceDialog({
  initialStyle,
  onCancel,
  onStart,
}: NewPieceDialogProps): React.ReactElement {
  const [direction, setDirection] = useState('');
  const [style, setStyle] = useState<DrawingStyleType>(initialStyle);
  const [profileId, setProfileId] = useState(CANVAS_PROFILES[0]!.id);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return (): void => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  const submit = (): void => {
    const profile = CANVAS_PROFILES.find((p) => p.id === profileId) ?? CANVAS_PROFILES[0]!;
    onStart(direction.trim() || undefined, style, {
      canvas_width: profile.width,
      canvas_height: profile.height,
    });
  };

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div
        className="dialog new-piece"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-piece-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="new-piece-title">What should we paint?</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <label htmlFor="new-piece-direction" className="visually-hidden">
            Direction (optional)
          </label>
          <textarea
            id="new-piece-direction"
            ref={inputRef}
            rows={3}
            data-testid="start-modal-input"
            placeholder="A foggy harbor at first light, boats barely there…"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <p className="dialog-hint">Optional. Leave it empty and the painter chooses.</p>

          <fieldset className="chip-group">
            <legend className="mono-label">style</legend>
            {STYLES.map((s) => (
              <button
                key={s.id}
                type="button"
                className="chip"
                aria-pressed={style === s.id}
                title={s.hint}
                onClick={() => setStyle(s.id)}
              >
                {s.label}
              </button>
            ))}
          </fieldset>

          <fieldset className="chip-group">
            <legend className="mono-label">canvas</legend>
            {CANVAS_PROFILES.map((p) => (
              <button
                key={p.id}
                type="button"
                className="chip"
                aria-pressed={profileId === p.id}
                title={`${p.width} × ${p.height}`}
                onClick={() => setProfileId(p.id)}
              >
                {p.label}
              </button>
            ))}
          </fieldset>

          <div className="dialog-actions">
            <button type="button" className="btn btn-ghost" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" data-testid="start-modal-submit">
              Begin
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
