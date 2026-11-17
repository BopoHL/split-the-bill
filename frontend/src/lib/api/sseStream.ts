import { requestSseTicket, type SseResource } from './auth';

const RECONNECT_DELAY_MS = 3000;

/**
 * An EventSource that re-authenticates itself.
 *
 * Each connection spends a one-shot ticket, so the browser's own retry (which
 * would replay the spent one) is replaced by reconnecting with a fresh ticket.
 */
export function openAuthenticatedStream(
  resourceType: SseResource,
  resourceId: number,
  path: string,
  onMessage: (data: string) => void,
): () => void {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
  let source: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const connect = async () => {
    if (closed) return;
    let ticket: string;
    try {
      ticket = await requestSseTicket(resourceType, resourceId);
    } catch (error) {
      // Refused rather than unreachable: asking again every few seconds changes nothing.
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status !== undefined && status >= 400 && status < 500) return;
      scheduleRetry();
      return;
    }
    if (closed) return;

    source = new EventSource(`${baseUrl}${path}?ticket=${encodeURIComponent(ticket)}`);
    source.onmessage = (event) => onMessage(event.data as string);
    source.onerror = () => {
      source?.close();
      source = null;
      scheduleRetry();
    };
  };

  const scheduleRetry = () => {
    if (closed || retryTimer) return;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      void connect();
    }, RECONNECT_DELAY_MS);
  };

  void connect();

  return () => {
    closed = true;
    if (retryTimer) clearTimeout(retryTimer);
    source?.close();
  };
}
