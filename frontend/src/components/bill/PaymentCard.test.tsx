import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { BillDetail } from '@/types/api';
import { BillStatus, SplitType } from '@/types/api';

const { showToastMock, fit } = vi.hoisted(() => ({ showToastMock: vi.fn(), fit: { clipped: false } }));

// jsdom lays nothing out, so how the details fit their line is set here.
vi.mock('@/hooks/useFittedFontSize', () => ({
  useFittedFontSize: () => ({ boxRef: { current: null }, textRef: { current: null }, size: 20, clipped: fit.clipped }),
}));

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    language: 'en',
    t: (key: string) =>
      ({
        'common.error': 'Error',
        'bill.copyCard': 'Copy card',
        'bill.editPaymentDetails': 'Edit payment details',
        'bill.paymentDetails': 'Payment details',
        'bill.noPaymentDetails': 'Payment details have not been added yet.',
        'bill.paymentCard': 'Payment Card',
        'bill.paymentDetailsInput': 'Card number or details',
        'common.save': 'Save',
        'bill.showPaymentDetails': 'Show in full',
        'bill.addPaymentDetails': 'Add payment details',
        'bill.cardNumber': 'Card number',
        'bill.otherCard': 'Another card',
        'bill.yourCards': 'Your cards',
        'bill.rememberCard': 'Remember for the next bills',
        'bill.removeFromBill': 'Remove from the bill',
      })[key] ?? key,
  }),
}));

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 1 } };
  const useStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});

vi.mock('@/lib/toast', () => ({
  showToast: (...args: unknown[]) => showToastMock(...args),
}));

vi.mock('@/lib/analytics', () => ({
  AnalyticsEvent: { PayDetailsCopied: 'pay_details_copied' },
  track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(),
}));

vi.mock('@/lib/api/paymentMethods', () => ({
  listPaymentMethods: vi.fn().mockResolvedValue([]),
  createPaymentMethod: vi.fn(),
  deletePaymentMethod: vi.fn(),
}));

import { createPaymentMethod, listPaymentMethods } from '@/lib/api/paymentMethods';
import PaymentCard from './PaymentCard';

const bill = (overrides: Partial<BillDetail> = {}): BillDetail => ({
  id: 7,
  owner_id: 1,
  total_sum: 1000,
  title: 'Dinner',
  payment_details: '8600 1111 2222 3333',
  participants_count: 1,
  status: BillStatus.OPEN,
  created_at: '2026-09-18T12:00:00Z',
  split_type: SplitType.BY_ITEMS,
  currency: 'usd',
  unallocated_sum: 0,
  public_token: 'token',
  items: [],
  participants: [],
  ...overrides,
});

describe('PaymentCard compact mode', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    fit.clipped = false;
  });

  it('shows details cut off on their line in full, and only then', async () => {
    const details = 'Humo 9860 1234 5678 9012, Ivanov Ivan';
    const { unmount } = render(<PaymentCard bill={bill({ payment_details: details })} compact />);
    expect(screen.queryByRole('button', { name: 'Show in full' })).toBeNull();
    unmount();

    fit.clipped = true;
    render(<PaymentCard bill={bill({ payment_details: details })} compact />);
    fireEvent.click(screen.getByRole('button', { name: 'Show in full' }));

    const dialog = await screen.findByRole('dialog', { name: 'Payment Card' });
    expect(dialog).toHaveTextContent(details);
    expect(within(dialog).getByRole('button', { name: 'Copy card' })).toBeInTheDocument();
  });

  it('falls back to the document copy command when Clipboard API is unavailable', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    });
    render(<PaymentCard bill={bill()} compact />);

    fireEvent.click(screen.getByRole('button', { name: 'Copy card' }));
    expect(execCommand).toHaveBeenCalledWith('copy');
    // The copy settles a turn later; the key shows it with a check mark.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Copy card' }).querySelector('svg')).toHaveClass('text-success'),
    );
    expect(showToastMock).not.toHaveBeenCalled();
  });

  it('shows an informative read-only state when payment details are missing', () => {
    render(<PaymentCard bill={bill({ payment_details: null })} compact />);
    expect(screen.getByText('Payment details have not been added yet.')).toBeInTheDocument();
  });

  it('opens editing on the saved cards, with the bill’s own card in the field', async () => {
    vi.mocked(listPaymentMethods).mockResolvedValueOnce([{ id: 3, label: null, value: '9860 0000 1111 2222' }]);
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(<PaymentCard bill={bill()} compact onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit payment details' }));
    await screen.findByRole('dialog', { name: 'Payment Card' });
    const saved = await screen.findByRole('radio', { name: /9860 0000 1111 2222/ });

    // The bill's card is not a saved one, so it waits in «Another card».
    expect(screen.getByRole('radio', { name: 'Another card' })).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Card number' })).toHaveValue('8600 1111 2222 3333');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    fireEvent.click(saved);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('9860 0000 1111 2222'));
  });

  it('puts a typed card on the bill and keeps it for next time', async () => {
    vi.mocked(createPaymentMethod).mockResolvedValueOnce({ id: 4, label: null, value: '5614 6812' });
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(<PaymentCard bill={bill({ payment_details: null })} compact onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole('button', { name: 'Add payment details' }));
    fireEvent.change(await screen.findByRole('textbox', { name: 'Card number' }), { target: { value: '5614681200001234' } });
    expect(screen.queryByRole('button', { name: 'Remove from the bill' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('5614 6812 0000 1234'));
    expect(createPaymentMethod).toHaveBeenCalledWith(1, { value: '5614 6812 0000 1234' });
  });

  it('saves a typed card before it goes on the bill, so the bill finds it saved', async () => {
    let saved!: (method: { id: number; label: null; value: string }) => void;
    vi.mocked(createPaymentMethod).mockReturnValueOnce(new Promise((resolve) => { saved = resolve; }));
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(<PaymentCard bill={bill({ payment_details: null })} compact onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole('button', { name: 'Add payment details' }));
    fireEvent.change(await screen.findByRole('textbox', { name: 'Card number' }), { target: { value: '5614681200001234' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(createPaymentMethod).toHaveBeenCalled());
    expect(onUpdate).not.toHaveBeenCalled();
    saved({ id: 4, label: null, value: '5614 6812 0000 1234' });
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('5614 6812 0000 1234'));
  });

  it('shows no field until the saved cards are in', async () => {
    let listed!: (methods: { id: number; label: null; value: string }[]) => void;
    vi.mocked(listPaymentMethods).mockReturnValueOnce(new Promise((resolve) => { listed = resolve; }));
    render(<PaymentCard bill={bill()} compact onUpdate={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit payment details' }));
    await screen.findByRole('dialog', { name: 'Payment Card' });
    expect(screen.queryByRole('textbox', { name: 'Card number' })).toBeNull();

    listed([{ id: 3, label: null, value: '8600 1111 2222 3333' }]);
    expect(await screen.findByRole('radio', { name: /8600 1111 2222 3333/ })).toBeChecked();
    expect(screen.queryByRole('textbox', { name: 'Card number' })).toBeNull();
  });

  it('has a cross on every saved card, with no mode to switch into', async () => {
    vi.mocked(listPaymentMethods).mockResolvedValueOnce([
      { id: 3, label: null, value: '9860 0000 1111 2222' },
      { id: 5, label: null, value: '4169 5858 0000 1111' },
    ]);
    render(<PaymentCard bill={bill()} compact onUpdate={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit payment details' }));
    await screen.findByRole('radio', { name: /9860 0000 1111 2222/ });

    expect(screen.getAllByRole('button', { name: /common\.delete/ })).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'bill.editCards' })).toBeNull();
  });

  it('takes the card off the bill', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(<PaymentCard bill={bill()} compact onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit payment details' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Remove from the bill' }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(''));
  });
});
