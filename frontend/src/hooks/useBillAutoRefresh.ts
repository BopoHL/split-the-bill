import { useEffect, useRef } from 'react';

export const BILL_AUTO_REFRESH_INTERVAL_MS = 10_000;
const AUTO_REFRESH_DEDUPE_MS = 1_000;

type RefreshHandler = () => void | Promise<void>;

/**
 * SSE is the live path, but mobile webviews can freeze or drop the connection
 * while the phone is locked. This catches the page up after resume and keeps a
 * visible bill fresh even if an SSE event was missed.
 */
export function useBillAutoRefresh(
  billId: number | undefined,
  onRefresh: RefreshHandler,
) {
  const lastRefreshAtRef = useRef(Number.NEGATIVE_INFINITY);

  useEffect(() => {
    if (!billId) return;

    const refreshIfVisible = () => {
      if (document.visibilityState !== 'visible') return;

      const now = Date.now();
      if (now - lastRefreshAtRef.current < AUTO_REFRESH_DEDUPE_MS) return;

      lastRefreshAtRef.current = now;
      void onRefresh();
    };

    const intervalId = window.setInterval(
      refreshIfVisible,
      BILL_AUTO_REFRESH_INTERVAL_MS,
    );

    document.addEventListener('visibilitychange', refreshIfVisible);
    window.addEventListener('focus', refreshIfVisible);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', refreshIfVisible);
      window.removeEventListener('focus', refreshIfVisible);
    };
  }, [billId, onRefresh]);
}
