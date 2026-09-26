/**
 * reveal.json loading, shared by the reveal renderer and the stage bar.
 * Versions are immutable per asset_base, so parsed manifests are cached.
 */

import { useEffect, useState } from 'react';
import type { RevealManifest } from '@code-monet/shared';
import { PAINTING_MANIFEST_FILE, paintingAssetUrl, parseRevealManifest } from '@code-monet/shared';

const MAX_CACHED = 24;
const cache = new Map<string, Promise<RevealManifest>>();

export function loadRevealManifest(url: string): Promise<RevealManifest> {
  const cached = cache.get(url);
  if (cached) return cached;
  const promise = (async (): Promise<RevealManifest> => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    const manifest = parseRevealManifest(await res.json());
    if (!manifest) throw new Error(`Invalid reveal manifest: ${url}`);
    return manifest;
  })();
  // Don't cache failures; a later attempt may succeed.
  promise.catch(() => cache.delete(url));
  cache.set(url, promise);
  if (cache.size > MAX_CACHED) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  return promise;
}

/** The parsed reveal.json of a version (null while loading, on error, or without a version). */
export function useRevealManifest(apiUrl: string, assetBase: string | null): RevealManifest | null {
  const [loaded, setLoaded] = useState<{ key: string; manifest: RevealManifest } | null>(null);

  useEffect(() => {
    if (!assetBase) return;
    let cancelled = false;
    const key = assetBase;
    loadRevealManifest(paintingAssetUrl(apiUrl, { asset_base: assetBase }, PAINTING_MANIFEST_FILE))
      .then((manifest) => {
        if (!cancelled) setLoaded({ key, manifest });
      })
      .catch((error: unknown) => {
        console.warn('[useRevealManifest] failed:', error);
      });
    return (): void => {
      cancelled = true;
    };
  }, [apiUrl, assetBase]);

  return loaded && loaded.key === assetBase ? loaded.manifest : null;
}
