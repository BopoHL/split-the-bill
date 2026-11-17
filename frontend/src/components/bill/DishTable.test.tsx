import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { billFixture, itemFixture, participantFixture } from '@/test/billFixtures';

vi.mock('@/lib/store/useStore', () => ({ useStore: (selector?: (state: { language: string }) => unknown) => selector ? selector({ language: 'en' }) : { language: 'en' } }));
vi.mock('@/lib/api/bills', () => ({ assignBillItemsBatch: vi.fn() }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/toast', () => toast);
const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));

import { assignBillItemsBatch } from '@/lib/api/bills';
import DishTable from './DishTable';

const bob = participantFixture({ id: 2, user_id: 20, username: 'bob', name: 'Bob', seat_index: 1 });
const bill = billFixture({
  participants: [participantFixture(), bob],
  items: [itemFixture({ id: 6, name: 'Plov', count: 2, item_sum: 8000, portions: [[], []] })],
});

const card = () => screen.getAllByRole('button', { name: /Plov/ })[0];
const seat = (name: string) => screen.getByLabelText(name, { selector: '[data-seat]' });

/** Points the finger at a seat: jsdom lays nothing out, so the hit test is told. */
const over = (element: Element | null) => {
  document.elementFromPoint = vi.fn(() => element);
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(assignBillItemsBatch).mockResolvedValue(bill);
});

afterEach(() => vi.useRealTimers());

const table = (overrides = bill) => {
  const onBillUpdate = vi.fn();
  render(<DishTable bill={overrides} currentUserId={10} onBillUpdate={onBillUpdate} onClose={vi.fn()} />);
  return onBillUpdate;
};

describe('DishTable', () => {
  it('gives a dish held and dragged onto someone to them', async () => {
    const onBillUpdate = table();

    fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 1 });
    act(() => vi.advanceTimersByTime(300));
    over(seat('Bob'));
    fireEvent.pointerMove(card(), { clientX: 40, clientY: 200, pointerId: 1 });
    expect(seat('Bob')).toHaveClass('scale-110');
    fireEvent.pointerUp(card(), { clientX: 40, clientY: 200, pointerId: 1 });

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 6, participant_id: 2, is_assigned: true, portion_index: 0, expected_count: 2 },
    ]));
    expect(onBillUpdate).toHaveBeenCalledWith(bill);
    expect(track).toHaveBeenCalledWith('items_assigned', { bill_id: 1, via: 'table', changes: 1 });
  });

  it('the first tap after a drop opens the dish, though no click followed the drop', async () => {
    table();
    fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 1 });
    act(() => vi.advanceTimersByTime(300));
    over(seat('Bob'));
    fireEvent.pointerUp(card(), { clientX: 40, clientY: 200, pointerId: 1 });
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalled());

    fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 2 });
    fireEvent.pointerUp(card(), { clientX: 10, clientY: 10, pointerId: 2 });
    fireEvent.click(card());

    expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeInTheDocument();
  });

  it('a finger that moves before the dish is held is scrolling, not dragging', () => {
    table();

    fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(card(), { clientX: 10, clientY: 60, pointerId: 1 });
    act(() => vi.advanceTimersByTime(300));
    over(seat('Bob'));
    fireEvent.pointerUp(card(), { clientX: 40, clientY: 200, pointerId: 1 });

    expect(assignBillItemsBatch).not.toHaveBeenCalled();
  });

  it('will not put a dish on someone who has already paid', () => {
    table({ ...bill, participants: [participantFixture(), { ...bob, is_paid: true }] });

    fireEvent.pointerDown(card(), { clientX: 10, clientY: 10, pointerId: 1 });
    act(() => vi.advanceTimersByTime(300));
    over(seat('Bob'));
    fireEvent.pointerUp(card(), { clientX: 40, clientY: 200, pointerId: 1 });

    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    expect(toast.showToast).toHaveBeenCalled();
  });

  it('a tap opens the dish to take people off it', () => {
    table();

    fireEvent.click(card());

    expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeInTheDocument();
  });
});
