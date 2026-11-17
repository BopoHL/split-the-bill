import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BillDetail } from '@/types/api';

const api = vi.hoisted(() => ({
  prepareShareMessage: vi.fn(),
  inviteDeepLink: (token: string) => `https://t.me/bot/app?startapp=join_${token}`,
}));
const invites = vi.hoisted(() => ({ createInvite: vi.fn() }));
const telegram = vi.hoisted(() => ({ canShareMessage: vi.fn(), shareMessage: vi.fn() }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock('@/lib/api/bills', () => api);
vi.mock('@/lib/api/invites', () => invites);
vi.mock('@/lib/telegram/share', () => telegram);
vi.mock('@/lib/toast', () => toast);
const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ language: 'ru', t: (key: string) => key }),
}));

import { useBillInvite } from './useBillInvite';

const bill = { id: 7, public_token: 'tok' } as BillDetail;

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  telegram.canShareMessage.mockReturnValue(true);
  telegram.shareMessage.mockReturnValue(true);
  api.prepareShareMessage.mockResolvedValue('PREPARED-1');
});

describe('useBillInvite share', () => {
  it('sends the prepared post every time, not only the first', async () => {
    const { result } = renderHook(() => useBillInvite(bill));

    await act(() => result.current.share());
    await act(() => result.current.share());

    expect(api.prepareShareMessage).toHaveBeenCalledWith(7, 'ru');
    expect(telegram.shareMessage).toHaveBeenCalledTimes(2);
    expect(telegram.shareMessage).toHaveBeenCalledWith('PREPARED-1');
    expect(toast.showToast).not.toHaveBeenCalled();
    expect(track).toHaveBeenCalledWith('share_invite', { method: 'message', channel: 'prepared', bill_id: 7 });
  });

  it('counts showing the QR as an invite of its own', async () => {
    invites.createInvite.mockResolvedValue({ deep_link: 'https://t.me/bot/app?startapp=inv_q' });
    const { result } = renderHook(() => useBillInvite(bill));

    await act(() => result.current.openQr());

    expect(track).toHaveBeenCalledWith('share_invite', { method: 'qr', channel: 'qr', bill_id: 7 });
  });

  it('asks an old client to update Telegram instead of sending a plain link', async () => {
    telegram.canShareMessage.mockReturnValue(false);
    const { result } = renderHook(() => useBillInvite(bill));

    await act(() => result.current.share());

    expect(api.prepareShareMessage).not.toHaveBeenCalled();
    expect(toast.showToast).toHaveBeenCalledWith('bill.shareUnsupported');
  });

  it('reports a post the server could not prepare', async () => {
    api.prepareShareMessage.mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useBillInvite(bill));

    await act(() => result.current.share());

    expect(telegram.shareMessage).not.toHaveBeenCalled();
    expect(toast.showToast).toHaveBeenCalledWith('common.error');
    expect(result.current.sharing).toBe(false);
  });
});

describe('useBillInvite QR', () => {
  it('shows the minted link that credits the sharer', async () => {
    invites.createInvite.mockResolvedValue({ deep_link: 'https://t.me/bot/app?startapp=inv_abc' });
    const { result } = renderHook(() => useBillInvite(bill));

    await act(() => result.current.openQr());

    expect(invites.createInvite).toHaveBeenCalledWith(7, 'qr');
    expect(result.current.qrLink).toBe('https://t.me/bot/app?startapp=inv_abc');
  });

  it('falls back to the bill link when minting fails', async () => {
    invites.createInvite.mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useBillInvite(bill));

    await act(() => result.current.openQr());

    expect(result.current.qrLink).toBe('https://t.me/bot/app?startapp=join_tok');
  });
});
