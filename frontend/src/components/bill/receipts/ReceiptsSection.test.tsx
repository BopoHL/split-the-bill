import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { BillDetail, Receipt } from '@/types/api';

const replace = vi.fn();
let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  useSearchParams: () => searchParams,
}));

// The scan link opens the sheet, which reaches for a scanner this environment
// has no Telegram client to provide — it says so through a toast.
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));

// The card fetches its photo with the caller's identity; the bytes are not
// what these tests are about.
vi.mock('@/hooks/useAuthenticatedImage', () => ({
  useAuthenticatedImage: (path: string | null) => path,
}));

const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));

vi.mock('@/lib/api/bills', () => ({
  deleteReceipt: vi.fn(),
  getReceiptDeleteImpact: vi
    .fn()
    .mockResolvedValue({ items_count: 5, total: 4200, assigned_count: 2 }),
  receiptImagePath: (b: number, t: number) => `/img/${b}/${t}`,
}));

import { deleteReceipt } from '@/lib/api/bills';
import ReceiptsSection from './ReceiptsSection';

const receipt = (over: Partial<Receipt> = {}): Receipt => ({
  task_id: 1,
  index: 1,
  source: 'photo',
  status: 'completed',
  merchant_name: 'Chaikhana',
  total: 4200,
  items_count: 5,
  quality: null,
  has_photo: true,
  created_at: '2026-08-11T10:00:00Z',
  ...over,
});

const bill = (receipts: Receipt[]): BillDetail =>
  ({ id: 7, status: 'open', receipts, items: [], participants: [] }) as unknown as BillDetail;

describe('ReceiptsSection', () => {
  it('lists every receipt with its own item count', () => {
    render(
      <ReceiptsSection
        bill={bill([receipt(), receipt({ task_id: 2, index: 2, merchant_name: 'Coffee', items_count: 3 })])}
        currentUserId={1}
        isCreator
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
      />,
    );

    expect(screen.getByText('Chaikhana')).toBeInTheDocument();
    expect(screen.getByText('Coffee')).toBeInTheDocument();
    expect(screen.queryByText('Receipts')).toBeNull();
  });

  it('keeps the compact add tile inside the receipt strip', async () => {
    render(
      <ReceiptsSection
        bill={bill([receipt()])}
        currentUserId={1}
        isCreator
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
      />,
    );

    const add = screen.getByRole('button', { name: /add receipt|добавить чек/i });
    expect(add.parentElement).toContainElement(screen.getByText('Chaikhana'));
    expect(add.parentElement).toHaveAttribute('data-sideways-scroller');
    // A vertical drag that starts on a receipt must still scroll the page.
    expect(add.parentElement!.style.touchAction.split(' ')).toEqual(
      expect.arrayContaining(['pan-x', 'pan-y']),
    );
    expect(add).toHaveAttribute('title', add.getAttribute('aria-label'));
    expect(add.className).toContain('h-[86px]');
    expect(add.className).toContain('w-[86px]');
    // A solid outline: a dashed one ran into its own hard shadow.
    expect(add.className).toContain('btn-hard-sm');
    expect(add.className).not.toContain('border-dashed');
    expect(add).toHaveTextContent('');
    expect(add.querySelectorAll('svg')).toHaveLength(2);

    await userEvent.click(add);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('uses the same add tile when the receipt strip is empty', () => {
    render(
      <ReceiptsSection
        bill={bill([])}
        currentUserId={1}
        isCreator
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
      />,
    );

    const add = screen.getByRole('button', { name: /add receipt|добавить чек/i });
    expect(add.parentElement?.children).toHaveLength(1);
    expect(add).toHaveTextContent('');
  });

  it('blocks deletion while a receipt is still being recognised', () => {
    render(
      <ReceiptsSection
        bill={bill([receipt({ status: 'processing' })])}
        currentUserId={1}
        isCreator
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /удалить/i })).toBeDisabled();
  });

  it('asks what should happen to the items before deleting', async () => {
    const onBillUpdate = vi.fn();
    vi.mocked(deleteReceipt).mockResolvedValue(bill([]));

    render(
      <ReceiptsSection
        bill={bill([receipt()])}
        currentUserId={1}
        isCreator
        onBillUpdate={onBillUpdate}
        onReload={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /удалить/i }));
    expect(await screen.findByText(/удалить позиции/i)).toBeInTheDocument();
    // The dialog quotes what the choice costs.
    expect(await screen.findByText(/2 уже назначены/i)).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole('button', { name: /сохранить позиции/i }),
    );
    expect(deleteReceipt).toHaveBeenCalledWith(7, 1, 1, true);
    await waitFor(() => expect(track).toHaveBeenCalledWith('receipt_deleted', { bill_id: 7, kept_items: true }));
  });

  it('hides the add button from participants', () => {
    render(
      <ReceiptsSection
        bill={bill([receipt()])}
        currentUserId={2}
        isCreator={false}
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole('button', { name: /add receipt|добавить чек/i }),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: /удалить/i })).toBeNull();
  });

  it('renders nothing for a participant when the bill has no receipts', () => {
    const { container } = render(
      <ReceiptsSection
        bill={bill([])}
        currentUserId={2}
        isCreator={false}
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ReceiptsSection, arriving from the bot's scan link", () => {
  const renderWith = (params: string, props = {}) => {
    searchParams = new URLSearchParams(params);
    replace.mockClear();
    render(
      <ReceiptsSection
        bill={bill([receipt()])}
        currentUserId={1}
        isCreator
        onBillUpdate={vi.fn()}
        onReload={vi.fn()}
        {...props}
      />,
    );
  };

  it('opens the receipt sheet and spends the flag', () => {
    renderWith('scan=1');

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    // Left in the URL, going back to the bill would reopen the scanner.
    expect(replace).toHaveBeenCalledWith('/bill/7');
  });

  it('stays shut without the flag', () => {
    renderWith('');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it('ignores the flag for someone who cannot add receipts', () => {
    renderWith('scan=1', { isCreator: false });

    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
