import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { billFixture } from '@/test/billFixtures';

const api = vi.hoisted(() => ({
  prepareShareMessage: vi.fn(),
  inviteDeepLink: (token: string) => `https://t.me/bot/app?startapp=join_${token}`,
}));
const telegram = vi.hoisted(() => ({ canShareMessage: vi.fn(), shareMessage: vi.fn() }));
const track = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api/bills', () => api);
vi.mock('@/lib/api/invites', () => ({ createInvite: vi.fn() }));
vi.mock('@/lib/telegram/share', () => telegram);
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ language: 'ru', t: (key: string) => key }),
}));

import InvitePrompt from './InvitePrompt';
import { useInvitePrompt } from '@/lib/store/useInvitePrompt';

const bill = billFixture({ id: 7 });

beforeEach(() => {
  vi.clearAllMocks();
  useInvitePrompt.setState({ billId: null });
  telegram.canShareMessage.mockReturnValue(true);
  telegram.shareMessage.mockReturnValue(true);
  api.prepareShareMessage.mockResolvedValue('PREPARED-1');
});

describe('InvitePrompt', () => {
  it('stays away from a bill that was not just made', () => {
    render(<InvitePrompt bill={bill} />);

    expect(screen.queryByText('bill.invitePromptTitle')).toBeNull();
    expect(track).not.toHaveBeenCalled();
  });

  it('asks once to send a bill just made to the table, and sends it', async () => {
    useInvitePrompt.getState().offer(bill.id);
    render(<InvitePrompt bill={bill} />);

    expect(await screen.findByText('bill.invitePromptTitle')).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith('invite_prompt_shown', { bill_id: 7 });

    fireEvent.click(screen.getByRole('button', { name: /bill.inviteParticipants/ }));

    await waitFor(() => expect(telegram.shareMessage).toHaveBeenCalledWith('PREPARED-1'));
    expect(track).toHaveBeenCalledWith('share_invite', { method: 'message', channel: 'prepared', bill_id: 7 });
    await waitFor(() => expect(screen.queryByText('bill.invitePromptTitle')).toBeNull());
  });

  it('is not asked again when the bill is drawn anew, answered or not', async () => {
    useInvitePrompt.getState().offer(bill.id);
    const first = render(<InvitePrompt bill={bill} />);
    expect(await screen.findByText('bill.invitePromptTitle')).toBeInTheDocument();
    first.unmount();

    render(<InvitePrompt bill={bill} />);

    expect(screen.queryByText('bill.invitePromptTitle')).toBeNull();
    expect(track.mock.calls.filter(([event]) => event === 'invite_prompt_shown')).toHaveLength(1);
  });

  it('can be put off', async () => {
    useInvitePrompt.getState().offer(bill.id);
    render(<InvitePrompt bill={bill} />);

    fireEvent.click(await screen.findByRole('button', { name: 'bill.invitePromptLater' }));

    expect(track).toHaveBeenCalledWith('invite_prompt_dismissed', { bill_id: 7 });
    await waitFor(() => expect(screen.queryByText('bill.invitePromptTitle')).toBeNull());
  });
});
