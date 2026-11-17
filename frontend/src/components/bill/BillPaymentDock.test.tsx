import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { BillDetail, BillItem, BillParticipant, User } from '@/types/api';
import { BillStatus, SplitType } from '@/types/api';

const { showToastMock, writeTextMock } = vi.hoisted(() => ({
  showToastMock: vi.fn(),
  writeTextMock: vi.fn(),
}));

vi.mock('@/lib/i18n/useTranslation', () => {
  const messages: Record<string, string> = {
    'common.back': 'Back',
    'common.cancel': 'Cancel',
    'common.error': 'Error',
    'common.save': 'Save',
    'bill.addPaymentDetails': 'Add payment details',
    'bill.cancelPaymentConfirm': 'Are you sure you want to cancel the payment?',
    'bill.cancelPaymentTitle': 'Cancel payment?',
    'bill.cancelPaymentYes': 'Yes, cancel',
    'bill.chooseItems': 'Choose items',
    'bill.closeBill': 'Close bill',
    'bill.copyAmount': 'Copy amount',
    'bill.copyCard': 'Copy card',
    'bill.editPaymentDetails': 'Edit payment details',
    'bill.emptyShareHint': 'Choose what you had before marking payment.',
    'bill.iPaidShort': 'I paid',
    'bill.leftToCollect': 'Left to collect',
    'bill.ownShare': 'your share {amount}',
    'bill.noPaymentDetails': 'Payment details have not been added yet.',
    'bill.noPaymentDue': 'No payment due',
    'bill.cancelPayment': 'Undo',
    'bill.paymentCard': 'Payment Card',
    'bill.paymentDetails': 'Payment details',
    'bill.cardNumber': 'Card number',
    'bill.rememberCard': 'Remember for the next bills',
    'bill.paymentMarked': 'Payment marked',
    'bill.reopen': 'Reopen bill',
    'bill.yourShare': 'Your Share',
    'bill.waitingForShare': 'Waiting for your share',
    'home.total': 'total',
  };

  return {
    useTranslation: () => ({
      language: 'en',
      t: (key: string, params?: Record<string, string>) =>
        (messages[key] ?? key).replace(/\{(\w+)\}/g, (_, name: string) => params?.[name] ?? ''),
    }),
  };
});

vi.mock('@/lib/store/useStore', () => {
  const state = {
    language: 'en',
    currentUser: { id: 2 },
    showToast: vi.fn(),
  };
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
  createPaymentMethod: vi.fn().mockImplementation((_userId, value) =>
    Promise.resolve({ id: 1, label: null, ...value }),
  ),
  deletePaymentMethod: vi.fn().mockResolvedValue(undefined),
}));

import BillPaymentDock from './BillPaymentDock';

const currentUser: User = {
  id: 2,
  telegram_id: 22,
  username: 'participant',
  name: 'Pat',
  surname: null,
  avatar_url: null,
};

const participant = (overrides: Partial<BillParticipant> = {}): BillParticipant => ({
  id: 20,
  bill_id: 7,
  user_id: currentUser.id,
  guest_name: null,
  username: currentUser.username,
  name: currentUser.name,
  surname: null,
  avatar_url: null,
  allocated_amount: 500,
  is_paid: false,
  seat_index: 1,
  is_guest: false,
  claimed_at: null,
  ...overrides,
});

const item = (overrides: Partial<BillItem> = {}): BillItem => ({
  id: 70,
  bill_id: 7,
  name: 'Dinner item',
  price: 500,
  count: 1,
  item_sum: 500,
  is_shared_globally: false,
  assigned_participant_ids: [],
  portions: [[]],
  ...overrides,
});

const bill = (overrides: Partial<BillDetail> = {}): BillDetail => ({
  id: 7,
  owner_id: 1,
  total_sum: 1000,
  title: 'Dinner',
  payment_details: '8600 1111 2222 3333',
  participants_count: 2,
  status: BillStatus.OPEN,
  created_at: '2026-09-18T12:00:00Z',
  split_type: SplitType.BY_ITEMS,
  currency: 'usd',
  unallocated_sum: 0,
  public_token: 'token',
  items: [],
  participants: [participant()],
  ...overrides,
});

describe('BillPaymentDock participant states', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    writeTextMock.mockReset().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: writeTextMock },
    });
  });

  it('shows an unpaid share and calls only the self-payment callback', () => {
    const onTogglePaid = vi.fn();
    render(
      <BillPaymentDock
        bill={bill()}
        currentUser={currentUser}
        onTogglePaid={onTogglePaid}
      />,
    );

    expect(screen.getByText('Your Share')).toBeInTheDocument();
    expect(screen.getByText('500 $')).toBeInTheDocument();
    expect(screen.getByText('8600 1111 2222 3333')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'I paid' }));
    expect(onTogglePaid).toHaveBeenCalledTimes(1);
  });

  it('lets the guest tour point at the share with its card, and at «I paid»', () => {
    render(<BillPaymentDock bill={bill()} currentUser={currentUser} onTogglePaid={vi.fn()} />);

    expect(document.querySelector('[data-tour="my-share"]')).toHaveTextContent('8600 1111 2222 3333');
    expect(screen.getByRole('button', { name: 'I paid' })).toHaveAttribute('data-tour', 'i-paid');
  });

  it('copies the card from beside its number, with «I paid» on its own under it', async () => {
    render(<BillPaymentDock bill={bill()} currentUser={currentUser} onTogglePaid={vi.fn()} />);

    const copyCard = screen.getByRole('button', { name: 'Copy card' });
    expect(copyCard.textContent).toBe('');
    expect(copyCard.parentElement).toContainElement(screen.getByText('8600 1111 2222 3333'));
    expect(copyCard.compareDocumentPosition(screen.getByRole('button', { name: 'I paid' })))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    fireEvent.click(copyCard);
    expect(writeTextMock).toHaveBeenCalledWith('8600 1111 2222 3333');
    await waitFor(() => expect(copyCard.querySelector('svg')).toHaveClass('text-success'));
  });

  it('keeps the copy key on the card when there is nothing to pay', () => {
    render(<BillPaymentDock bill={bill({ status: BillStatus.CLOSED })} currentUser={currentUser} onTogglePaid={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Copy card' }).parentElement)
      .toContainElement(screen.getByText('8600 1111 2222 3333'));
  });

  it('confirms before undoing a paid share', () => {
    const onTogglePaid = vi.fn();
    render(
      <BillPaymentDock
        bill={bill({ participants: [participant({ is_paid: true })] })}
        currentUser={currentUser}
        onTogglePaid={onTogglePaid}
      />,
    );

    expect(screen.getByText('Payment marked')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onTogglePaid).not.toHaveBeenCalled();
    expect(screen.getByText('Are you sure you want to cancel the payment?')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Yes, cancel' }));
    expect(onTogglePaid).toHaveBeenCalledTimes(1);
  });

  it('offers item selection for an empty share without a payment action', () => {
    const onSelectItems = vi.fn();
    render(
      <BillPaymentDock
        bill={bill({ participants: [participant({ allocated_amount: 0 })] })}
        currentUser={currentUser}
        onTogglePaid={vi.fn()}
        onSelectItems={onSelectItems}
      />,
    );

    expect(screen.getByText('Choose what you had before marking payment.')).toBeInTheDocument();
    expect(screen.getByText('Choose what you had before marking payment.')).toHaveClass('basis-40');
    expect(screen.queryByRole('button', { name: 'I paid' })).toBeNull();
    const chooseItems = screen.getByRole('button', { name: 'Choose items' });
    expect(chooseItems).toHaveClass('flex-1', 'basis-28');
    expect(chooseItems.parentElement).toHaveClass('flex-wrap');
    fireEvent.click(chooseItems);
    expect(onSelectItems).toHaveBeenCalledTimes(1);
  });

  it.each([0, -12.34])(
    'keeps the amount and card for an assigned share worth %s without a payment action',
    async (allocatedAmount) => {
      render(
        <BillPaymentDock
          bill={bill({
            items: [item({ assigned_participant_ids: [20], portions: [[20]] })],
            participants: [participant({ allocated_amount: allocatedAmount })],
          })}
          currentUser={currentUser}
          onTogglePaid={vi.fn()}
          onSelectItems={vi.fn()}
        />,
      );

      expect(screen.getByText(allocatedAmount === 0 ? '0 $' : '-12.34 $')).toBeInTheDocument();
      expect(screen.getByText('8600 1111 2222 3333')).toBeInTheDocument();
      expect(screen.getByText('No payment due')).toBeInTheDocument();
      expect(screen.queryByText('Choose what you had before marking payment.')).toBeNull();
      expect(screen.queryByRole('button', { name: 'Choose items' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'I paid' })).toBeNull();

      if (allocatedAmount < 0) {
        fireEvent.click(screen.getByRole('button', { name: 'Copy amount' }));
        await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith('-12.34'));
      }
    },
  );

  it('offers item selection on a bill with dishes nobody has split yet', () => {
    render(
      <BillPaymentDock
        bill={bill({
          split_type: SplitType.MANUAL,
          items: [item()],
          participants: [participant({ allocated_amount: 0 }), participant({ id: 10, user_id: 1, allocated_amount: 0 })],
        })}
        currentUser={currentUser}
        onTogglePaid={vi.fn()}
        onSelectItems={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Choose items' })).toBeEnabled();
    expect(screen.queryByText('Waiting for your share')).toBeNull();
  });

  it.each([SplitType.MANUAL])(
    'waits for a %s zero share without offering item selection',
    (splitType) => {
      render(
        <BillPaymentDock
          bill={bill({
            split_type: splitType,
            items: [item()],
            participants: [participant({ allocated_amount: 0 }), participant({ id: 10, user_id: 1, allocated_amount: 1000 })],
          })}
          currentUser={currentUser}
          onTogglePaid={vi.fn()}
          onSelectItems={vi.fn()}
        />,
      );

      expect(screen.getByText('Waiting for your share')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Choose items' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'I paid' })).toBeNull();
    },
  );

  it('wraps a large amount instead of truncating it', () => {
    render(
      <BillPaymentDock
        bill={bill({
          total_sum: 9_999_999_999,
          participants: [participant({ allocated_amount: 9_999_999_999 })],
        })}
        currentUser={currentUser}
        onTogglePaid={vi.fn()}
      />,
    );

    const amount = screen.getByText('9 999 999 999 $');
    expect(amount).toHaveClass('whitespace-normal', 'break-words');
    expect(amount).not.toHaveClass('truncate');
  });

  it('keeps a closed bill read-only while retaining the amount and card', () => {
    render(
      <BillPaymentDock
        bill={bill({ status: BillStatus.CLOSED })}
        currentUser={currentUser}
        onTogglePaid={vi.fn()}
      />,
    );

    expect(screen.getByText('500 $')).toBeInTheDocument();
    expect(screen.getByText('8600 1111 2222 3333')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'I paid' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
  });

  it('copies the numeric amount and only shows success after the write resolves', async () => {
    render(<BillPaymentDock bill={bill()} currentUser={currentUser} onTogglePaid={vi.fn()} />);
    const copy = screen.getByRole('button', { name: 'Copy amount' });

    fireEvent.click(copy);
    await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith('500'));
    await waitFor(() => expect(copy.querySelector('svg')).toHaveClass('text-success'));
    expect(showToastMock).not.toHaveBeenCalled();
  });

  it('copies a floating input as an exact minor-unit amount', async () => {
    render(
      <BillPaymentDock
        bill={bill({
          participants: [participant({ allocated_amount: 0.1 + 0.2 })],
        })}
        currentUser={currentUser}
        onTogglePaid={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Copy amount' }));
    await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith('0.3'));
  });

  it('reports a clipboard error without showing the copied state', async () => {
    writeTextMock.mockRejectedValueOnce(new Error('denied'));
    render(<BillPaymentDock bill={bill()} currentUser={currentUser} onTogglePaid={vi.fn()} />);
    const copy = screen.getByRole('button', { name: 'Copy amount' });

    fireEvent.click(copy);
    await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('Error'));
    expect(copy.querySelector('svg')).not.toHaveClass('text-success');
  });
});

describe('BillPaymentDock creator states', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    writeTextMock.mockReset().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: writeTextMock },
    });
  });

  it('shows what is left to collect, edits a missing card in a modal, and closes', async () => {
    const onCloseBill = vi.fn();
    const onUpdatePaymentDetails = vi.fn().mockResolvedValue(undefined);
    const paid = participant({ id: 21, user_id: 3, allocated_amount: 300, is_paid: true });
    render(
      <BillPaymentDock
        bill={bill({ payment_details: null, participants: [paid], left_to_collect: 700 })}
        currentUser={{ ...currentUser, id: 1 }}
        isCreator
        onCloseBill={onCloseBill}
        onUpdatePaymentDetails={onUpdatePaymentDetails}
      />,
    );

    expect(screen.getByText('Left to collect')).toBeInTheDocument();
    expect(screen.getByText('700 $')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close bill' }));
    expect(onCloseBill).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole('button', { name: 'Add payment details' }));
    expect(screen.getByRole('dialog', { name: 'Payment Card' })).toBeInTheDocument();
    await userEvent.type(screen.getByRole('textbox', { name: 'Card number' }), '8600123456789012');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onUpdatePaymentDetails).toHaveBeenCalledWith('8600 1234 5678 9012'));
  });

  it('gives the dock over to what the screen needs it for instead', () => {
    render(
      <BillPaymentDock
        bill={bill()}
        currentUser={{ ...currentUser, id: 1 }}
        isCreator
        onCloseBill={vi.fn()}
        takeover={<p>Picking dishes</p>}
      />,
    );

    expect(screen.getByTestId('bill-payment-dock')).toHaveTextContent('Picking dishes');
    expect(screen.queryByText('Left to collect')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Close bill' })).not.toBeInTheDocument();
  });

  it('shows the total, not «0 left», while nobody has taken a dish yet', () => {
    render(
      <BillPaymentDock
        bill={bill({ total_sum: 300, unallocated_sum: 300, left_to_collect: 0, participants: [participant({ id: 10, user_id: 1, allocated_amount: 0 })] })}
        currentUser={{ ...currentUser, id: 1 }}
        isCreator
        onCloseBill={vi.fn()}
      />,
    );

    expect(screen.getByText('total')).toBeInTheDocument();
    expect(screen.getByText('300 $')).toBeInTheDocument();
    expect(screen.queryByText('Left to collect')).not.toBeInTheDocument();
  });

  it('shows the owner what the others still owe, as the server counts it, and their own share apart', () => {
    const owner = participant({
      id: 10,
      user_id: 1,
      allocated_amount: 200,
      is_paid: false,
    });
    const paidOther = participant({
      id: 21,
      user_id: 3,
      allocated_amount: 300,
      is_paid: true,
    });
    const unpaidOther = participant({
      id: 22,
      user_id: 4,
      allocated_amount: 400,
      is_paid: false,
    });

    render(
      <BillPaymentDock
        bill={bill({
          total_sum: 1700,
          unallocated_sum: 800,
          left_to_collect: 400,
          participants: [owner, paidOther, unpaidOther],
        })}
        currentUser={{ ...currentUser, id: 1 }}
        isCreator
        onCloseBill={vi.fn()}
      />,
    );

    expect(screen.getByText('400 $')).toBeInTheDocument();
    expect(screen.getByText('your share 200 $')).toBeInTheDocument();
  });

  it('reopens a closed owner bill and does not offer card editing', () => {
    const onReopenBill = vi.fn();
    render(
      <BillPaymentDock
        bill={bill({ status: BillStatus.CLOSED })}
        currentUser={{ ...currentUser, id: 1 }}
        isCreator
        onUpdatePaymentDetails={vi.fn()}
        onReopenBill={onReopenBill}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Edit payment details' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Reopen bill' }));
    expect(onReopenBill).toHaveBeenCalledTimes(1);
  });

  it('mounts without ResizeObserver and reserves the measured dock height', async () => {
    const originalObserver = globalThis.ResizeObserver;
    Reflect.deleteProperty(globalThis, 'ResizeObserver');
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 640,
      height: 144,
      top: 0,
      right: 640,
      bottom: 144,
      left: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    try {
      render(
        <BillPaymentDock
          bill={bill()}
          currentUser={{ ...currentUser, id: 1 }}
          isCreator
          onCloseBill={vi.fn()}
        />,
      );
      await waitFor(() =>
        expect(screen.getByTestId('bill-payment-dock-spacer')).toHaveStyle({ height: '144px' }),
      );
      expect(screen.getByTestId('bill-payment-dock')).toHaveClass('fixed', 'bottom-0');
      expect(screen.getByTestId('bill-payment-dock')).toHaveClass('overflow-x-clip');
      const content = screen.getByTestId('bill-payment-dock').firstElementChild;
      expect(content).toHaveClass('max-w-2xl', 'min-w-0');
      expect(content?.className).toContain('max(1.25rem,var(--content-safe-bottom))');
      expect(content?.className).toContain('var(--content-safe-left)');
      expect(content?.className).toContain('var(--content-safe-right)');
    } finally {
      rect.mockRestore();
      if (originalObserver) globalThis.ResizeObserver = originalObserver;
    }
  });

  it('gets out of the way while a text field owns the native keyboard', async () => {
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 640, height: 144, top: 0, right: 640, bottom: 144, left: 0, x: 0, y: 0, toJSON: () => ({}),
    });
    render(
      <>
        <input aria-label="Guest name" />
        <BillPaymentDock
          bill={bill()}
          currentUser={{ ...currentUser, id: 1 }}
          isCreator
          onCloseBill={vi.fn()}
        />
      </>,
    );

    const dock = screen.getByTestId('bill-payment-dock');
    const spacer = screen.getByTestId('bill-payment-dock-spacer');
    fireEvent.focusIn(screen.getByLabelText('Guest name'));

    await waitFor(() => expect(dock).toHaveAttribute('data-keyboard-hidden', 'true'));
    expect(dock).toHaveAttribute('aria-hidden', 'true');
    expect(dock).toHaveStyle({ opacity: '0', pointerEvents: 'none' });
    // The page must not change height under the finger: a tap on a confirm
    // button blurs the field first, and a growing spacer would scroll the
    // button away before the tap lands.
    expect(spacer).toHaveStyle({ height: '144px' });

    fireEvent.focusOut(screen.getByLabelText('Guest name'), { relatedTarget: null });
    await waitFor(() => expect(dock).toHaveAttribute('data-keyboard-hidden', 'false'));
    expect(dock).not.toHaveAttribute('aria-hidden');
    expect(spacer).toHaveStyle({ height: '144px' });
    rect.mockRestore();
  });

  it('also hides for visual-viewport keyboard occlusion and removes its listeners', async () => {
    const originalViewport = Object.getOwnPropertyDescriptor(window, 'visualViewport');
    const resize = new Set<EventListener>();
    const scroll = new Set<EventListener>();
    const viewport = {
      height: 800,
      offsetTop: 0,
      addEventListener: vi.fn((type: string, listener: EventListener) => {
        (type === 'resize' ? resize : scroll).add(listener);
      }),
      removeEventListener: vi.fn((type: string, listener: EventListener) => {
        (type === 'resize' ? resize : scroll).delete(listener);
      }),
    };
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: viewport,
    });
    const innerHeight = window.innerHeight;
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });

    try {
      const { unmount } = render(
        <BillPaymentDock
          bill={bill()}
          currentUser={{ ...currentUser, id: 1 }}
          isCreator
          onCloseBill={vi.fn()}
        />,
      );
      const dock = screen.getByTestId('bill-payment-dock');
      viewport.height = 600;
      act(() => resize.forEach((listener) => listener(new Event('resize'))));
      await waitFor(() => expect(dock).toHaveAttribute('data-keyboard-hidden', 'true'));

      unmount();
      expect(viewport.removeEventListener).toHaveBeenCalledWith('resize', expect.any(Function));
      expect(viewport.removeEventListener).toHaveBeenCalledWith('scroll', expect.any(Function));
    } finally {
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: innerHeight });
      if (originalViewport) Object.defineProperty(window, 'visualViewport', originalViewport);
      else Reflect.deleteProperty(window, 'visualViewport');
    }
  });
});
