import { useEffect } from 'react';
import { openAuthenticatedStream } from '@/lib/api/sseStream';

export function useBillEvents(
  billId: number | undefined,
  onRefresh: () => void,
  /** The owner deleted the bill while this screen was open. */
  onDeleted?: () => void,
) {
  useEffect(() => {
    if (!billId) return;

    return openAuthenticatedStream('bill', billId, `/bills/${billId}/events`, (data) => {
      if (data === 'REFRESH') {
        onRefresh();
      } else if (data === 'DELETED') {
        onDeleted?.();
      }
    });
  }, [billId, onRefresh, onDeleted]);
}
