import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mocks ---------------------------------------------------------
// useStore is mocked so the translator (which reads `language` from it)
// resolves to a deterministic locale without touching real Zustand
// state between tests.
vi.mock('@/lib/store/useStore', () => ({
  useStore: () => ({ language: 'en' }),
}));

const updateBillMock = vi.fn();
vi.mock('@/lib/api/bills', () => ({
  updateBill: (...args: unknown[]) => updateBillMock(...args),
}));

import BillTitleEditor from './BillTitleEditor';
import type { BillDetail, User } from '@/types/api';

const mkBill = (overrides: Partial<BillDetail> = {}): BillDetail =>
  ({
    id: 42,
    owner_id: 1,
    total_sum: 100,
    title: 'Dinner',
    payment_details: null,
    split_type: 'manual',
    status: 'open',
    unallocated_sum: 0,
    items: [],
    participants: [],
    ...overrides,
  }) as BillDetail;

const user: User = {
  id: 1,
  telegram_id: 99,
  username: 'tester',
  name: null,
  surname: null,
  avatar_url: null,
} as User;

describe('BillTitleEditor', () => {
  beforeEach(() => {
    updateBillMock.mockReset();
  });

  it('shows pencil only when canEdit is true', () => {
    const { rerender } = render(
      <BillTitleEditor
        bill={mkBill()}
        currentUser={user}
        setBill={vi.fn()}
        canEdit={false}
      />,
    );
    expect(screen.queryByLabelText(/rename/i)).toBeNull();

    rerender(
      <BillTitleEditor
        bill={mkBill()}
        currentUser={user}
        setBill={vi.fn()}
        canEdit={true}
      />,
    );
    expect(screen.getByLabelText(/rename/i)).toBeInTheDocument();
  });

  it('Enter saves: calls updateBill with new title and propagates response', async () => {
    const setBill = vi.fn();
    const updated = mkBill({ title: 'Lunch' });
    updateBillMock.mockResolvedValueOnce(updated);

    render(
      <BillTitleEditor
        bill={mkBill({ title: 'Dinner' })}
        currentUser={user}
        setBill={setBill}
        canEdit={true}
      />,
    );

    await userEvent.click(screen.getByLabelText(/rename/i));
    const input = screen.getByDisplayValue('Dinner') as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, 'Lunch');
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(updateBillMock).toHaveBeenCalledWith(42, {
        title: 'Lunch',
        user_id: 1,
      });
    });
    expect(setBill).toHaveBeenCalledWith(updated);
  });

  it('Esc cancels without calling the API', async () => {
    render(
      <BillTitleEditor
        bill={mkBill({ title: 'Dinner' })}
        currentUser={user}
        setBill={vi.fn()}
        canEdit={true}
      />,
    );

    await userEvent.click(screen.getByLabelText(/rename/i));
    const input = screen.getByDisplayValue('Dinner') as HTMLInputElement;
    await userEvent.type(input, 'Changed', { skipClick: true });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(updateBillMock).not.toHaveBeenCalled();
    // back to view mode
    expect(screen.getByText('Dinner')).toBeInTheDocument();
  });

  it('no-op save when title unchanged (no API call)', async () => {
    render(
      <BillTitleEditor
        bill={mkBill({ title: 'Dinner' })}
        currentUser={user}
        setBill={vi.fn()}
        canEdit={true}
      />,
    );

    await userEvent.click(screen.getByLabelText(/rename/i));
    const input = screen.getByDisplayValue('Dinner') as HTMLInputElement;
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(updateBillMock).not.toHaveBeenCalled();
  });
});
