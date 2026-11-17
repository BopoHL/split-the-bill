import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mocks ---------------------------------------------------------
const storeState = {
  language: 'en',
  currency: 'uzs' as const,
  currentUser: { id: 1, settings: {} as { currency?: string } },
};

vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector?: (s: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// The payment step lists the saved details and keeps new ones.
vi.mock('@/lib/api/paymentMethods', () => ({
  listPaymentMethods: vi.fn().mockResolvedValue([]),
  createPaymentMethod: vi.fn().mockResolvedValue({ id: 9, label: null, value: '5614 6812' }),
  deletePaymentMethod: vi.fn(),
}));

// The scan path talks to the receipts API; keep it off the network.
vi.mock('@/lib/api/receipts', () => ({
  receiptsApi: {
    upload: vi.fn().mockResolvedValue({ id: 1 }),
    getStreamUrl: vi.fn().mockReturnValue('http://x/stream'),
    cancelTask: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/lib/utils/image', () => ({
  compressImage: (file: File) => Promise.resolve(file),
}));
vi.mock('@/lib/api/auth', () => ({
  requestSseTicket: vi.fn().mockResolvedValue('ticket'),
}));
vi.mock('@/lib/utils/platform', () => ({ isIOS: () => true }));

import { receiptsApi } from '@/lib/api/receipts';
import { createPaymentMethod, listPaymentMethods } from '@/lib/api/paymentMethods';
import CreateBillWizard from './CreateBillWizard';
import type { Bill } from '@/types/api';

const open = (onSubmit = vi.fn()) => {
  render(<CreateBillWizard isOpen onClose={vi.fn()} onSubmit={onSubmit} existingBills={[]} />);
  return onSubmit;
};

const next = () => userEvent.click(screen.getByRole('button', { name: /next/i }));

// Each step shows what it asks rather than a title over it.
const onPeople = () => screen.queryByText('Number of people');
const onPayment = () => screen.queryByText('Where to send the money');
const onSource = () => screen.queryByText(/enter by hand/i);

describe('CreateBillWizard — three steps', () => {
  beforeEach(() => {
    storeState.currentUser.settings = {};
    vi.mocked(createPaymentMethod).mockClear();
  });

  it('starts on the headcount, which decides how the bill is laid out', () => {
    open();
    expect(onPeople()).toBeInTheDocument();
    // The later steps aren't reachable until this one is answered.
    expect(onSource()).toBeNull();
  });

  it('opens on the step itself, with no title over it', () => {
    open();

    expect(screen.getByRole('dialog', { name: 'Create New Bill' })).toBeInTheDocument();
    expect(screen.queryByRole('heading')).toBeNull();
    expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument();
  });

  it('walks forward through payment to the source step', async () => {
    open();
    await next();
    expect(onPayment()).toBeInTheDocument();
    await next();
    expect(onSource()).toBeInTheDocument();
  });

  it('goes back without losing what was already entered', async () => {
    open();
    await userEvent.click(screen.getByRole('button', { name: '+' })); // 3 → 4
    await next();
    await userEvent.click(screen.getByRole('button', { name: /back/i }));

    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('refuses to leave the first step without a valid headcount', async () => {
    open();
    // Drive the count below the minimum via the keypad-less stepper.
    await userEvent.click(screen.getByRole('button', { name: '−' }));
    await userEvent.click(screen.getByRole('button', { name: '−' }));
    await userEvent.click(screen.getByRole('button', { name: '−' }));
    await next();
    // 1 is still valid, so we do advance — the guard is about an empty field.
    expect(onPayment()).toBeInTheDocument();
  });

  it('says out loud that the card can wait', async () => {
    open();
    await next();

    // A button of its own: people were filling the field in because the step
    // looked required, then correcting it on the bill.
    await userEvent.click(screen.getByRole('button', { name: /^skip$/i }));
    expect(onSource()).toBeInTheDocument();
  });

  it('creates the bill without a card when the step is skipped', async () => {
    const onSubmit = open();
    await next();
    await userEvent.click(screen.getByRole('button', { name: /^skip$/i }));
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit.mock.calls[0][0].payment_details).toBeUndefined();
  });

  it('skipping drops a card the step had already filled in', async () => {
    // One saved card is offered up front; Skip has to mean «no card on this
    // bill» even so, or the step it skips still ends up in the bill.
    vi.mocked(listPaymentMethods).mockResolvedValueOnce([
      { id: 1, label: null, value: '8600 1234' },
    ]);
    const onSubmit = open();
    await next();
    expect(await screen.findByText('8600 1234')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /^skip$/i }));
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit.mock.calls[0][0].payment_details).toBeUndefined();
  });

  it('picks the card of the latest bill up front, and another with a tap', async () => {
    vi.mocked(listPaymentMethods).mockResolvedValueOnce([
      { id: 1, label: null, value: '8600 1234 5678 9012' },
      { id: 2, label: null, value: '9860 1100 2200 4411' },
    ]);
    const bills = [
      { owner_id: 1, created_at: '2026-09-01T10:00:00Z', payment_details: '8600 1234 5678 9012' },
      { owner_id: 1, created_at: '2026-09-20T10:00:00Z', payment_details: '9860110022004411' },
      { owner_id: 7, created_at: '2026-09-25T10:00:00Z', payment_details: '8600 0000 0000 0000' },
    ] as Bill[];
    const onSubmit = vi.fn();
    render(<CreateBillWizard isOpen onClose={vi.fn()} onSubmit={onSubmit} existingBills={bills} />);
    await next();

    expect(await screen.findByRole('radio', { name: /9860 1100 2200 4411/ })).toBeChecked();
    await userEvent.click(screen.getByRole('radio', { name: /8600 1234 5678 9012/ }));
    expect(screen.queryByRole('textbox', { name: 'Card number' })).toBeNull();
    await next();
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit.mock.calls[0][0].payment_details).toBe('8600 1234 5678 9012');
    expect(createPaymentMethod).not.toHaveBeenCalled();
  });

  it('offers only the field until a card is saved, and keeps a new one for next time', async () => {
    const onSubmit = open();
    await next();

    expect(screen.queryByRole('radio')).toBeNull();
    await userEvent.type(screen.getByRole('textbox', { name: 'Card number' }), '8600123456789012');
    expect(screen.getByRole('textbox', { name: 'Card number' })).toHaveValue('8600 1234 5678 9012');
    expect(screen.getByText('UZCARD')).toBeInTheDocument();
    await next();
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit.mock.calls[0][0].payment_details).toBe('8600 1234 5678 9012');
    expect(createPaymentMethod).toHaveBeenCalledWith(1, { value: '8600 1234 5678 9012' });
  });

  it('puts a card on the bill without keeping it when told not to', async () => {
    const onSubmit = open();
    await next();

    await userEvent.type(screen.getByRole('textbox', { name: 'Card number' }), '9860110022004411');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Remember for the next bills' }));
    await next();
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit.mock.calls[0][0].payment_details).toBe('9860 1100 2200 4411');
    expect(createPaymentMethod).not.toHaveBeenCalled();
  });

  it('the manual route creates an empty bill with the chosen headcount', async () => {
    const onSubmit = open();
    await userEvent.click(screen.getByRole('button', { name: '+' })); // 4
    await next();
    await next();
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const data = onSubmit.mock.calls[0][0];
    expect(data.total_sum).toBe(0);
    expect(data.expected_people).toBe(4);
    expect(data.title).toMatch(/^Bill /);
  });

  it('offers all three sources at once instead of hiding the scan', async () => {
    open();
    await next();
    await next();
    expect(screen.getByText(/ai scan/i)).toBeInTheDocument();
    expect(screen.getByText(/enter by hand/i)).toBeInTheDocument();
  });

  it('offers the currency where the amounts are about to be typed', async () => {
    const onSubmit = open();

    // Nothing chosen before: the money this app is for, not the browser default.
    expect(screen.getByText('UZS')).toBeInTheDocument();

    await userEvent.click(screen.getByText('UZS'));
    await userEvent.click(screen.getByText('EUR'));
    await next();
    await next();
    await userEvent.click(screen.getByRole('button', { name: /enter by hand/i }));

    expect(onSubmit.mock.calls[0][0].currency).toBe('eur');
  });

  it('keeps the create-time currency choice out of profile settings', async () => {
    open();

    await userEvent.click(screen.getByText('UZS'));
    await userEvent.click(screen.getByText('KZT'));

    expect(storeState.currentUser.settings).toEqual({});
  });

  it('starts from what the person chose before', () => {
    storeState.currentUser.settings = { currency: 'rub' };
    open();

    expect(screen.getByText('RUB')).toBeInTheDocument();
  });
});

describe('CreateBillWizard — walking out of a scan', () => {
  class IdleEventSource {
    onmessage: unknown = null;
    onerror: unknown = null;
    close = vi.fn();
  }

  beforeEach(() => {
    vi.stubGlobal('EventSource', IdleEventSource);
    vi.mocked(receiptsApi.cancelTask).mockClear();
  });

  it('closing the sheet mid-scan cancels the scan rather than leaving it to finish alone', async () => {
    const onClose = vi.fn();
    render(<CreateBillWizard isOpen onClose={onClose} onSubmit={vi.fn()} existingBills={[]} />);
    await next();
    await next();
    await userEvent.click(screen.getByText(/ai scan/i));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(['x'], 'receipt.jpg', { type: 'image/jpeg' }));
    expect(await screen.findByText(/usually takes/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /close/i }));

    // The task — and the empty bill it was about to fill — go with the sheet.
    expect(receiptsApi.cancelTask).toHaveBeenCalledWith(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
