import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BillStatus, SplitType, type BillDetail, type BillParticipant } from '@/types/api';
import { billFixture, itemFixture, participantFixture } from '@/test/billFixtures';

// useTranslation reads `language`; the viewer is user 999.
vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 999 } };
  return {
    useStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

import ParticipantCard from './ParticipantCard';

const me = participantFixture({ id: 1, user_id: 999, name: 'Leonid', surname: 'Petrov', allocated_amount: 1000 });
const bob = participantFixture({ id: 2, user_id: 20, name: 'Bob', allocated_amount: 500 });
const guest = participantFixture({
  id: 3, user_id: null, name: null, username: null, is_guest: true, seat_index: 3, allocated_amount: 500,
});

const makeBill = (overrides: Partial<BillDetail> = {}): BillDetail => billFixture({
  owner_id: 999,
  participants: [me, bob, guest],
  items: [
    itemFixture({ id: 5, name: 'Plov', item_sum: 1000, portions: [[1]], assigned_participant_ids: [1] }),
    itemFixture({ id: 6, name: 'Tea', price: 250, count: 2, item_sum: 500, portions: [[2], [3]], assigned_participant_ids: [2, 3] }),
  ],
  ...overrides,
});

type CardProps = Parameters<typeof ParticipantCard>[0];
const renderCard = (participant: BillParticipant, props: Partial<CardProps> = {}) =>
  render(<ParticipantCard bill={makeBill()} participant={participant} {...props} />);

const expand = (name: RegExp | string) =>
  fireEvent.click(screen.getByRole('button', { name, expanded: false }));

describe('ParticipantCard — the collapsed row', () => {
  it('reads as avatar, first name and amount, without a role or a «You» tag', () => {
    renderCard(me);

    expect(screen.getByText('Leonid')).toBeInTheDocument();
    expect(screen.queryByText(/Petrov/)).toBeNull();
    expect(screen.queryByText('You')).toBeNull();
    expect(screen.queryByText('Creator')).toBeNull();
    expect(screen.getByText(/1[\s ]000/)).toBeInTheDocument();
  });

  it('names an empty seat by its number and nothing more', () => {
    renderCard(guest);

    expect(screen.getByText('Guest 3')).toBeInTheDocument();
    expect(screen.queryByText('Free seat')).toBeNull();
  });

  it('stamps a paid share and nothing else', () => {
    const { unmount } = renderCard({ ...bob, is_paid: true });
    expect(screen.getByRole('img', { name: 'Paid' })).toBeInTheDocument();
    unmount();

    render(
      <ParticipantCard bill={makeBill({ status: BillStatus.CLOSED })} participant={bob} />,
    );
    expect(screen.queryByRole('img', { name: 'Paid' })).toBeNull();
  });

  it('opens from anywhere on the row but the renamable name', () => {
    renderCard(guest, { onRenameGuest: vi.fn(), onAssignItems: vi.fn() });

    expand(/^Guest 3$/);
    expect(screen.getByRole('button', { name: 'Assign' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rename: Guest 3' })).toBeInTheDocument();
  });

  it('is not a button when there is nothing to open', () => {
    render(
      <ParticipantCard bill={makeBill({ items: [] })} participant={{ ...bob, allocated_amount: 0 }} />,
    );

    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('ParticipantCard — disclosure', () => {
  it('opens the own seat by default and lists its dishes', () => {
    renderCard(me, { defaultExpanded: true });

    expect(screen.getByRole('button', { name: /Leonid/, expanded: true })).toBeInTheDocument();
    expect(screen.getByText('Plov')).toBeInTheDocument();
  });

  it('keeps other seats closed until tapped, and closes them again', async () => {
    renderCard(bob);
    expect(screen.queryByText('Tea')).toBeNull();

    expand(/Bob/);
    expect(screen.getByText('Tea')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Bob/, expanded: true }));
    await waitFor(() => expect(screen.queryByText('Tea')).toBeNull());
  });

  it('follows a new default when the row changes hands', () => {
    const { rerender } = renderCard(bob);
    expect(screen.queryByText('Tea')).toBeNull();

    rerender(<ParticipantCard bill={makeBill()} participant={bob} defaultExpanded />);
    expect(screen.getByText('Tea')).toBeInTheDocument();
  });
});

describe('ParticipantCard — owner actions', () => {
  it('keeps «Add a person» in sight on an empty seat only, in place of its face', () => {
    const onAddPerson = vi.fn();
    const { unmount } = renderCard(guest, { onAddPerson });

    fireEvent.click(screen.getByRole('button', { name: 'Add a person' }));
    expect(onAddPerson).toHaveBeenCalledWith(3);
    // It opens the invite, not the row.
    expect(screen.getByRole('button', { name: /^Guest 3$/ })).toHaveAttribute('aria-expanded', 'false');
    unmount();

    renderCard(bob, { onAddPerson });
    expect(screen.queryByRole('button', { name: 'Add a person' })).toBeNull();
  });

  it('offers nothing on an empty seat of a closed bill', () => {
    render(
      <ParticipantCard
        bill={makeBill({ status: BillStatus.CLOSED })}
        participant={guest}
        onAddPerson={vi.fn()}
        onDelete={vi.fn()}
        onRenameGuest={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Add a person' })).toBeNull();
    expand(/Guest 3/);
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Rename/ })).toBeNull();
  });

  it('folds its actions away with the dishes until the row is opened', () => {
    const onAssignItems = vi.fn();
    renderCard(bob, { onAssignItems });

    expect(screen.queryByText('Tea')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Assign' })).toBeNull();

    expand(/Bob/);
    expect(screen.getByText('Tea')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    expect(onAssignItems).toHaveBeenCalledTimes(1);
  });

  it('opens for its actions alone when the seat has no dishes', () => {
    render(<ParticipantCard bill={makeBill({ items: [] })} participant={bob} onAssignItems={vi.fn()} />);

    expect(screen.queryByRole('button', { name: 'Assign' })).toBeNull();
    expand(/Bob/);
    expect(screen.getByRole('button', { name: 'Assign' })).toBeInTheDocument();
  });

  it('puts nothing more on a share that is already paid', () => {
    renderCard({ ...bob, is_paid: true }, { onAssignItems: vi.fn() });

    expand(/Bob/);
    expect(screen.queryByRole('button', { name: 'Assign' })).toBeNull();
  });

  it('marks only an empty seat with a share as paid, straight away', () => {
    const onTogglePayment = vi.fn();
    const { unmount } = renderCard(guest, { onTogglePayment });

    expand(/Guest 3/);
    fireEvent.click(screen.getByRole('button', { name: 'Mark as paid' }));
    expect(onTogglePayment).toHaveBeenCalledWith(3, false);
    expect(screen.queryByText('Are you sure you want to cancel the payment?')).toBeNull();
    unmount();

    for (const participant of [bob, { ...guest, allocated_amount: 0 }]) {
      const view = renderCard(participant, { onTogglePayment });
      if (screen.queryByRole('button', { expanded: false })) {
        fireEvent.click(screen.getByRole('button', { expanded: false }));
      }
      expect(screen.queryByRole('button', { name: 'Mark as paid' })).toBeNull();
      view.unmount();
    }
  });

  it('asks before undoing a payment', () => {
    const onTogglePayment = vi.fn();
    renderCard({ ...guest, is_paid: true }, { onTogglePayment });
    expand(/Guest 3/);

    fireEvent.click(screen.getByRole('button', { name: 'Undo payment' }));
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(onTogglePayment).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Undo payment' }));
    fireEvent.click(screen.getByRole('button', { name: /yes, cancel/i }));
    expect(onTogglePayment).toHaveBeenCalledWith(3, true);
  });

  it('lets the owner take back the payment of someone who joined, and only take it back', () => {
    const onTogglePayment = vi.fn();
    const { unmount } = renderCard({ ...bob, is_paid: true }, { onTogglePayment });

    expand(/Bob/);
    fireEvent.click(screen.getByRole('button', { name: 'Undo payment' }));
    fireEvent.click(screen.getByRole('button', { name: /yes, cancel/i }));
    expect(onTogglePayment).toHaveBeenCalledWith(2, true);
    unmount();

    renderCard(bob, { onTogglePayment });
    expand(/Bob/);
    expect(screen.queryByRole('button', { name: 'Undo payment' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Mark as paid' })).toBeNull();
  });

  it('removes anyone but the owner', () => {
    const onDelete = vi.fn();
    const { unmount } = renderCard(bob, { onDelete });

    expand(/Bob/);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onDelete).toHaveBeenCalledWith(2);
    unmount();

    renderCard(me, { onDelete, defaultExpanded: true });
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });

  it('removes an empty seat only while renaming it', () => {
    const onDelete = vi.fn();
    renderCard(guest, { onDelete, onRenameGuest: vi.fn(), onAssignItems: vi.fn(), defaultExpanded: true });
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Rename: Guest 3' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(onDelete).toHaveBeenCalledWith(3);
  });

  it('renames an empty seat by tapping its name and confirms it with a check mark', async () => {
    const onRenameGuest = vi.fn().mockResolvedValue(undefined);
    renderCard(guest, { onRenameGuest });

    fireEvent.click(screen.getByRole('button', { name: 'Rename: Guest 3' }));
    expect(screen.queryByRole('button', { name: /Guest 3/, expanded: true })).toBeNull();
    fireEvent.change(screen.getByRole('textbox', { name: 'Rename' }), { target: { value: '  Aziza ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onRenameGuest).toHaveBeenCalledWith(3, 'Aziza'));
    expect(await screen.findByRole('status', { name: 'Saved' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Rename' })).toBeNull();
  });

  it('keeps the draft open when the rename fails', async () => {
    const onRenameGuest = vi.fn().mockRejectedValue(new Error('offline'));
    renderCard(guest, { onRenameGuest });

    fireEvent.click(screen.getByRole('button', { name: 'Rename: Guest 3' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Rename' }), { target: { value: 'Aziza' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled());
    expect(screen.getByRole('textbox', { name: 'Rename' })).toHaveValue('Aziza');
    expect(screen.queryByRole('status', { name: 'Saved' })).toBeNull();
  });

  it('leaves the name alone when renaming is cancelled', () => {
    const onRenameGuest = vi.fn();
    renderCard(guest, { onRenameGuest });

    fireEvent.click(screen.getByRole('button', { name: 'Rename: Guest 3' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Rename' }), { target: { value: 'Aziza' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onRenameGuest).not.toHaveBeenCalled();
    expect(screen.getByText('Guest 3')).toBeInTheDocument();
  });

  it('drops an amount being typed when the row folds', () => {
    render(
      <ParticipantCard
        bill={makeBill({ split_type: SplitType.MANUAL, items: [] })}
        participant={bob}
        onAssignAmount={vi.fn()}
      />,
    );

    expand(/Bob/);
    fireEvent.click(screen.getByRole('button', { name: 'Set amount' }));
    fireEvent.click(screen.getByRole('button', { name: /Bob/, expanded: true }));
    expand(/Bob/);

    expect(screen.queryByRole('textbox', { name: 'Set amount' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Set amount' })).toBeInTheDocument();
  });

  it('sets and resets a manual share', async () => {
    const onAssignAmount = vi.fn().mockResolvedValue(undefined);
    render(
      <ParticipantCard
        bill={makeBill({ split_type: SplitType.MANUAL, items: [] })}
        participant={bob}
        onAssignAmount={onAssignAmount}
      />,
    );

    expand(/Bob/);
    fireEvent.click(screen.getByRole('button', { name: 'Set amount' }));
    expect(screen.getByRole('textbox', { name: 'Set amount' })).toHaveValue('500');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onAssignAmount).toHaveBeenCalledWith(2, 500));

    fireEvent.click(screen.getByRole('button', { name: 'Reset share' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onAssignAmount).toHaveBeenLastCalledWith(2, 0);
  });

  it('works out a typed sum and refuses a share below zero', async () => {
    const onAssignAmount = vi.fn().mockResolvedValue(undefined);
    render(
      <ParticipantCard
        bill={makeBill({ split_type: SplitType.MANUAL, items: [] })}
        participant={bob}
        onAssignAmount={onAssignAmount}
      />,
    );

    expand(/Bob/);
    fireEvent.click(screen.getByRole('button', { name: 'Set amount' }));
    const field = screen.getByRole('textbox', { name: 'Set amount' });
    fireEvent.change(field, { target: { value: '-500' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onAssignAmount).not.toHaveBeenCalled();

    fireEvent.change(field, { target: { value: '5000-3000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onAssignAmount).toHaveBeenCalledWith(2, 2000));
  });
});

describe('ParticipantCard — participant actions', () => {
  it('moves onto an empty seat from its opened row', () => {
    const onTakeSeat = vi.fn();
    renderCard(guest, { onTakeSeat });

    expand(/Guest 3/);
    fireEvent.click(screen.getByRole('button', { name: 'Move here' }));
    expect(onTakeSeat).toHaveBeenCalledTimes(1);
  });

  it('sends the viewer from their own row to the receipt', () => {
    const onPickItems = vi.fn();
    renderCard(me, { onPickItems, defaultExpanded: true });

    fireEvent.click(screen.getByRole('button', { name: 'Choose items' }));
    expect(onPickItems).toHaveBeenCalledTimes(1);
  });
});

describe('ParticipantCard — reminders', () => {
  const NOW = new Date('2026-10-01T12:00:00Z');
  const minutes = (n: number) => new Date(NOW.getTime() + n * 60_000).toISOString();

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('reminds someone who joined and still owes', async () => {
    const onRemind = vi.fn().mockResolvedValue(undefined);
    renderCard(bob, { onRemind });

    expand(/Bob/);
    fireEvent.click(screen.getByRole('button', { name: 'Remind' }));

    await waitFor(() => expect(onRemind).toHaveBeenCalledWith(2));
  });

  it('says when they were reminded and when the next one can go', () => {
    renderCard({ ...bob, reminder: { status: 'sent', at: minutes(-5), failure: null, next_at: minutes(55) } }, { onRemind: vi.fn() });

    expand(/Bob/);
    expect(screen.getByRole('button', { name: 'Reminded 5 min ago' })).toBeDisabled();
    expect(screen.getByText('Again in 55 min')).toBeInTheDocument();
  });

  it('explains a reminder nobody could deliver', () => {
    renderCard(
      { ...bob, reminder: { status: 'failed', at: minutes(-1), failure: 'unreachable', next_at: minutes(59) } },
      { onRemind: vi.fn() },
    );

    expand(/Bob/);
    expect(screen.getByRole('button', { name: 'Not delivered' })).toBeDisabled();
    expect(screen.getByText(/no @username/)).toBeInTheDocument();
  });

  it('offers another try after one that got lost on the way', () => {
    renderCard(
      { ...bob, reminder: { status: 'failed', at: minutes(-1), failure: 'no_senders', next_at: null } },
      { onRemind: vi.fn() },
    );

    expand(/Bob/);
    expect(screen.getByRole('button', { name: 'Remind again' })).toBeEnabled();
    expect(screen.getByText('The last reminder did not get through.')).toBeInTheDocument();
  });

  it('is not offered for an empty seat, a paid share or the owner', () => {
    for (const participant of [guest, { ...bob, is_paid: true }, me]) {
      const view = renderCard(participant, { onRemind: vi.fn(), defaultExpanded: true });
      expect(screen.queryByRole('button', { name: 'Remind' })).toBeNull();
      view.unmount();
    }
  });
});

describe('ParticipantCard — for the guest tour', () => {
  it('marks the viewer’s own seat and its «Choose items», and nobody else’s', () => {
    const { container } = render(
      <>
        <ParticipantCard bill={makeBill()} participant={me} defaultExpanded onPickItems={vi.fn()} />
        <ParticipantCard bill={makeBill()} participant={bob} />
      </>,
    );

    expect(container.querySelectorAll('[data-tour="my-seat"]')).toHaveLength(1);
    expect(container.querySelector('[data-tour="my-seat"]')).toHaveTextContent('Leonid');
    expect(container.querySelector('[data-tour="choose-items"]')).toBeInTheDocument();
  });
});
