import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createPaymentMethod, deletePaymentMethod, listPaymentMethods } from '@/lib/api/paymentMethods';
import { usePaymentChoice } from './usePaymentChoice';

vi.mock('@/lib/store/useStore', () => {
  const state = { currentUser: { id: 5 } };
  return { useStore: (selector: (s: typeof state) => unknown) => selector(state) };
});
vi.mock('@/lib/api/paymentMethods', () => ({
  listPaymentMethods: vi.fn(),
  createPaymentMethod: vi.fn(),
  deletePaymentMethod: vi.fn(),
}));

const humo = { id: 1, label: null, value: '9860 1100 2200 4411' };
const uzcard = { id: 2, label: null, value: '8600 1234 5678 9012' };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listPaymentMethods).mockResolvedValue([humo, uzcard]);
  vi.mocked(deletePaymentMethod).mockResolvedValue(undefined);
});

const loaded = async (options?: Parameters<typeof usePaymentChoice>[0]) => {
  const view = renderHook(() => usePaymentChoice(options));
  await waitFor(() => expect(view.result.current.methods).toHaveLength(2));
  return view;
};

describe('usePaymentChoice', () => {
  it('starts on the saved card that is on the bill, however it is spaced', async () => {
    const { result } = await loaded({ current: '8600123456789012' });

    expect(result.current.selectedId).toBe(2);
    expect(result.current.value).toBe('8600 1234 5678 9012');
  });

  it('keeps a bill’s card that is not saved in the field', async () => {
    const { result } = await loaded({ current: '4169 5858 0000 1111' });

    expect(result.current.isNew).toBe(true);
    expect(result.current.value).toBe('4169 5858 0000 1111');
  });

  it('offers the preferred card, or else the first one, when the bill has none', async () => {
    expect((await loaded({ preferred: '8600 1234 5678 9012' })).result.current.selectedId).toBe(2);
    expect((await loaded()).result.current.selectedId).toBe(1);
  });

  it('leaves a choice the person already made alone when the cards arrive late', async () => {
    const { result } = renderHook(() => usePaymentChoice());
    act(() => result.current.changeDraft('5614'));
    await waitFor(() => expect(result.current.methods).toHaveLength(2));

    expect(result.current.isNew).toBe(true);
    expect(result.current.value).toBe('5614');
  });

  it('falls back to another card when the chosen one is removed', async () => {
    const { result } = await loaded();

    act(() => result.current.remove(humo));

    expect(result.current.isNew).toBe(true);
    expect(deletePaymentMethod).toHaveBeenCalledWith(5, 1);
  });

  it('keeps a typed card only when asked to remember it', async () => {
    vi.mocked(createPaymentMethod).mockResolvedValue({ id: 3, label: null, value: '4169 5858 0000 1111' });
    const { result } = await loaded();
    act(() => result.current.changeDraft('4169585800001111'));

    act(() => result.current.setRemember(false));
    await act(async () => { await result.current.keep(); });
    expect(createPaymentMethod).not.toHaveBeenCalled();

    act(() => result.current.setRemember(true));
    await act(async () => { await result.current.keep(); });
    expect(createPaymentMethod).toHaveBeenCalledWith(5, { value: '4169 5858 0000 1111' });
  });
});
