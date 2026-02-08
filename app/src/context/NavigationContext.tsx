/**
 * Navigation context - manages app screen state and transitions.
 *
 * ## Design Decision: Explicit State Machine
 *
 * This app uses a simple state machine for navigation instead of a library
 * like react-navigation because:
 *
 * 1. Three-screen model - Home, Studio, and Gallery screens
 * 2. Controlled transitions - Navigation triggers side effects (pause/resume agent)
 * 3. Backgrounding behavior - Custom logic for app suspend/resume
 * 4. No deep linking needs - App always starts at Home
 *
 * ## Limitations (Accepted Trade-offs)
 *
 * - No swipe back gesture (intentional - prevents accidental exits during drawing)
 * - Minimal navigation history (gallery tracks its previous screen)
 * - No URL-based routing (not a web app)
 *
 * ## Future Considerations
 *
 * If the app grows to need more than 3 screens, deep linking, or nested
 * navigation, consider migrating to react-navigation with custom state
 * persistence to maintain the pause-on-exit behavior.
 */

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

/** Navigation screen type */
export type Screen = 'home' | 'studio' | 'gallery' | 'imageView';

export interface NavigationContextValue {
  /** Current screen */
  screen: Screen;
  /** Whether user is in the studio (convenience accessor) */
  inStudio: boolean;
  /** Navigate to studio screen */
  enterStudio: () => void;
  /** Navigate to home screen */
  exitStudio: () => void;
  /** Set screen directly (for gallery selection, etc.) */
  setInStudio: (inStudio: boolean) => void;
  /** Navigate to gallery screen */
  openGallery: () => void;
  /** Navigate back from gallery to the previous screen */
  closeGallery: () => void;
  /** Navigate from gallery directly to home */
  galleryToHome: () => void;
  /** Whether gallery was opened from the studio screen */
  galleryFromStudio: boolean;
  /** Navigate to image view for a gallery piece */
  openImageView: (pieceNumber: number) => void;
  /** Navigate back from image view to gallery */
  closeImageView: () => void;
  /** Piece number being viewed in image view */
  viewingPieceNumber: number | null;
}

const NavigationContext = createContext<NavigationContextValue | null>(null);

export interface NavigationProviderProps {
  children: React.ReactNode;
}

/**
 * Provider that manages navigation state and screen transitions.
 *
 * Handles:
 * - Screen transitions (home <-> studio <-> gallery)
 * - Android back button (exits studio -> home, then exits app)
 *
 * Note: App backgrounding (pause/resume) is handled by StudioProvider,
 * which has access to the WebSocket connection.
 */
export function NavigationProvider({
  children,
}: NavigationProviderProps): React.JSX.Element {
  const [screen, setScreen] = useState<Screen>('home');
  // Track which screen the gallery was opened from
  const [previousScreen, setPreviousScreen] = useState<Screen>('home');
  // Track which piece is being viewed in image view
  const [viewingPieceNumber, setViewingPieceNumber] = useState<number | null>(null);

  // Track screen in ref for back button handler (avoids stale closure)
  const screenRef = useRef(screen);
  screenRef.current = screen;

  // Derived state
  const inStudio = screen === 'studio';
  const galleryFromStudio = screen === 'gallery' && previousScreen === 'studio';

  // Navigate to studio
  const enterStudio = useCallback(() => {
    setScreen('studio');
  }, []);

  // Navigate to home (caller is responsible for pausing agent if needed)
  const exitStudio = useCallback(() => {
    setScreen('home');
  }, []);

  // Set screen directly (for gallery selection)
  const setInStudio = useCallback((value: boolean) => {
    setScreen(value ? 'studio' : 'home');
  }, []);

  // Navigate to gallery, remembering where we came from
  const openGallery = useCallback(() => {
    if (screenRef.current === 'gallery') return;
    setPreviousScreen(screenRef.current);
    setScreen('gallery');
  }, []);

  // Navigate back from gallery to previous screen
  const closeGallery = useCallback(() => {
    setScreen((prev) => prev === 'gallery' ? previousScreen : prev);
  }, [previousScreen]);

  // Navigate from gallery directly to home
  const galleryToHome = useCallback(() => {
    setScreen('home');
  }, []);

  // Navigate to image view for a gallery piece
  const openImageView = useCallback((pieceNumber: number) => {
    setViewingPieceNumber(pieceNumber);
    setScreen('imageView');
  }, []);

  // Navigate back from image view to gallery
  const closeImageView = useCallback(() => {
    setViewingPieceNumber(null);
    setScreen('gallery');
  }, []);

  // Note: Android back button is handled in StudioProvider, which has
  // access to both navigation and the WebSocket (needed to pause agent).

  // Memoize context value
  const value = useMemo<NavigationContextValue>(
    () => ({
      screen,
      inStudio,
      enterStudio,
      exitStudio,
      setInStudio,
      openGallery,
      closeGallery,
      galleryToHome,
      galleryFromStudio,
      openImageView,
      closeImageView,
      viewingPieceNumber,
    }),
    [screen, inStudio, enterStudio, exitStudio, setInStudio, openGallery, closeGallery, galleryToHome, galleryFromStudio, openImageView, closeImageView, viewingPieceNumber]
  );

  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

/**
 * Hook to access navigation context.
 * Must be used within a NavigationProvider.
 */
export function useNavigation(): NavigationContextValue {
  const context = useContext(NavigationContext);
  if (!context) {
    throw new Error('useNavigation must be used within a NavigationProvider');
  }
  return context;
}
