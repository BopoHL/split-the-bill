import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createPaymentMethod, deletePaymentMethod, listPaymentMethods } from '@/lib/api/paymentMethods';
import { useSavedPaymentMethods } from './useSavedPaymentMethods';

vi.mock('@/lib/store/useStore', () => {
  const state = { currentUser: { id: 5 } };
  return { useStore: (selector: (s: typeof state) => unknown) => selector(state) };
});
vi.mock('@/lib/api/paymentMethods', () => ({
  listPaymentMethods: vi.fn(),
  createPaymentMethod: vi.fn(),
  deletePaymentMethod: vi.fn(),
}));

const saved = [{ id: 1, label: null, value: 'CARD-A' }];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listPaymentMethods).mockResolvedValue(saved);
});

describe('useSavedPaymentMethods', () => {
  it('loads the saved details and tells the caller', async () => {
    const onLoad = vi.fn();
    const { result } = renderHook(() => useSavedPaymentMethods(onLoad));

    await waitFor(() => expect(result.current.methods).toEqual(saved));
    expect(onLoad).toHaveBeenCalledWith(saved);
    expect(listPaymentMethods).toHaveBeenCalledWith(5);
  });

  it('keeps new details once and does not keep the same twice', async () => {
    vi.mocked(createPaymentMethod).mockResolvedValue({ id: 2, label: null, value: 'CARD-B' });
    const { result } = renderHook(() => useSavedPaymentMethods());
    await waitFor(() => expect(result.current.methods).toHaveLength(1));

    await act(() => result.current.add('CARD-A'));
    await act(() => result.current.add('CARD-B'));

    expect(createPaymentMethod).toHaveBeenCalledTimes(1);
    expect(createPaymentMethod).toHaveBeenCalledWith(5, { value: 'CARD-B' });
    expect(result.current.methods.map((method) => method.value)).toEqual(['CARD-A', 'CARD-B']);
  });

  it('takes removed details off the list straight away and brings them back if that fails', async () => {
    vi.mocked(deletePaymentMethod).mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useSavedPaymentMethods());
    await waitFor(() => expect(result.current.methods).toHaveLength(1));

    await act(() => result.current.remove(1));

    expect(deletePaymentMethod).toHaveBeenCalledWith(5, 1);
    await waitFor(() => expect(result.current.methods).toEqual(saved));
  });
});
