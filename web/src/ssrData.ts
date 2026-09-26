/**
 * SSR initial data is rendered for one URL. After client-side navigation the
 * same object is still around, so it may only be used on the path it was
 * rendered for.
 */

import type { SSRData } from './entry-server';

export function ssrDataFor(initialData: unknown, pathname: string): SSRData | undefined {
  if (typeof initialData !== 'object' || initialData === null) return undefined;
  const data = initialData as SSRData;
  const normalize = (p: string): string => (p.length > 1 ? p.replace(/\/+$/, '') : p);
  return data.path !== undefined && normalize(data.path) === normalize(pathname) ? data : undefined;
}
