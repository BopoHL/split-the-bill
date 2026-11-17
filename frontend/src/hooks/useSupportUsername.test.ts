import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/appConfig', () => ({ getAppConfig: vi.fn() }));

// A fresh module per case: it remembers the answer for the whole launch.
beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('useSupportUsername', () => {
  it('asks the server once, however many menus want it', async () => {
    const { getAppConfig } = await import('@/lib/api/appConfig');
    vi.mocked(getAppConfig).mockResolvedValue({ support_username: 'split_help' });
    const { useSupportUsername } = await import('./useSupportUsername');

    const first = renderHook(() => useSupportUsername());
    const second = renderHook(() => useSupportUsername());

    await waitFor(() => expect(first.result.current).toBe('split_help'));
    await waitFor(() => expect(second.result.current).toBe('split_help'));
    expect(getAppConfig).toHaveBeenCalledTimes(1);
  });

  it('asks again next time when the server could not say', async () => {
    const { getAppConfig } = await import('@/lib/api/appConfig');
    vi.mocked(getAppConfig).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ support_username: 'split_help' });
    const { useSupportUsername } = await import('./useSupportUsername');

    const offline = renderHook(() => useSupportUsername());
    await waitFor(() => expect(getAppConfig).toHaveBeenCalledTimes(1));
    expect(offline.result.current).toBeNull();

    const later = renderHook(() => useSupportUsername());
    await waitFor(() => expect(later.result.current).toBe('split_help'));
  });
});
