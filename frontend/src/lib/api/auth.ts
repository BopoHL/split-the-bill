import apiClient from './client';

export type SseResource = 'bill' | 'receipt_task';

/**
 * Trade the Telegram identity header for a URL-safe ticket.
 *
 * EventSource cannot send headers, so streams authenticate with a one-shot
 * ticket that is bound to a single resource and expires within a minute.
 */
export async function requestSseTicket(
  resourceType: SseResource,
  resourceId: number,
): Promise<string> {
  const response = await apiClient.post<{ ticket: string; expires_in: number }>(
    '/auth/sse-ticket',
    { resource_type: resourceType, resource_id: resourceId },
  );
  return response.data.ticket;
}
