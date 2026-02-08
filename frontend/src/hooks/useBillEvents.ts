import { useEffect } from 'react';

export function useBillEvents(
  billId: number | undefined, 
  onRefresh: () => void,
  onReaction?: (userId: number, emoji: string) => void
) {
  useEffect(() => {
    if (!billId) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
    const sseUrl = `${apiUrl}/bills/${billId}/events`;
    
    console.log(`Subscribing to SSE: ${sseUrl}`);
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      console.log('SSE message received:', event.data);
      const data = event.data as string;
      
      if (data === 'REFRESH') {
        onRefresh();
      } else if (data.startsWith('REACTION:')) {
        const parts = data.split(':');
        if (parts.length === 3 && onReaction) {
          const userId = parseInt(parts[1]);
          const emoji = parts[2];
          onReaction(userId, emoji);
        }
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
  }, [billId, onRefresh, onReaction]);
}
