import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BILL_AUTO_REFRESH_INTERVAL_MS,
  useBillAutoRefresh,
} from './useBillAutoRefresh';

describe('useBillAutoRefresh', () => {
  let visibilityState: DocumentVisibilityState;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-15T12:00:00Z'));
    visibilityState = 'visible';
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibilityState,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls visible bill pages every 10 seconds', () => {
    const onRefresh = vi.fn();
    renderHook(() => useBillAutoRefresh(7, onRefresh));

    act(() => {
      vi.advanceTimersByTime(BILL_AUTO_REFRESH_INTERVAL_MS - 1);
    });
    expect(onRefresh).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(BILL_AUTO_REFRESH_INTERVAL_MS);
    });
    expect(onRefresh).toHaveBeenCalledTimes(2);
  });

  it('skips hidden polling and refreshes once when the page resumes', () => {
    visibilityState = 'hidden';
    const onRefresh = vi.fn();
    renderHook(() => useBillAutoRefresh(7, onRefresh));

    act(() => {
      vi.advanceTimersByTime(BILL_AUTO_REFRESH_INTERVAL_MS * 3);
    });
    expect(onRefresh).not.toHaveBeenCalled();

    visibilityState = 'visible';
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new Event('focus'));
    });

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('does not refresh without a bill id', () => {
    const onRefresh = vi.fn();
    renderHook(() => useBillAutoRefresh(undefined, onRefresh));

    act(() => {
      vi.advanceTimersByTime(BILL_AUTO_REFRESH_INTERVAL_MS);
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new Event('focus'));
    });

    expect(onRefresh).not.toHaveBeenCalled();
  });
});
