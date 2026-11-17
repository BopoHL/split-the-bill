import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render } from '@testing-library/react';

const scan = vi.hoisted((): { onScanned?: (billId: number) => void } => ({}));

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currency: 'uzs', currentUser: { id: 1, settings: {} } };
  return { useStore: (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state) };
});
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/api/paymentMethods', () => ({
  listPaymentMethods: vi.fn().mockResolvedValue([]),
  createPaymentMethod: vi.fn(),
  deletePaymentMethod: vi.fn(),
}));
vi.mock('./useReceiptScan', () => ({
  useReceiptScan: (args: { onScanned: (billId: number) => void }) => {
    scan.onScanned = args.onScanned;
    return {
      running: false, mode: 'photo', phase: 'creating', failed: false, abortable: true,
      scanPhoto: vi.fn(), scanQr: vi.fn(), abort: vi.fn(), retry: vi.fn(),
    };
  },
}));

import CreateBillWizard from './CreateBillWizard';
import { useInvitePrompt } from '@/lib/store/useInvitePrompt';
import { useTour } from '@/lib/tour/useTour';

const scanned = (billId: number) => {
  render(<CreateBillWizard isOpen onClose={vi.fn()} onSubmit={vi.fn()} existingBills={[]} />);
  act(() => scan.onScanned?.(billId));
};

describe('CreateBillWizard — inviting the table to a scanned bill', () => {
  beforeEach(() => {
    useInvitePrompt.setState({ billId: null });
    useTour.setState({ active: false });
  });

  it('offers to invite the table to the bill the scan made', () => {
    scanned(31);

    expect(useInvitePrompt.getState().billId).toBe(31);
  });

  it('offers nothing during the tour, which shows the invite its own way', () => {
    useTour.setState({ active: true });

    scanned(31);

    expect(useInvitePrompt.getState().billId).toBeNull();
  });
});
