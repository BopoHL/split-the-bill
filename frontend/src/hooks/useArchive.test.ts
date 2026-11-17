import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { Bill } from '@/types/api';

const api = vi.hoisted(() => ({ getUserBills: vi.fn(), getBillCounts: vi.fn() }));
vi.mock('@/lib/api/bills', () => api);
vi.mock('@/lib/store/useStore', () => ({ useStore: () => ({ language: 'en' }) }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/toast', () => toast);

import { useArchive } from './useArchive';

const bill = (id: number, ownerId = 1) => ({ id, owner_id: ownerId, title: `Bill ${id}` }) as Bill;

describe('useArchive', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getUserBills.mockImplementation((_user: number, _offset: number, _size: number, _status: string, { role }: { role?: string }) =>
      Promise.resolve(role === 'owner' ? [bill(1)] : [bill(1), bill(2, 7)]));
    api.getBillCounts.mockResolvedValue({ all: 2, owned: 1, joined: 1 });
  });

  it('shows a filter seen before at once while asking for it again', async () => {
    const { result } = renderHook(() => useArchive(1));
    await waitFor(() => expect(result.current.bills).toHaveLength(2));

    act(() => result.current.setRole('owner'));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.bills).toHaveLength(1));

    let release: (bills: Bill[]) => void = () => {};
    api.getUserBills.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    act(() => result.current.setRole(undefined));

    expect(result.current.loading).toBe(false);
    expect(result.current.bills.map((shown) => shown.id)).toEqual([1, 2]);
    expect(api.getUserBills).toHaveBeenCalledTimes(3);
    await act(async () => release([bill(1), bill(2, 7), bill(3)]));
    expect(result.current.bills).toHaveLength(3);
  });

  it('forgets a deleted bill everywhere it was found, counts included', async () => {
    const { result } = renderHook(() => useArchive(1));
    await waitFor(() => expect(result.current.bills).toHaveLength(2));

    act(() => result.current.remove(1));

    expect(result.current.bills.map((shown) => shown.id)).toEqual([2]);
    expect(result.current.counts).toEqual({ all: 1, owned: 0, joined: 1 });
    expect(result.current.total).toBe(1);
    expect(result.current.recent.map((shown) => shown.id)).toEqual([2]);
  });

  it('pages on from the bills shown, a deleted one no longer among them', async () => {
    const page = (from: number) => Array.from({ length: 15 }, (_, index) => bill(100 + from + index));
    api.getUserBills.mockImplementation((_user: number, offset: number, _size: number, _status: string, { query }: { query?: string }) =>
      Promise.resolve(query === 'deep' ? page(offset) : []));
    const { result } = renderHook(() => useArchive(1));
    act(() => result.current.setQuery('deep'));
    await waitFor(() => expect(result.current.bills).toHaveLength(15));

    act(() => result.current.remove(100));
    expect(result.current.hasMore).toBe(true);
    await act(() => result.current.loadMore());

    expect(api.getUserBills).toHaveBeenLastCalledWith(1, 14, 15, 'closed', { query: 'deep', role: undefined });
    expect(result.current.bills).toHaveLength(29);
  });

  it('says when the archive could not be loaded and asks again on retry', async () => {
    api.getUserBills.mockRejectedValueOnce(new Error('offline'));
    const { result } = renderHook(() => useArchive(2));
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.loading).toBe(false);

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.bills).toHaveLength(2));
    expect(result.current.failed).toBe(false);
  });
});
