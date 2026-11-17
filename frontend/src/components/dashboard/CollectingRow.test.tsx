import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { listedBillFixture } from '@/test/billFixtures';
import type { BillCollection } from '@/types/api';

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 10 } };
  const useStore = Object.assign(
    (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});

import CollectingRow from './CollectingRow';

const NOW = new Date('2026-10-01T12:00:00Z');
const minutes = (n: number) => new Date(NOW.getTime() + n * 60_000).toISOString();

const renderRow = (collection: BillCollection | null, overrides = {}) => {
  const onRemind = vi.fn().mockResolvedValue(undefined);
  const onDelete = vi.fn().mockResolvedValue(undefined);
  render(
    <CollectingRow
      bill={listedBillFixture({ owner_id: 10, title: 'Dinner', total_sum: 300000, collection, ...overrides })}
      onRemind={onRemind}
      onDelete={onDelete}
    />,
  );
  return { onRemind, onDelete };
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe('CollectingRow', () => {
  it('shows what is left and rings the bell for everyone who owes', async () => {
    const { onRemind } = renderRow({ left: 168000, remindable: 2, reminded_at: null, next_reminder_at: null });

    expect(screen.getByText('left')).toBeInTheDocument();
    expect(screen.getByText('168 000 uzs')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remind those who haven’t paid' }));

    await waitFor(() => expect(onRemind).toHaveBeenCalledWith(expect.objectContaining({ id: 1 })));
  });

  it('rests the bell for the hour after it rang and says when it did', () => {
    renderRow({ left: 240000, remindable: 0, reminded_at: minutes(-20), next_reminder_at: minutes(40) });

    expect(screen.getByRole('button', { name: 'Again in 40 min' })).toBeDisabled();
    expect(screen.getByText('reminded 20 min ago')).toBeInTheDocument();
  });

  it('has no bell once everyone has paid', () => {
    renderRow({ left: 0, remindable: 0, reminded_at: null, next_reminder_at: null }, { payers_count: 2, payers_paid: 2 });

    expect(screen.queryByRole('button', { name: /Remind|Again/ })).not.toBeInTheDocument();
    expect(screen.getByText('all paid')).toBeInTheDocument();
    expect(screen.getByText('300 000 uzs')).toBeInTheDocument();
  });

  it('deletes the bill from «⋯» after asking in the row', async () => {
    const { onDelete } = renderRow(null);

    fireEvent.click(screen.getByRole('button', { name: 'Delete bill' }));
    expect(screen.getByText('Delete this bill?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(1));
  });
});
