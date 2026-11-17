import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const requestSseTicket = vi.fn();
vi.mock('./auth', () => ({ requestSseTicket: (...args: unknown[]) => requestSseTicket(...args) }));

import { openAuthenticatedStream } from './sseStream';

describe('openAuthenticatedStream', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    requestSseTicket.mockReset();
  });

  it('stops asking for a ticket the server refuses', async () => {
    requestSseTicket.mockRejectedValue({ response: { status: 401 } });
    const close = openAuthenticatedStream('bill', 1, '/bills/1/events', () => {});

    await vi.advanceTimersByTimeAsync(30_000);

    expect(requestSseTicket).toHaveBeenCalledOnce();
    close();
  });

  it('keeps trying while the server is merely out of reach', async () => {
    requestSseTicket.mockRejectedValue(new Error('Network Error'));
    const close = openAuthenticatedStream('bill', 1, '/bills/1/events', () => {});

    await vi.advanceTimersByTimeAsync(10_000);

    expect(requestSseTicket.mock.calls.length).toBeGreaterThan(1);
    close();
  });
});
