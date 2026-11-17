import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { billFixture } from '@/test/billFixtures';

const api = vi.hoisted(() => ({ updateBill: vi.fn() }));
vi.mock('@/lib/api/bills', () => api);
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));
vi.mock('@/components/ui/NumericKeypad', () => ({ default: () => null }));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ language: 'en', t: (key: string) => key }),
}));

import HeadcountEditor from './HeadcountEditor';

const bill = billFixture({ expected_people: 3 });

beforeEach(() => {
  vi.clearAllMocks();
});

describe('HeadcountEditor', () => {
  it('shows how many seats there are until the owner opens it', () => {
    render(<HeadcountEditor bill={bill} userId={10} onBillUpdate={vi.fn()} />);

    expect(screen.getByText(String(bill.participants.length))).toBeInTheDocument();
    expect(screen.queryByText(/\//)).toBeNull();
    expect(screen.getByRole('button', { name: 'bill.editPeople' })).toBeInTheDocument();
  });

  it('saves a nudged headcount and hands back the updated bill', async () => {
    const updated = billFixture({ expected_people: 4 });
    api.updateBill.mockResolvedValue(updated);
    const onBillUpdate = vi.fn();
    render(<HeadcountEditor bill={bill} userId={10} onBillUpdate={onBillUpdate} />);

    fireEvent.click(screen.getByRole('button', { name: 'bill.editPeople' }));
    fireEvent.click(screen.getByRole('button', { name: '+' }));
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(api.updateBill).toHaveBeenCalledWith(1, { expected_people: 4, user_id: 10 }));
    expect(onBillUpdate).toHaveBeenCalledWith(updated);
    expect(screen.getByRole('button', { name: 'bill.editPeople' })).toBeInTheDocument();
  });

  it('never goes below the people already seated', () => {
    render(<HeadcountEditor bill={bill} userId={10} onBillUpdate={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'bill.editPeople' }));
    for (let i = 0; i < 4; i++) fireEvent.click(screen.getByRole('button', { name: '−' }));

    expect(screen.getByRole('button', { name: 'bill.peopleCount' })).toHaveTextContent('2');
  });

  it('closes without a request when nothing changed', () => {
    render(<HeadcountEditor bill={bill} userId={10} onBillUpdate={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'bill.editPeople' }));
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }));

    expect(api.updateBill).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'bill.editPeople' })).toBeInTheDocument();
  });
});
