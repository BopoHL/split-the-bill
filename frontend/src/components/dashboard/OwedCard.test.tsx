import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({ getOwed: vi.fn(), remindEveryoneWhoOwes: vi.fn() }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/api/reminders', () => api);
vi.mock('@/lib/toast', () => toast);
vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 10 } };
  const useStore = Object.assign(
    (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});

import OwedCard from './OwedCard';
import { usePro } from '@/lib/store/usePro';
import type { ProOverview } from '@/types/pro';

const FREE: ProOverview = {
  active: false, until: null, trial: false, subscription: false, plans: [], free_scans_per_day: 3, scans_left_today: 3,
  free_reminders_per_month: 3, reminders_left_this_month: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  usePro.setState({ overview: null, paywall: null });
});
afterEach(() => vi.useRealTimers());

describe('OwedCard', () => {
  it('shows what is owed in every currency and reminds everyone at once', async () => {
    api.getOwed
      .mockResolvedValueOnce({ totals: [{ currency: 'uzs', amount: 270000 }, { currency: 'usd', amount: 40 }], people: 3, bills: 2, remindable: 2 })
      .mockResolvedValueOnce({ totals: [{ currency: 'uzs', amount: 270000 }], people: 3, bills: 2, remindable: 0 });
    api.remindEveryoneWhoOwes.mockResolvedValue({ queued: 2, skipped: [] });

    render(<OwedCard userId={10} />);

    expect(await screen.findByText('Owed to you')).toBeInTheDocument();
    expect(screen.getByText('3 people')).toBeInTheDocument();
    expect(screen.getByText(/270/)).toBeInTheDocument();
    expect(screen.getByText(/40/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Remind everyone/ }));

    await waitFor(() => expect(api.remindEveryoneWhoOwes).toHaveBeenCalledWith(10));
    expect(toast.showToast).toHaveBeenCalledWith('Sending reminders: 2', 'success');
    expect(await screen.findByRole('button', { name: 'Everyone has been reminded' })).toBeDisabled();
  });

  it('counts down to when everyone may be reminded again, then asks again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-10-05T12:00:00Z'));
    const held = { totals: [{ currency: 'uzs', amount: 270000 }], people: 3, bills: 2, remindable: 0 };
    api.getOwed
      .mockResolvedValueOnce({ ...held, next_reminder_at: '2026-10-05T12:45:00+00:00' })
      .mockResolvedValue({ ...held, remindable: 3, next_reminder_at: null });

    render(<OwedCard userId={10} />);

    expect(await screen.findByRole('button', { name: 'Remind again in 45:00' })).toBeDisabled();
    await act(async () => {
      vi.advanceTimersByTime(45 * 60_000);
    });
    await waitFor(() => expect(api.getOwed).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('button', { name: /Remind everyone/ })).toBeEnabled();
  });

  it('stays while nobody owes, and a press says what to do first instead of opening the paywall', async () => {
    usePro.setState({ overview: FREE });
    api.getOwed.mockResolvedValue({ totals: [], people: 0, bills: 0, remindable: 0, why_nobody: 'unassigned' });

    render(<OwedCard userId={10} />);

    expect(await screen.findByText('Nobody yet')).toBeInTheDocument();
    expect(screen.queryByText(/people/)).toBeNull();
    const button = screen.getByRole('button', { name: /Remind everyone/ });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(button);

    expect(toast.showToast).toHaveBeenCalledWith('Assign the items first', 'info');
    expect(usePro.getState().paywall).toBeNull();
    expect(api.remindEveryoneWhoOwes).not.toHaveBeenCalled();
  });

  it('reminds everyone without Pro while the month’s free presses last', async () => {
    usePro.setState({ overview: { ...FREE, reminders_left_this_month: 2 } });
    api.getOwed.mockResolvedValue({ totals: [{ currency: 'uzs', amount: 270000 }], people: 3, bills: 2, remindable: 2 });
    api.remindEveryoneWhoOwes.mockResolvedValue({ queued: 2, skipped: [] });

    render(<OwedCard userId={10} />);
    const button = await screen.findByRole('button', { name: /Remind everyone/ });
    expect(button).not.toHaveAccessibleName(/Pro/);
    fireEvent.click(button);

    await waitFor(() => expect(api.remindEveryoneWhoOwes).toHaveBeenCalledWith(10));
    expect(usePro.getState().paywall).toBeNull();
  });

  it('opens the paywall instead of reminding once the free presses are spent', async () => {
    usePro.setState({ overview: FREE });
    api.getOwed.mockResolvedValue({ totals: [{ currency: 'uzs', amount: 270000 }], people: 3, bills: 2, remindable: 2 });

    render(<OwedCard userId={10} />);
    fireEvent.click(await screen.findByRole('button', { name: /Remind everyone.*Pro/ }));

    expect(usePro.getState().paywall).toBe('reminders');
    expect(api.remindEveryoneWhoOwes).not.toHaveBeenCalled();
  });
});
