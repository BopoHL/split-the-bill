import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { BillDetail, BillItem, BillParticipant, User } from '@/types/api';
import { BillStatus, SplitType } from '@/types/api';

const {
  claimSeatMock,
  deleteBillParticipantMock,
  dockState,
  getBillMock,
  routerPushMock,
  showToastMock,
  updatePaymentStatusMock,
} = vi.hoisted(() => ({
  claimSeatMock: vi.fn(),
  deleteBillParticipantMock: vi.fn(),
  dockState: {
    loading: false,
    onSelectItems: undefined as (() => void) | undefined,
    onTogglePaid: undefined as (() => void) | undefined,
  },
  getBillMock: vi.fn(),
  routerPushMock: vi.fn(),
  showToastMock: vi.fn(),
  updatePaymentStatusMock: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPushMock }),
}));

vi.mock('@/lib/api/bills', () => ({
  claimSeat: (...args: unknown[]) => claimSeatMock(...args),
  deleteBillParticipant: (...args: unknown[]) => deleteBillParticipantMock(...args),
  getBill: (...args: unknown[]) => getBillMock(...args),
  updatePaymentStatus: (...args: unknown[]) => updatePaymentStatusMock(...args),
}));

vi.mock('@/lib/i18n/useTranslation', () => {
  const messages: Record<string, string> = {
    'bill.detailsTabs': 'Bill details',
    'bill.joinBill': 'Join bill',
    'bill.leaveBill': 'Leave bill',
    'bill.leaveBillConfirm': 'Leave this bill?',
    'bill.notParticipant': 'Not a participant',
    'bill.participants': 'Participants',
    'bill.receipt': 'Receipt',
    'common.cancel': 'Cancel',
  };
  return {
    useTranslation: () => ({
      t: (key: string) => messages[key] ?? key,
      language: 'en',
    }),
  };
});

vi.mock('@/lib/toast', () => ({
  showToast: (...args: unknown[]) => showToastMock(...args),
}));

vi.mock('@/lib/utils/apiError', () => ({
  translateApiError: (detail?: string) => detail ?? 'Error',
}));

vi.mock('./BillOverview', () => ({
  default: ({ children }: { children: import('react').ReactNode }) => (
    <div data-testid="bill-overview">{children}</div>
  ),
}));

vi.mock('./receipts/ReceiptsSection', () => ({
  default: () => <div data-testid="receipts-section" />,
}));

vi.mock('./ItemsSection', () => ({
  default: (props: {
    currentUserId: number;
    isCreator: boolean;
    isClosed: boolean;
    ownerId: number;
    requiresRecalculation: boolean;
  }) => (
    <div
      data-testid="items-section"
      data-current-user={props.currentUserId}
      data-is-creator={String(props.isCreator)}
      data-is-closed={String(props.isClosed)}
      data-owner-id={props.ownerId}
      data-requires-recalculation={String(props.requiresRecalculation)}
    />
  ),
}));

vi.mock('./ParticipantCard', () => ({
  default: (props: {
    participant: BillParticipant;
    defaultExpanded?: boolean;
    onPickItems?: () => void;
    onTakeSeat?: () => void;
  }) => (
    <article
      data-testid={`participant-card-${props.participant.id}`}
      data-default-expanded={String(Boolean(props.defaultExpanded))}
    >
      card-{props.participant.id}
      {props.onPickItems && (
        <button type="button" onClick={props.onPickItems}>
          pick-{props.participant.id}
        </button>
      )}
      {props.onTakeSeat && (
        <button type="button" onClick={props.onTakeSeat}>
          move-{props.participant.id}
        </button>
      )}
    </article>
  ),
}));

vi.mock('./ParticipantItemsDialog', () => ({
  default: (props: { participant: BillParticipant; currentUserId: number; onClose: () => void }) => (
    <div role="dialog" aria-label={`Pick items for ${props.participant.id} as ${props.currentUserId}`}>
      <button type="button" onClick={props.onClose}>Close picker</button>
    </div>
  ),
}));

vi.mock('./invite/InviteRow', () => ({
  default: () => <div data-testid="invite-row" />,
}));

vi.mock('./BillPaymentDock', () => ({
  default: (props: {
    loading?: boolean;
    onSelectItems?: () => void;
    onTogglePaid?: () => void;
  }) => {
    dockState.loading = !!props.loading;
    dockState.onSelectItems = props.onSelectItems;
    dockState.onTogglePaid = props.onTogglePaid;
    return <div data-testid="payment-dock" data-loading={String(!!props.loading)} />;
  },
}));

vi.mock('./MoveSeatDialog', () => ({
  default: (props: { isOpen: boolean; onCancel: () => void; onConfirm: () => void }) =>
    props.isOpen ? (
      <div role="dialog" aria-label="Move seat">
        <button type="button" onClick={props.onConfirm}>Confirm move</button>
        <button type="button" onClick={props.onCancel}>Cancel move</button>
      </div>
    ) : null,
}));

vi.mock('@/components/ui/Modal', () => ({
  default: (props: {
    isOpen: boolean;
    title?: string;
    children: import('react').ReactNode;
  }) =>
    props.isOpen ? (
      <div role="dialog" aria-label={props.title}>{props.children}</div>
    ) : null,
}));

vi.mock('@/components/ui/Button', () => ({
  default: (props: import('react').ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props} />
  ),
}));

import BillDetailsParticipant from './BillDetailsParticipant';

const currentUser: User = {
  id: 2,
  telegram_id: 22,
  username: 'me',
  name: 'Me',
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

const owner = participant({
  id: 10,
  user_id: 1,
  username: 'owner',
  name: 'Owner',
  seat_index: 0,
});

const guest = participant({
  id: 30,
  user_id: null,
  username: null,
  name: null,
  guest_name: 'Guest',
  seat_index: 2,
  is_guest: true,
});

const bill = (overrides: Partial<BillDetail> = {}): BillDetail => ({
  id: 7,
  owner_id: owner.user_id!,
  total_sum: 1500,
  title: 'Dinner',
  payment_details: '8600 1111 2222 3333',
  participants_count: 3,
  expected_people: 4,
  status: BillStatus.OPEN,
  created_at: '2026-09-18T12:00:00Z',
  split_type: SplitType.BY_ITEMS,
  currency: 'usd',
  unallocated_sum: 0,
  public_token: 'token',
  items: [],
  participants: [owner, participant(), guest],
  ...overrides,
});

const item = (overrides: Partial<BillItem> = {}): BillItem => ({
  id: 100,
  bill_id: 7,
  name: 'Plov',
  price: 100,
  count: 2,
  item_sum: 200,
  is_shared_globally: false,
  assigned_participant_ids: [guest.id],
  portions: [[guest.id], [guest.id, participant().id]],
  ...overrides,
});

describe('BillDetailsParticipant redesign integration', () => {
  beforeEach(() => {
    claimSeatMock.mockReset();
    deleteBillParticipantMock.mockReset().mockResolvedValue(undefined);
    getBillMock.mockReset();
    routerPushMock.mockReset();
    showToastMock.mockReset();
    updatePaymentStatusMock.mockReset();
    dockState.loading = false;
    dockState.onSelectItems = undefined;
    dockState.onTogglePaid = undefined;
  });

  it('lists the own seat first and opened, with the invite above the list', () => {
    render(
      <BillDetailsParticipant bill={bill()} currentUser={currentUser} setBill={vi.fn()} />,
    );

    const cards = screen.getAllByTestId(/^participant-card-/);
    expect(cards.map((card) => card.dataset.testid)).toEqual([
      'participant-card-20',
      'participant-card-10',
      'participant-card-30',
    ]);
    expect(cards.map((card) => card.dataset.defaultExpanded)).toEqual(['true', 'false', 'false']);
    expect(screen.getByTestId('invite-row')).toBeVisible();
    expect(screen.getByTestId('invite-row').compareDocumentPosition(cards[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId('items-section').closest('[role="tabpanel"]')).toHaveAttribute('aria-hidden', 'true');
  });

  it('opens the item sheet for the viewer’s own seat from their row', async () => {
    render(
      <BillDetailsParticipant
        bill={bill({ items: [item()] })}
        currentUser={currentUser}
        setBill={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'pick-10' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'pick-20' }));
    expect(screen.getByRole('dialog', { name: 'Pick items for 20 as 2' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Participants' })).toHaveAttribute('aria-selected', 'true');

    await userEvent.click(screen.getByRole('button', { name: 'Close picker' }));
    expect(screen.queryByRole('dialog', { name: /Pick items/ })).toBeNull();
  });

  it('switches to the receipt while preserving the existing ItemsSection contract', async () => {
    render(
      <BillDetailsParticipant bill={bill()} currentUser={currentUser} setBill={vi.fn()} />,
    );

    await userEvent.click(screen.getByRole('tab', { name: 'Receipt' }));
    const items = screen.getByTestId('items-section');
    expect(items.closest('[role="tabpanel"]')).not.toHaveAttribute('aria-hidden');
    expect(items).toHaveAttribute('data-current-user', '2');
    expect(items).toHaveAttribute('data-is-creator', 'false');
    expect(items).toHaveAttribute('data-is-closed', 'false');
    expect(items).toHaveAttribute('data-owner-id', '1');
    expect(items).toHaveAttribute('data-requires-recalculation', 'false');
    expect(screen.getByTestId('receipts-section')).toBeVisible();
  });

  it('does not send people to pick dishes outside item splitting and marks legacy splits for recalculation', async () => {
    render(
      <BillDetailsParticipant
        bill={bill({ split_type: SplitType.MANUAL, items: [item()] })}
        currentUser={currentUser}
        setBill={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'pick-20' })).toBeNull();

    await userEvent.click(screen.getByRole('tab', { name: 'Receipt' }));
    expect(screen.getByTestId('items-section')).toHaveAttribute(
      'data-requires-recalculation',
      'true',
    );
  });

  it('keeps only payment undo active while the bill is paid', async () => {
    const paidBill = bill({
      status: BillStatus.PAID,
      participants: [owner, participant({ is_paid: true }), guest],
    });
    const updated = bill({ status: BillStatus.OPEN });
    updatePaymentStatusMock.mockResolvedValue(updated);
    const setBill = vi.fn();

    render(
      <BillDetailsParticipant bill={paidBill} currentUser={currentUser} setBill={setBill} />,
    );

    expect(screen.queryByTestId('invite-row')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Leave bill' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'move-30' })).toBeNull();
    expect(screen.getByTestId('items-section')).toHaveAttribute('data-is-closed', 'true');
    expect(dockState.onTogglePaid).toBeTypeOf('function');

    await act(async () => {
      dockState.onTogglePaid?.();
    });
    await waitFor(() =>
      expect(updatePaymentStatusMock).toHaveBeenCalledWith(7, 20, false, currentUser.id),
    );
    await waitFor(() => expect(setBill).toHaveBeenCalledWith(updated));
  });

  it('does not expose a payment confirmation for an unpaid participant in paid state', () => {
    render(
      <BillDetailsParticipant
        bill={bill({ status: BillStatus.PAID })}
        currentUser={currentUser}
        setBill={vi.fn()}
      />,
    );

    expect(dockState.onTogglePaid).toBeUndefined();
  });

  it('opens the same item sheet from the empty-share dock action', () => {
    render(
      <BillDetailsParticipant
        bill={bill({ participants: [owner, participant({ allocated_amount: 0 }), guest] })}
        currentUser={currentUser}
        setBill={vi.fn()}
      />,
    );

    expect(screen.getByRole('tab', { name: 'Participants' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    act(() => dockState.onSelectItems?.());
    expect(screen.getByRole('dialog', { name: 'Pick items for 20 as 2' })).toBeInTheDocument();
  });

  it('guards payment updates against rapid duplicate calls and exposes busy state', async () => {
    let resolvePayment!: (updated: BillDetail) => void;
    const updated = bill({ participants: [owner, participant({ is_paid: true }), guest] });
    updatePaymentStatusMock.mockReturnValue(
      new Promise<BillDetail>((resolve) => {
        resolvePayment = resolve;
      }),
    );
    const setBill = vi.fn();
    render(<BillDetailsParticipant bill={bill()} currentUser={currentUser} setBill={setBill} />);

    act(() => {
      dockState.onTogglePaid?.();
      dockState.onTogglePaid?.();
    });
    expect(updatePaymentStatusMock).toHaveBeenCalledTimes(1);
    expect(updatePaymentStatusMock).toHaveBeenCalledWith(7, 20, true, 2);
    await waitFor(() => expect(screen.getByTestId('payment-dock')).toHaveAttribute('data-loading', 'true'));

    resolvePayment(updated);
    await waitFor(() => expect(setBill).toHaveBeenCalledWith(updated));
    await waitFor(() => expect(screen.getByTestId('payment-dock')).toHaveAttribute('data-loading', 'false'));
  });

  it('keeps the move-seat confirmation flow', async () => {
    const updated = bill({ participants: [owner, participant(), { ...guest, user_id: 2 }] });
    claimSeatMock
      .mockRejectedValueOnce({ response: { data: { detail: 'SEAT_MOVE_CONFIRM' } } })
      .mockResolvedValueOnce(updated);
    const setBill = vi.fn();
    render(<BillDetailsParticipant bill={bill()} currentUser={currentUser} setBill={setBill} />);

    fireEvent.click(screen.getByRole('button', { name: 'move-30' }));
    expect(await screen.findByRole('dialog', { name: 'Move seat' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm move' }));

    await waitFor(() => expect(claimSeatMock).toHaveBeenLastCalledWith(7, 30, 2, null, true));
    await waitFor(() => expect(setBill).toHaveBeenCalledWith(updated));
  });

  it('keeps the leave confirmation and navigates home after deletion', async () => {
    render(
      <BillDetailsParticipant bill={bill()} currentUser={currentUser} setBill={vi.fn()} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Leave bill' }));
    const dialog = screen.getByRole('dialog', { name: 'Leave bill' });
    expect(within(dialog).getByText('Leave this bill?')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Leave bill' }));

    await waitFor(() =>
      expect(deleteBillParticipantMock).toHaveBeenCalledWith(7, 20, currentUser.id),
    );
    expect(routerPushMock).toHaveBeenCalledWith('/');
  });
});
