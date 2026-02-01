/**
 * Action bar with controls for the drawing agent.
 * Redesigned for clarity: unified input field for start prompt or nudge.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import type { ClientMessage, DrawingStyleType } from '@code-monet/shared';

interface ActionBarProps {
  paused: boolean;
  drawingEnabled: boolean;
  drawingStyle: DrawingStyleType;
  onSend: (message: ClientMessage) => void;
  onStyleChange: (style: DrawingStyleType) => void;
  onToggleDrawing: () => void;
  onPause: () => void;
  onResume: (direction?: string) => void;
}

export function ActionBar({
  paused,
  drawingEnabled,
  drawingStyle,
  onSend,
  onStyleChange,
  onToggleDrawing,
  onPause,
  onResume,
}: ActionBarProps): React.ReactElement {
  const [inputText, setInputText] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [modalDirection, setModalDirection] = useState('');
  const modalInputRef = useRef<HTMLInputElement>(null);

  const handleStyleToggle = useCallback(() => {
    const newStyle: DrawingStyleType = drawingStyle === 'plotter' ? 'paint' : 'plotter';
    onStyleChange(newStyle);
  }, [drawingStyle, onStyleChange]);

  // Focus modal input when opened
  useEffect(() => {
    if (showModal && modalInputRef.current) {
      modalInputRef.current.focus();
    }
  }, [showModal]);

  const handleStartClick = useCallback(() => {
    setShowModal(true);
    setModalDirection('');
  }, []);

  const handleModalStart = useCallback(() => {
    const direction = modalDirection.trim();
    onResume(direction || undefined);
    setShowModal(false);
    setModalDirection('');
  }, [modalDirection, onResume]);

  const handleModalCancel = useCallback(() => {
    setShowModal(false);
    setModalDirection('');
  }, []);

  const handleModalKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleModalStart();
      } else if (e.key === 'Escape') {
        handleModalCancel();
      }
    },
    [handleModalStart, handleModalCancel]
  );

  const handlePause = useCallback(() => {
    onPause();
  }, [onPause]);

  const handleClear = useCallback(() => {
    onSend({ type: 'clear' });
  }, [onSend]);

  const handleNewCanvas = useCallback(() => {
    onSend({ type: 'new_canvas' });
  }, [onSend]);

  const handleNudge = useCallback(() => {
    if (inputText.trim()) {
      onSend({ type: 'nudge', text: inputText.trim() });
      setInputText('');
    }
  }, [inputText, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleNudge();
      }
    },
    [handleNudge]
  );

  return (
    <>
      <div className="action-bar">
        <div className="action-bar-left">
          <button
            className={drawingEnabled ? 'icon-btn active' : 'icon-btn'}
            onClick={onToggleDrawing}
            title={drawingEnabled ? 'Drawing mode on' : 'Enable drawing'}
          >
            <span className="icon">✏️</span>
          </button>
          <button
            className="style-toggle"
            onClick={handleStyleToggle}
            title={`Style: ${drawingStyle === 'plotter' ? 'Plotter (monochrome)' : 'Paint (color)'}`}
          >
            <span className="icon">{drawingStyle === 'plotter' ? '🖊️' : '🎨'}</span>
            <span className="style-label">{drawingStyle === 'plotter' ? 'Plotter' : 'Paint'}</span>
          </button>
        </div>

        <div className="action-bar-center">
          {paused ? (
            <button className="primary start-btn" onClick={handleStartClick}>
              ▶ Start
            </button>
          ) : (
            <>
              <input
                type="text"
                placeholder="Nudge the artist..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button className="primary" onClick={handleNudge} disabled={!inputText.trim()}>
                Send
              </button>
              <button className="secondary pause-btn" onClick={handlePause}>
                ⏸
              </button>
            </>
          )}
        </div>

        <div className="action-bar-right">
          <button className="text-btn" onClick={handleClear}>
            Clear
          </button>
          <button className="text-btn" onClick={handleNewCanvas}>
            New Piece
          </button>
        </div>
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={handleModalCancel}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Start Drawing</h3>
            <p>Give the agent a direction (optional):</p>
            <input
              ref={modalInputRef}
              type="text"
              placeholder="e.g., Draw a peaceful landscape..."
              value={modalDirection}
              onChange={(e) => setModalDirection(e.target.value)}
              onKeyDown={handleModalKeyDown}
            />
            <div className="modal-actions">
              <button className="secondary" onClick={handleModalCancel}>
                Cancel
              </button>
              <button className="primary" onClick={handleModalStart}>
                Start
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
