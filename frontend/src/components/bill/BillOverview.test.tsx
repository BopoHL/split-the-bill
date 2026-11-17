import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { billFixture } from '@/test/billFixtures';
import BillOverview from './BillOverview';

vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector: (state: { currentUser: { id: number }; language: string }) => unknown) =>
    selector({ currentUser: { id: 10 }, language: 'en' }),
}));

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    language: 'en',
    t: (key: string, params?: Record<string, string>) =>
      key === 'bill.scanTotalMismatch'
        ? `Receipt mismatch ${params?.amount}`
        : ({
            'bill.items': 'Items',
            'bill.totalBill': 'Total',
            'bill.untitled': 'Untitled',
            'common.close': 'Close',
          })[key] ?? key,
  }),
}));

describe('BillOverview scan mismatch placement', () => {
  it('shows the owner warning below the title but before a long receipt and lets it be dismissed', () => {
    render(
      <BillOverview
        bill={billFixture({ scan_total_mismatch: true, receipt_total_sum: 900 })}
      >
        <div data-testid="receipt-contents">Long receipt contents</div>
      </BillOverview>,
    );

    const warning = screen.getByRole('note');
    const contents = screen.getByTestId('receipt-contents');
    expect(warning).toHaveTextContent('Receipt mismatch');
    expect(warning.compareDocumentPosition(contents) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('note')).toBeNull();
  });

  it('does not show the warning to a non-owner', () => {
    render(
      <BillOverview
        bill={billFixture({ owner_id: 20, scan_total_mismatch: true, receipt_total_sum: 900 })}
      />,
    );

    expect(screen.queryByRole('note')).toBeNull();
  });
});
