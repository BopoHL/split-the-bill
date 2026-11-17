import { useEffect, useState } from 'react';
import apiClient from '@/lib/api/client';

/**
 * An image the API serves only to an authenticated caller.
 *
 * <img src> cannot carry the Telegram identity header, so the bytes come
 * through the API client and are handed to the browser as a blob URL. The
 * loaded path is kept alongside the URL so a result that arrives after the
 * caller moved on is never shown.
 */
export function useAuthenticatedImage(path: string | null | undefined): string | null {
  const [loaded, setLoaded] = useState<{ path: string; url: string } | null>(null);

  useEffect(() => {
    if (!path) return;

    let cancelled = false;
    let created: string | null = null;

    apiClient
      .get(path, { responseType: 'blob' })
      .then((response) => {
        if (cancelled) return;
        created = URL.createObjectURL(response.data as Blob);
        setLoaded({ path, url: created });
      })
      .catch(() => {
        /* a missing or forbidden photo just renders the drawn slip */
      });

    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [path]);

  return loaded && loaded.path === path ? loaded.url : null;
}
