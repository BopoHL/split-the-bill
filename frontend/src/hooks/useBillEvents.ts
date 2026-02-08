import { useEffect } from 'react';

export function useBillEvents(billId: number | undefined, onRefresh: () => void) {
  useEffect(() => {
    if (!billId) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
    const sseUrl = `${apiUrl}/bills/${billId}/events`;
    
    console.log(`Subscribing to SSE: ${sseUrl}`);
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      console.log('SSE message received:', event.data);
      if (event.data === 'REFRESH') {
        onRefresh();
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      // EventSource automatically retries by default
    };

    return () => {
      console.log(`Closing SSE: ${sseUrl}`);
      eventSource.close();
    };
  }, [billId, onRefresh]);
}
