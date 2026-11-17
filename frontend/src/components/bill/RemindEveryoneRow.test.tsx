import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { billFixture, participantFixture } from '@/test/billFixtures';
import type { BillParticipant } from '@/types/api';

const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/toast', () => toast);
vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 10 } };
  return {
    useStore: (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
  };
});

import RemindEveryoneRow from './RemindEveryoneRow';

const NOW = new Date('2026-10-01T12:00:00Z');
const minutes = (n: number) => new Date(NOW.getTime() + n * 60_000).toISOString();

const owner = participantFixture({ id: 1, user_id: 10, allocated_amount: 500 });
const dana = participantFixture({ id: 2, user_id: 20, allocated_amount: 500 });
const oleg = participantFixture({ id: 3, user_id: 30, allocated_amount: 700 });
const guest = participantFixture({ id: 4, user_id: null, is_guest: true, allocated_amount: 300 });

const renderRow = (participants: BillParticipant[], onRemindEveryone = vi.fn().mockResolvedValue(undefined)) => {
  render(<RemindEveryoneRow bill={billFixture({ owner_id: 10, participants })} onRemindEveryone={onRemindEveryone} />);
  return onRemindEveryone;
};

beforeEach(() => {
  toast.showToast.mockClear();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe('RemindEveryoneRow', () => {
  it('counts who can be reminded now and reminds them in one press', async () => {
    const remind = renderRow([owner, dana, oleg, guest]);

    const button = screen.getByRole('button', { name: /Remind everyone who hasn’t paid/ });
    expect(button).toHaveTextContent('2');
    fireEvent.click(button);

    await waitFor(() => expect(remind).toHaveBeenCalledOnce());
  });

  it('counts down to when it can be pressed again once everyone has had theirs', () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    renderRow([
      owner,
      { ...dana, reminder: { status: 'sent', at: minutes(-30), failure: null, next_at: minutes(30) } },
      { ...oleg, reminder: { status: 'sent', at: minutes(-10), failure: null, next_at: minutes(50) } },
    ]);

    expect(screen.getByRole('button', { name: 'Remind again in 30:00' })).toBeDisabled();

    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.getByRole('button', { name: 'Remind again in 29:58' })).toBeDisabled();

    // The first of them may be reminded again: the button wakes up by itself.
    act(() => vi.advanceTimersByTime(30 * 60_000));
    const button = screen.getByRole('button', { name: /Remind everyone who hasn’t paid/ });
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent('1');
  });

  it('stays with nobody to remind, and a press says what to do first', () => {
    const remind = renderRow([owner, { ...dana, allocated_amount: 0 }, guest]);

    const button = screen.getByRole('button', { name: /Remind everyone who hasn’t paid/ });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).not.toHaveTextContent(/\d/);
    fireEvent.click(button);

    expect(toast.showToast).toHaveBeenCalledWith('Assign the items first', 'info');
    expect(remind).not.toHaveBeenCalled();
  });

  it('tells apart guests yet to join and everyone having paid', () => {
    renderRow([owner, { ...dana, is_paid: true }, guest]);
    fireEvent.click(screen.getByRole('button'));
    expect(toast.showToast).toHaveBeenLastCalledWith('Only people who joined the bill can be reminded', 'info');
    cleanup();

    renderRow([owner, { ...dana, is_paid: true }, { ...guest, is_paid: true }]);
    fireEvent.click(screen.getByRole('button'));
    expect(toast.showToast).toHaveBeenLastCalledWith('Everyone has already paid', 'info');
  });
});
