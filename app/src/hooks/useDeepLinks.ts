/**
 * Deep link handling for magic link authentication.
 * Handles Universal Links and custom scheme callbacks.
 */

import * as Linking from 'expo-linking';
import { useCallback, useEffect, useState } from 'react';

export interface UseDeepLinksOptions {
  /** Exchange a Fenton Identity authorization code using the pending PKCE verifier. */
  exchangeAuthorizationCode: (
    code: string
  ) => Promise<{ success: boolean; error?: string }>;
}

export interface UseDeepLinksReturn {
  /** Whether we're currently verifying a magic link */
  verifyingMagicLink: boolean;
  /** Error message from magic link verification */
  magicLinkError: string | null;
  /** Clear the magic link error */
  clearError: () => void;
}

/**
 * Hook to handle deep links for magic link authentication.
 *
 * Handles several URL patterns:
 * - `https://monet.dmfenton.net/auth/callback?code=...` - OAuth authorization callback
 */
export function useDeepLinks({
  exchangeAuthorizationCode,
}: UseDeepLinksOptions): UseDeepLinksReturn {
  const [verifyingMagicLink, setVerifyingMagicLink] = useState(false);
  const [magicLinkError, setMagicLinkError] = useState<string | null>(null);

  const clearError = useCallback(() => {
    setMagicLinkError(null);
  }, []);

  // Handle incoming deep link URL
  const handleDeepLink = useCallback(
    async (url: string | null) => {
      if (!url) return;

      try {
        const parsed = Linking.parse(url);

        if (parsed.path === 'auth/callback' && parsed.queryParams?.code) {
          const code = parsed.queryParams.code as string;
          setVerifyingMagicLink(true);
          setMagicLinkError(null);
          const result = await exchangeAuthorizationCode(code);
          if (!result.success) {
            setMagicLinkError(result.error ?? 'Failed to authenticate');
          }
          setVerifyingMagicLink(false);
        }
      } catch (error) {
        console.error('[useDeepLinks] Error handling deep link:', error);
        setVerifyingMagicLink(false);
      }
    },
    [exchangeAuthorizationCode]
  );

  // Listen for deep links when app is already running
  useEffect(() => {
    const subscription = Linking.addEventListener('url', (event) => {
      void handleDeepLink(event.url);
    });

    // Check for initial URL (app opened via deep link)
    void Linking.getInitialURL().then(handleDeepLink);

    return () => subscription.remove();
  }, [handleDeepLink]);

  return {
    verifyingMagicLink,
    magicLinkError,
    clearError,
  };
}
