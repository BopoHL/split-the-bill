import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { BillDetail, BillParticipant, User } from '@/types/api';
import { BillStatus, SplitType } from '@/types/api';

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  searchParams: new URLSearchParams(),
}));

const api = vi.hoisted(() => ({
  addBillItem: vi.fn(),
  assignAmount: vi.fn(),
  updatePaymentStatus: vi.fn(),
  deleteBillParticipant: vi.fn(),
  closeBill: vi.fn(),
  reopenBill: vi.fn(),
  updateBill: vi.fn(),
  assignBillItemsBatch: vi.fn(),
  renameGuest: vi.fn(),
  getBill: vi.fn(),
  preparePersonalSeatInvite: vi.fn(),
  assignSeatUser: vi.fn(),
}));
const telegram = vi.hoisted(() => ({
  canShareMessage: vi.fn(),
  shareMessage: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigation.push }),
  useSearchParams: () => navigation.searchParams,
}));

vi.mock('@/lib/api/bills', () => api);
const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));
vi.mock('@/lib/telegram/share', () => ({
  canShareMessage: telegram.canShareMessage,
  shareMessage: telegram.shareMessage,
}));
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    language: 'en',
    t: (key: string, params?: Record<string, string>) =>
      params
        ? Object.entries(params).reduce(
            (text, [name, value]) => `${text} ${name}:${value}`,
            key,
          )
        : key,
  }),
}));

vi.mock('@/components/ui/Button', () => ({
  default: ({
    children,
    isLoading,
    variant,
    ...props
  }: ButtonHTMLAttributes<HTMLButtonElement> & {
    isLoading?: boolean;
    variant?: string;
  }) => {
    void isLoading;
    void variant;
    return <button {...props}>{children}</button>;
  },
}));
vi.mock('@/components/ui/Modal', () => ({
  default: ({ isOpen, title, children }: {
    isOpen: boolean;
    title: ReactNode;
    children: ReactNode;
  }) => isOpen ? <div role="dialog" aria-label={String(title)}>{children}</div> : null,
}));
vi.mock('@/components/ui/NumericKeypad', () => ({ default: () => null }));

vi.mock('./BillDetailsTabs', () => ({
  default: ({ value, onChange, participants, receipt }: {
    value: 'participants' | 'receipt';
    onChange: (value: 'participants' | 'receipt') => void;
    participants: ReactNode;
    receipt: ReactNode;
  }) => (
    <div>
      <button type="button" onClick={() => onChange('participants')}>Participants tab</button>
      <button type="button" onClick={() => onChange('receipt')}>Receipt tab</button>
      <div data-testid="active-tab">{value}</div>
      {value === 'participants' ? participants : receipt}
    </div>
  ),
}));
vi.mock('./BillPaymentDock', () => ({
  BESIDE_AMOUNT: '',
  default: ({ onCloseBill, onReopenBill, onUpdatePaymentDetails, takeover }: {
    onCloseBill?: () => void;
    onReopenBill?: () => void;
    onUpdatePaymentDetails?: (value: string) => Promise<void>;
    takeover?: ReactNode;
  }) => (
    <div data-testid="payment-dock">
      {takeover ?? (
        <>
          <button type="button" onClick={onCloseBill}>Dock close</button>
          <button type="button" onClick={onReopenBill}>Dock reopen</button>
          <button type="button" onClick={() => void onUpdatePaymentDetails?.('new card')}>
            Dock update payment
          </button>
        </>
      )}
    </div>
  ),
}));
vi.mock('./BillOverview', () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="bill-overview">{children}</div>,
}));
vi.mock('./ItemsSection', () => ({
  default: ({ onAddItem, ownerId, requiresRecalculation, selection }: {
    onAddItem?: (name: string, price: number, count: number) => Promise<void>;
    ownerId: number;
    requiresRecalculation: boolean;
    selection?: { start: () => void; toggle: (keys: string[]) => void };
  }) => (
    <div
      data-testid="items-section"
      data-owner-id={ownerId}
      data-requires-recalculation={String(requiresRecalculation)}
    >
      <button type="button" onClick={() => void onAddItem?.('Tea', 1250, 7)}>
        Add mocked item
      </button>
      <button type="button" onClick={() => void onAddItem?.('Water', 0, 7)}>
        Add zero item
      </button>
      <button type="button" onClick={selection?.start}>Mock start picking</button>
      <button type="button" onClick={() => selection?.toggle(['50:1'])}>Mock pick a tea</button>
    </div>
  ),
}));
vi.mock('./receipts/ReceiptsSection', () => ({ default: () => <div>Receipts content</div> }));
vi.mock('./ParticipantCard', () => ({
  default: ({ participant, defaultExpanded, onAssignItems, onAssignAmount, onAddPerson }: {
    participant: BillParticipant;
    defaultExpanded?: boolean;
    onAssignItems?: () => void;
    onAssignAmount?: unknown;
    onAddPerson?: (id: number) => void;
  }) => (
    <article
      data-testid={`participant-card-${participant.id}`}
      data-default-expanded={String(Boolean(defaultExpanded))}
      data-can-set-amount={String(Boolean(onAssignAmount))}
      data-can-add-person={String(Boolean(onAddPerson))}
    >
      {onAssignItems && (
        <button type="button" onClick={onAssignItems}>Assign items to {participant.id}</button>
      )}
      {onAddPerson && (
        <button type="button" onClick={() => onAddPerson(participant.id)}>
          Open person picker {participant.id}
        </button>
      )}
    </article>
  ),
}));
vi.mock('./ParticipantItemsDialog', () => ({
  default: ({ participant, onClose }: {
    participant: BillParticipant;
    onClose: () => void;
  }) => (
    <div role="dialog" aria-label={`Items for ${participant.id}`}>
      <button type="button" onClick={onClose}>Close item dialog</button>
    </div>
  ),
}));
vi.mock('./invite/InviteRow', () => ({ default: () => <div>Invite row</div> }));
vi.mock('./invite/InvitePrompt', () => ({ default: () => null }));
vi.mock('./AssignUserPicker', () => ({
  default: ({ isOpen, onSendPersonalInvite }: {
    isOpen: boolean;
    onSendPersonalInvite?: () => Promise<void>;
  }) => isOpen ? (
    <div role="dialog" aria-label="Person picker">
      {onSendPersonalInvite && (
        <button type="button" onClick={() => void onSendPersonalInvite()}>
          Picker personal invite
        </button>
      )}
    </div>
  ) : null,
}));

import BillDetailsCreator from './BillDetailsCreator';

const owner: User = {
  id: 10,
  telegram_id: 100,
  username: 'owner',
  name: 'Owner',
  surname: null,
  avatar_url: null,
};

const participant = (
  id: number,
  userId: number | null,
  overrides: Partial<BillParticipant> = {},
): BillParticipant => ({
  id,
  bill_id: 7,
  user_id: userId,
  guest_name: userId == null ? `Guest ${id}` : null,
  username: userId == null ? null : `user${userId}`,
  name: userId == null ? null : `Person ${userId}`,
  surname: null,
  avatar_url: null,
  allocated_amount: 1250,
  is_paid: false,
  seat_index: id - 1,
  is_guest: userId == null,
  claimed_at: null,
  ...overrides,
});

const makeBill = (overrides: Partial<BillDetail> = {}): BillDetail => ({
  id: 7,
  owner_id: owner.id,
  total_sum: 2500,
  title: 'Dinner',
  payment_details: '8600 0000 0000 0000',
  participants_count: 2,
  status: BillStatus.OPEN,
  created_at: '2026-09-18T12:00:00Z',
  split_type: SplitType.BY_ITEMS,
  currency: 'uzs',
  unallocated_sum: 0,
  public_token: 'public',
  expected_people: 2,
  participants: [participant(1, owner.id), participant(2, null)],
  items: [
    {
      id: 50,
      bill_id: 7,
      name: 'Tea',
      price: 1250,
      count: 2,
      item_sum: 2500,
      is_shared_globally: false,
      assigned_participant_ids: [1, 2],
      portions: [[1], [1, 2]],
      receipt_task_id: null,
    },
  ],
  receipts: [],
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  navigation.searchParams = new URLSearchParams();
  api.addBillItem.mockResolvedValue({ id: 99 });
  api.closeBill.mockResolvedValue(undefined);
  api.updateBill.mockImplementation(async () => makeBill({ payment_details: 'new card' }));
  telegram.canShareMessage.mockReturnValue(false);
  telegram.shareMessage.mockReturnValue(false);
});

describe('BillDetailsCreator redesign integration', () => {
  it('starts on participants with only the own seat opened', () => {
    render(<BillDetailsCreator bill={makeBill()} setBill={vi.fn()} currentUser={owner} />);

    expect(screen.getByTestId('active-tab')).toHaveTextContent('participants');
    expect(screen.getByTestId('participant-card-1')).toHaveAttribute('data-default-expanded', 'true');
    expect(screen.getByTestId('participant-card-2')).toHaveAttribute('data-default-expanded', 'false');
    expect(screen.getByTestId('payment-dock')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'bill.editPeople' })).toBeInTheDocument();
    expect(screen.getByText('Invite row').compareDocumentPosition(screen.getByTestId('participant-card-1')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('starts on the receipt tab for the bot scan query', () => {
    navigation.searchParams = new URLSearchParams('scan=1');

    render(<BillDetailsCreator bill={makeBill()} setBill={vi.fn()} currentUser={owner} />);

    expect(screen.getByTestId('active-tab')).toHaveTextContent('receipt');
    expect(screen.getByTestId('bill-overview')).toBeInTheDocument();
  });

  it('opens the assignment dialog for the selected participant', async () => {
    const user = userEvent.setup();
    render(<BillDetailsCreator bill={makeBill()} setBill={vi.fn()} currentUser={owner} />);

    await user.click(screen.getByRole('button', { name: 'Assign items to 2' }));
    expect(screen.getByRole('dialog', { name: 'Items for 2' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Close item dialog' }));
    await user.click(screen.getByRole('button', { name: 'Assign items to 1' }));
    expect(screen.getByRole('dialog', { name: 'Items for 1' })).toBeInTheDocument();
  });

  it('fills an empty seat through one picker that also sends the personal invite', async () => {
    telegram.canShareMessage.mockReturnValue(true);
    telegram.shareMessage.mockReturnValue(true);
    api.preparePersonalSeatInvite.mockResolvedValue('PREPARED-ZERO-SHARE');
    const emptyGuestBill = makeBill({
      items: [],
      unallocated_sum: 2500,
      participants: [
        participant(1, owner.id),
        participant(2, null, { allocated_amount: 0 }),
      ],
    });
    render(<BillDetailsCreator bill={emptyGuestBill} setBill={vi.fn()} currentUser={owner} />);

    expect(screen.getByTestId('participant-card-1')).toHaveAttribute('data-can-add-person', 'false');
    await userEvent.click(screen.getByRole('button', { name: 'Open person picker 2' }));
    await userEvent.click(screen.getByRole('button', { name: 'Picker personal invite' }));

    await waitFor(() =>
      expect(api.preparePersonalSeatInvite).toHaveBeenCalledWith(7, 2, 'en'),
    );
    expect(telegram.shareMessage).toHaveBeenCalledWith('PREPARED-ZERO-SHARE');
    expect(api.assignSeatUser).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: 'Person picker' })).toBeNull();
  });

  it('offers manual amounts only on a bill without items and flags recalculation to ItemsSection', async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <BillDetailsCreator
        bill={makeBill({ split_type: SplitType.MANUAL })}
        setBill={vi.fn()}
        currentUser={owner}
      />,
    );
    expect(screen.getByTestId('participant-card-2')).toHaveAttribute('data-can-set-amount', 'false');

    rerender(
      <BillDetailsCreator
        bill={makeBill({ split_type: SplitType.MANUAL, items: [] })}
        setBill={vi.fn()}
        currentUser={owner}
      />,
    );
    expect(screen.getByTestId('participant-card-2')).toHaveAttribute('data-can-set-amount', 'true');

    rerender(
      <BillDetailsCreator
        bill={makeBill({ split_type: SplitType.MANUAL })}
        setBill={vi.fn()}
        currentUser={owner}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Receipt tab' }));
    expect(screen.getByTestId('items-section')).toHaveAttribute('data-owner-id', '10');
    expect(screen.getByTestId('items-section')).toHaveAttribute(
      'data-requires-recalculation',
      'true',
    );
  });

  it('adds the item with its quantity and refetches the authoritative bill', async () => {
    const user = userEvent.setup();
    const setBill = vi.fn();
    const refreshed = makeBill({ total_sum: 3750 });
    api.getBill.mockResolvedValue(refreshed);
    render(<BillDetailsCreator bill={makeBill()} setBill={setBill} currentUser={owner} />);

    await user.click(screen.getByRole('button', { name: 'Receipt tab' }));
    await user.click(screen.getByRole('button', { name: 'Add mocked item' }));

    await waitFor(() => {
      expect(api.addBillItem).toHaveBeenCalledWith(7, {
        name: 'Tea',
        price: 1250,
        count: 7,
      });
      expect(api.getBill).toHaveBeenCalledWith(7, owner.id);
      expect(setBill).toHaveBeenCalledWith(refreshed);
    });
  });

  it('counts an added line as added even when the bill cannot be reloaded', async () => {
    const user = userEvent.setup();
    const { showToast } = await import('@/lib/toast');
    api.getBill.mockRejectedValue(new Error('offline'));
    render(<BillDetailsCreator bill={makeBill()} setBill={vi.fn()} currentUser={owner} />);

    await user.click(screen.getByRole('button', { name: 'Receipt tab' }));
    await user.click(screen.getByRole('button', { name: 'Add mocked item' }));

    await waitFor(() => expect(track).toHaveBeenCalledWith('items_added', { bill_id: 7, count: 1 }));
    expect(showToast).not.toHaveBeenCalled();
  });

  it('allows a finite zero-price item', async () => {
    const user = userEvent.setup();
    api.getBill.mockResolvedValue(makeBill({ total_sum: 2500 }));
    render(<BillDetailsCreator bill={makeBill()} setBill={vi.fn()} currentUser={owner} />);

    await user.click(screen.getByRole('button', { name: 'Receipt tab' }));
    await user.click(screen.getByRole('button', { name: 'Add zero item' }));

    await waitFor(() => {
      expect(api.addBillItem).toHaveBeenCalledWith(7, {
        name: 'Water',
        price: 0,
        count: 7,
      });
    });
  });

  it('routes dock close through the existing remainder confirmation', async () => {
    const user = userEvent.setup();
    render(
      <BillDetailsCreator
        bill={makeBill({ unallocated_sum: 500 })}
        setBill={vi.fn()}
        currentUser={owner}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Dock close' }));

    expect(
      screen.getByRole('dialog', { name: 'bill.unallocatedOnCloseTitle' }),
    ).toBeInTheDocument();
    expect(api.closeBill).not.toHaveBeenCalled();
  });

  it('hands the remainder out and closes in one request', async () => {
    const user = userEvent.setup();
    render(
      <BillDetailsCreator
        bill={makeBill({ unallocated_sum: 500 })}
        setBill={vi.fn()}
        currentUser={owner}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Dock close' }));
    await user.click(screen.getByRole('button', { name: 'bill.assignRemainderToMe' }));

    await waitFor(() => expect(api.closeBill).toHaveBeenCalledWith(7, owner.id, 'me'));
    expect(api.assignBillItemsBatch).not.toHaveBeenCalled();
    expect(track).toHaveBeenCalledWith('bill_closed', { bill_id: 7, remainder: 'me' });
  });

  it('keeps direct close, reopen, and payment-detail handlers connected to the dock', async () => {
    const user = userEvent.setup();
    const setBill = vi.fn();
    const openBill = makeBill();
    const { rerender } = render(
      <BillDetailsCreator bill={openBill} setBill={setBill} currentUser={owner} />,
    );

    await user.click(screen.getByRole('button', { name: 'Dock update payment' }));
    await waitFor(() => {
      expect(api.updateBill).toHaveBeenCalledWith(7, {
        payment_details: 'new card',
        user_id: owner.id,
      });
    });

    await user.click(screen.getByRole('button', { name: 'Dock close' }));
    await waitFor(() => {
      expect(api.closeBill).toHaveBeenCalledWith(7, owner.id);
      expect(navigation.push).toHaveBeenCalledWith('/');
    });
    expect(track).toHaveBeenCalledWith('bill_edited', { bill_id: 7, field: 'payment_details' });
    expect(track).toHaveBeenCalledWith('bill_closed', { bill_id: 7, remainder: 'none' });

    const reopened = makeBill();
    api.reopenBill.mockResolvedValue(reopened);
    rerender(
      <BillDetailsCreator
        bill={makeBill({ status: BillStatus.CLOSED })}
        setBill={setBill}
        currentUser={owner}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Dock reopen' }));
    await waitFor(() => {
      expect(api.reopenBill).toHaveBeenCalledWith(7, owner.id);
      expect(setBill).toHaveBeenCalledWith(reopened);
    });
  });
});

describe('picking dishes on the receipt', () => {
  const pickBill = () => makeBill({
    total_sum: 4500,
    items: [
      ...makeBill().items,
      {
        id: 60, bill_id: 7, name: 'Plov', price: 1000, count: 2, item_sum: 2000,
        is_shared_globally: false, assigned_participant_ids: [], portions: [[], []], receipt_task_id: null,
      },
    ],
  });
  const startPicking = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(screen.getByRole('button', { name: 'Receipt tab' }));
    await user.click(screen.getByRole('button', { name: 'Mock start picking' }));
  };

  it('turns the dock into the pick and hands the picked dishes out in one go', async () => {
    const user = userEvent.setup();
    const setBill = vi.fn();
    const assigned = makeBill();
    api.assignBillItemsBatch.mockResolvedValue(assigned);
    render(<BillDetailsCreator bill={pickBill()} setBill={setBill} currentUser={owner} />);
    await startPicking(user);

    expect(screen.queryByRole('button', { name: 'Dock close' })).not.toBeInTheDocument();
    expect(screen.getByText('bill.pickDishes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'bill.assign' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'bill.selectAllFree count:2' }));
    await user.click(screen.getByRole('button', { name: 'Mock pick a tea' }));
    expect(screen.getByText('bill.selectedCount count:3 dishes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'bill.resetSelection' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'bill.assign' }));
    const sheet = screen.getByRole('dialog', { name: 'bill.assignPeople' });
    await user.click(within(sheet).getByRole('checkbox', { name: 'Guest 2' }));
    await user.click(within(sheet).getByRole('button', { name: 'common.confirm' }));

    await waitFor(() => expect(api.assignBillItemsBatch).toHaveBeenCalledWith(7, owner.id, [
      { item_id: 60, portion_index: 0, expected_count: 2, participant_id: 2, is_assigned: true },
      { item_id: 60, portion_index: 1, expected_count: 2, participant_id: 2, is_assigned: true },
    ], []));
    expect(setBill).toHaveBeenCalledWith(assigned);
    expect(screen.queryByRole('dialog', { name: 'bill.assignPeople' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dock close' })).toBeInTheDocument();
  });

  it('drops a picked dish once someone on it has paid, as the receipt does', async () => {
    const user = userEvent.setup();
    const view = render(<BillDetailsCreator bill={pickBill()} setBill={vi.fn()} currentUser={owner} />);
    await startPicking(user);
    await user.click(screen.getByRole('button', { name: 'Mock pick a tea' }));
    expect(screen.getByText(/bill\.selectedCount count:1/)).toBeInTheDocument();

    const paid = pickBill();
    paid.participants = [paid.participants[0], { ...paid.participants[1], is_paid: true }];
    view.rerender(<BillDetailsCreator bill={paid} setBill={vi.fn()} currentUser={owner} />);

    expect(screen.queryByText(/bill\.selectedCount count:1/)).not.toBeInTheDocument();
  });

  it('ends the pick on leaving the receipt', async () => {
    const user = userEvent.setup();
    render(<BillDetailsCreator bill={pickBill()} setBill={vi.fn()} currentUser={owner} />);
    await startPicking(user);

    await user.click(screen.getByRole('button', { name: 'Participants tab' }));
    await user.click(screen.getByRole('button', { name: 'Receipt tab' }));

    expect(screen.getByRole('button', { name: 'Dock close' })).toBeInTheDocument();
  });
});
