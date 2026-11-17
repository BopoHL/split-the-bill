import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { listedBillFixture } from '@/test/billFixtures';

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 10 } };
  const useStore = Object.assign(
    (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});
vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: { PayDetailsCopied: 'pay_details_copied' } }));

import OwingRow, { UNDO_WINDOW_MS } from './OwingRow';

const bill = listedBillFixture({
  id: 8, title: 'Taxi', owner_id: 20, owner: { name: 'Alice', avatar_url: null },
  payment_details: '8600 1234 5678 9012', my_seat: { id: 81, amount: 42500, is_paid: false },
});

afterEach(() => vi.useRealTimers());

describe('OwingRow', () => {
  it('shows whose bill it is and my share, with the card and «I paid»', () => {
    render(<OwingRow bill={bill} onMarkPaid={vi.fn()} onSettled={vi.fn()} />);

    expect(screen.getByText('Alice is collecting')).toBeInTheDocument();
    expect(screen.getByText('42 500 uzs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Card' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'I paid' })).toBeInTheDocument();
  });

  it('moves the bill to the paid ones once the undo window is over', async () => {
    vi.useFakeTimers();
    const onMarkPaid = vi.fn().mockResolvedValue(undefined);
    const onSettled = vi.fn();
    render(<OwingRow bill={bill} onMarkPaid={onMarkPaid} onSettled={onSettled} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'I paid' }));
    });
    expect(onMarkPaid).toHaveBeenCalledWith(bill, true);
    expect(screen.getByRole('status')).toHaveTextContent('Payment marked');

    act(() => vi.advanceTimersByTime(UNDO_WINDOW_MS));
    expect(onSettled).toHaveBeenCalledWith(8);
  });

  it('keeps the bill where it is when the mark is undone', async () => {
    vi.useFakeTimers();
    const onMarkPaid = vi.fn().mockResolvedValue(undefined);
    const onSettled = vi.fn();
    render(<OwingRow bill={bill} onMarkPaid={onMarkPaid} onSettled={onSettled} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'I paid' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    });
    act(() => vi.advanceTimersByTime(UNDO_WINDOW_MS));

    expect(onMarkPaid).toHaveBeenLastCalledWith(bill, false);
    expect(onSettled).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'I paid' })).toBeInTheDocument();
  });

  it('says the share is not counted yet and offers nothing to pay', () => {
    render(<OwingRow bill={{ ...bill, my_seat: { id: 81, amount: 0, is_paid: false } }} onMarkPaid={vi.fn()} onSettled={vi.fn()} />);

    expect(screen.getByText('your share isn’t counted yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'I paid' })).not.toBeInTheDocument();
  });
});
