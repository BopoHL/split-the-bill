import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillStatus, type BillSeats } from '@/types/api';

const push = vi.fn();
let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useParams: () => ({ token: 'tok' }),
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 5 } };
  return {
    useStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));
vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: { ParticipantJoined: 'joined' } }));
vi.mock('@/components/layout/AppHeader', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/lib/api/bills', () => ({
  getSeatsByToken: vi.fn(),
  claimSeat: vi.fn(),
}));
vi.mock('@/lib/tour/arrival', () => ({ arriveAsGuest: vi.fn() }));

import { claimSeat, getSeatsByToken } from '@/lib/api/bills';
import { arriveAsGuest } from '@/lib/tour/arrival';
import JoinBillPage from './page';

const table: BillSeats = {
  bill_id: 1,
  title: 'Dinner',
  currency: 'uzs',
  status: BillStatus.OPEN,
  seats: [
    { id: 11, seat_index: 0, guest_name: null, display_name: 'me', avatar_url: null, is_taken: true, is_me: true, allocated_amount: 100, items: [] },
    { id: 12, seat_index: 1, guest_name: null, display_name: null, avatar_url: null, is_taken: false, is_me: false, allocated_amount: 200, items: [] },
  ],
};

describe('JoinBillPage — a personal invite that would move somebody', () => {
  beforeEach(() => {
    push.mockClear();
    vi.mocked(getSeatsByToken).mockResolvedValue(table);
    vi.mocked(claimSeat).mockResolvedValue({ id: 1 } as never);
  });

  it('asks about the invited seat straight away instead of showing a blind picker', async () => {
    searchParams = new URLSearchParams('seat=12');
    render(<JoinBillPage />);

    expect(await screen.findByText(/items assigned to you will be replaced/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /yes, move/i }));

    await waitFor(() => expect(claimSeat).toHaveBeenCalledWith(1, 12, 5, null, true, 'tok'));
    expect(arriveAsGuest).toHaveBeenCalledWith(1);
    expect(push).toHaveBeenCalledWith('/bill/1');
  });

  it('comes back from one failed poll instead of saying the bill is gone', async () => {
    searchParams = new URLSearchParams();
    vi.mocked(getSeatsByToken).mockRejectedValueOnce(new Error('Network Error'));
    render(<JoinBillPage />);
    expect(await screen.findByText('This bill no longer exists')).toBeInTheDocument();

    document.dispatchEvent(new Event('visibilitychange'));

    expect(await screen.findByText('me')).toBeInTheDocument();
    expect(screen.queryByText('This bill no longer exists')).toBeNull();
  });

  it('leaves the picker alone when no seat was named', async () => {
    searchParams = new URLSearchParams();
    render(<JoinBillPage />);

    await screen.findByText('me');
    expect(screen.queryByText(/items assigned to you will be replaced/i)).toBeNull();
  });
});
