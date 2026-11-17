import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const upload = vi.fn();
const cancelTask = vi.fn();
const loadPro = vi.fn();

vi.mock('@/lib/api/receipts', () => ({
  receiptsApi: {
    upload: (...args: unknown[]) => upload(...args),
    uploadQr: vi.fn(),
    getStreamUrl: () => 'http://stream',
    cancelTask: (...args: unknown[]) => cancelTask(...args),
  },
}));

vi.mock('@/lib/api/auth', () => ({
  requestSseTicket: vi.fn().mockResolvedValue('ticket'),
}));

vi.mock('@/lib/utils/image', () => ({
  compressImage: (file: File) => Promise.resolve(file),
}));

vi.mock('@/lib/analytics', () => ({
  track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(),
  AnalyticsEvent: {
    ReceiptScanStarted: 'receipt_scan_started',
    ReceiptScanResult: 'receipt_scan_result',
    BillCreated: 'bill_created',
  },
}));

vi.mock('@/lib/store/usePro', () => ({
  usePro: { getState: () => ({ load: (...args: unknown[]) => loadPro(...args) }) },
}));

import { track } from '@/lib/analytics';
import { useReceiptScan } from './useReceiptScan';

/** Stands in for the browser's EventSource so a test can push worker statuses. */
class FakeEventSource {
  static last: FakeEventSource | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.last = this;
  }

  close() {
    this.closed = true;
  }

  emit(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

/** Let the upload and the ticket request settle without leaving fake timers. */
const settle = async () => {
  for (let i = 0; i < 5; i += 1) await act(async () => {});
};

describe('useReceiptScan', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    upload.mockResolvedValue({ id: 42 });
    cancelTask.mockResolvedValue(undefined);
    FakeEventSource.last = null;
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    upload.mockReset();
    cancelTask.mockReset();
    loadPro.mockReset();
    vi.mocked(track).mockClear();
  });

  const start = async (onScanned = vi.fn()) => {
    const hook = renderHook(() => useReceiptScan({ userId: 1, currency: 'eur', onScanned }));
    act(() => hook.result.current.scanPhoto(new File(['x'], 'receipt.jpg')));
    await settle();
    return { hook, onScanned };
  };

  it('counts a scan that makes a bill as the bill created', async () => {
    await start();
    act(() => FakeEventSource.last!.emit({ status: 'completed', bill_id: 7 }));

    expect(track).toHaveBeenCalledWith('receipt_scan_started', { mode: 'photo', target: 'new_bill' });
    expect(track).toHaveBeenCalledWith('receipt_scan_result', { mode: 'photo', target: 'new_bill', ok: true });
    expect(track).toHaveBeenCalledWith('bill_created', { source: 'photo', bill_id: 7 });
  });

  it('does not count another receipt on a bill as a new bill', async () => {
    const hook = renderHook(() => useReceiptScan({ userId: 1, billId: 7, onScanned: vi.fn() }));
    act(() => hook.result.current.scanPhoto(new File(['x'], 'receipt.jpg')));
    await settle();
    act(() => FakeEventSource.last!.emit({ status: 'completed', bill_id: 7 }));

    expect(track).toHaveBeenCalledWith('receipt_scan_result', { mode: 'photo', target: 'existing_bill', ok: true });
    expect(track).not.toHaveBeenCalledWith('bill_created', expect.anything());
  });

  it('passes the selected creation currency into a photo scan', async () => {
    await start();

    expect(upload).toHaveBeenCalledWith(expect.any(File), 1, undefined, undefined, undefined, 'eur');
  });

  it('lets the model take its time instead of cancelling mid-answer', async () => {
    const { hook, onScanned } = await start();
    const stream = FakeEventSource.last!;

    // The old clock covered OCR and the model together and gave up at 20s, so a
    // model that answers in half a minute — the normal case — was killed and its
    // parse thrown away by the worker.
    act(() => void vi.advanceTimersByTime(25_000));
    act(() => stream.emit({ status: 'structuring', bill_id: null }));
    expect(hook.result.current.phase).toBe('llm');
    expect(cancelTask).not.toHaveBeenCalled();
    expect(hook.result.current.failed).toBe(false);

    // And the model's own phase starts on a full clock, not the leftovers.
    act(() => void vi.advanceTimersByTime(85_000));
    expect(hook.result.current.failed).toBe(false);

    act(() => stream.emit({ status: 'completed', bill_id: 7 }));
    expect(onScanned).toHaveBeenCalledWith(7);
    expect(cancelTask).not.toHaveBeenCalled();
  });

  it('still gives up on a scan that never answers', async () => {
    const { hook } = await start();

    act(() => void vi.advanceTimersByTime(90_000));

    expect(hook.result.current.failed).toBe(true);
    expect(cancelTask).toHaveBeenCalledWith(42);
  });

  it('cancels the scan when its stream breaks, so a retry makes no second bill', async () => {
    const { hook } = await start();

    act(() => FakeEventSource.last!.onerror?.());

    expect(hook.result.current.failed).toBe(true);
    expect(cancelTask).toHaveBeenCalledWith(42);
  });

  it('offers a way out once the scan has dragged on', async () => {
    const { hook } = await start();

    expect(hook.result.current.abortable).toBe(false);
    act(() => void vi.advanceTimersByTime(30_000));
    expect(hook.result.current.abortable).toBe(true);
    // Still running — a slow scan is not a failed one.
    expect(hook.result.current.failed).toBe(false);
    expect(hook.result.current.running).toBe(true);
  });

  it('drops a task whose upload only answered after the scan was abandoned', async () => {
    let resolveUpload: (task: { id: number }) => void = () => {};
    upload.mockImplementation(
      () => new Promise<{ id: number }>((resolve) => { resolveUpload = resolve; }),
    );
    const onScanned = vi.fn();
    const hook = renderHook(() => useReceiptScan({ userId: 1, currency: 'eur', onScanned }));
    act(() => hook.result.current.scanPhoto(new File(['x'], 'receipt.jpg')));
    await settle();

    // Walked out while the photo was still uploading — nothing to cancel yet.
    act(() => hook.result.current.abort());
    expect(cancelTask).not.toHaveBeenCalled();

    // The upload lands anyway: that task belongs to nobody now.
    await act(async () => { resolveUpload({ id: 43 }); });
    await settle();

    expect(cancelTask).toHaveBeenCalledWith(43);
    expect(FakeEventSource.last).toBeNull();
    expect(hook.result.current.running).toBe(false);
  });

  it('abort drops the task so no empty bill is left behind', async () => {
    const { hook } = await start();
    const stream = FakeEventSource.last!;

    act(() => void vi.advanceTimersByTime(30_000));
    act(() => hook.result.current.abort());

    expect(cancelTask).toHaveBeenCalledWith(42);
    expect(stream.closed).toBe(true);
    expect(hook.result.current.running).toBe(false);
    expect(hook.result.current.abortable).toBe(false);
  });

  it('counts a scan against the day once it is accepted', async () => {
    await start();

    expect(loadPro).toHaveBeenCalledWith(1);
  });

  it('returns to the choice of source when the free scans are used up', async () => {
    upload.mockRejectedValue({ isAxiosError: true, response: { status: 402, data: { detail: { code: 'SCAN_LIMIT', limit: 3 } } } });

    const { hook } = await start();

    expect(hook.result.current.running).toBe(false);
    expect(hook.result.current.failed).toBe(false);
    expect(FakeEventSource.last).toBeNull();
  });
});
