import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { billFixture, itemFixture, participantFixture } from '@/test/billFixtures';
import { billPositions } from '@/lib/utils/billPositions';
import { assignBillItemsBatch } from '@/lib/api/bills';
import type { BillItem, BillParticipant } from '@/types/api';
import ItemAssignmentDialog from './ItemAssignmentDialog';

vi.mock('@/lib/store/useStore', () => ({ useStore: (selector?: (state: { language: string }) => unknown) => selector ? selector({ language: 'en' }) : { language: 'en' } }));
vi.mock('@/lib/api/bills', () => ({ assignBillItemsBatch: vi.fn() }));
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));

const participants = [
  ...billFixture().participants,
  participantFixture({ id: 3, user_id: 30, username: 'carol', name: 'Carol', seat_index: 2 }),
];
const samsa = itemFixture({ name: 'Samsa', count: 3, item_sum: 3000, portions: [[1], [1, 2], []] });

function open(item: BillItem, { people = participants, portion }: { people?: BillParticipant[]; portion?: number } = {}) {
  const positions = billPositions([item], people, 'uzs');
  render(
    <ItemAssignmentDialog
      positions={portion == null ? positions : [positions[portion]]}
      participants={people}
      billId={1}
      currentUserId={10}
      ownerId={10}
      onClose={vi.fn()}
    />,
  );
}

const confirm = () => fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(assignBillItemsBatch).mockResolvedValue(billFixture());
});

describe('assigning dishes picked across lines', () => {
  it('leaves a shared line alone when only the other line changes', async () => {
    const bread = itemFixture({ id: 5, name: 'Bread', count: 1, item_sum: 900, is_shared_globally: true });
    const pizza = itemFixture({ id: 6, name: 'Pizza', count: 1, item_sum: 5000, portions: [[]] });
    render(
      <ItemAssignmentDialog
        positions={billPositions([bread, pizza], participants, 'uzs')}
        participants={participants}
        billId={1}
        currentUserId={10}
        ownerId={10}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    confirm();

    // Bread stays everyone's: no shared flag dropped, nobody spelled out on it.
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 6, portion_index: 0, expected_count: 1, participant_id: 2, is_assigned: true },
    ], []));
  });
});

describe('assigning a whole line', () => {
  it('names the line with its quantity and tells who is on only some of it', () => {
    open(samsa);

    expect(screen.getByText('Samsa').closest('p')).toHaveTextContent('Samsa ×3');
    expect(screen.getByRole('checkbox', { name: 'Alice' })).toBePartiallyChecked();
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Bob' })).toBePartiallyChecked();
    expect(screen.getByRole('checkbox', { name: 'Carol' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  });

  it('puts a ticked person on every dish they are not on yet, and nobody else changes', async () => {
    open(samsa);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Carol' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 0, expected_count: 3, participant_id: 3, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 3, is_assigned: true },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 3, is_assigned: true },
    ], []));
  });

  it('takes an unticked person off every dish of the line', async () => {
    open(samsa);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 3, participant_id: 1, is_assigned: false },
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 1, is_assigned: false },
    ], []));
  });

  it('hands one dish to each when as many people are ticked as there are dishes', async () => {
    open(itemFixture({ name: 'Raketki', count: 3, item_sum: 105000, portions: [[], [], []] }));

    for (const name of ['Alice', 'Bob', 'Carol']) fireEvent.click(screen.getByRole('checkbox', { name }));
    expect(screen.getByText('1 each to the ticked people')).toBeInTheDocument();
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 3, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 2, is_assigned: true },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 3, is_assigned: true },
    ], []));
  });

  it('leaves a line everyone shares dish by dish as it is until a tick changes', async () => {
    open(itemFixture({ count: 3, item_sum: 3000, portions: [[1, 2, 3], [1, 2, 3], [1, 2, 3]] }));

    expect(screen.getByText('Ticked people share all 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Carol' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Carol' }));
    expect(screen.getByText('1 each to the ticked people')).toBeInTheDocument();
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 1, is_assigned: false },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 1, is_assigned: false },
      { item_id: 1, portion_index: 0, expected_count: 3, participant_id: 2, is_assigned: false },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 2, is_assigned: false },
      { item_id: 1, portion_index: 0, expected_count: 3, participant_id: 3, is_assigned: false },
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 3, is_assigned: false },
    ], []));
  });

  it('keeps the dishes people already hold when handing a line out', async () => {
    open(itemFixture({ count: 3, item_sum: 3000, portions: [[3], [], [1]] }));

    for (const name of ['Alice', 'Bob', 'Carol']) fireEvent.click(screen.getByRole('checkbox', { name }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 2, is_assigned: true },
    ], []));
  });

  it('has nothing to confirm when a handed-out line is ticked for the same people again', () => {
    open(itemFixture({ count: 3, item_sum: 3000, portions: [[1], [2], [3]] }));

    for (const name of ['Alice', 'Bob', 'Carol']) fireEvent.click(screen.getByRole('checkbox', { name }));

    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  });

  it('pairs people up on each dish when there are twice as many of them', async () => {
    const people = [...participants, participantFixture({ id: 4, user_id: 40, username: 'dan', name: 'Dan', seat_index: 3 })];
    open(itemFixture({ count: 2, item_sum: 2000, portions: [[], []] }), { people });

    for (const name of ['Alice', 'Bob', 'Carol', 'Dan']) fireEvent.click(screen.getByRole('checkbox', { name }));
    expect(screen.getByText('Each dish shared by 2 people')).toBeInTheDocument();
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 2, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 3, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 4, is_assigned: true },
    ], []));
  });

  it('hands out only the dishes picked from a line', async () => {
    const positions = billPositions([itemFixture({ count: 3, item_sum: 3000, portions: [[], [], []] })], participants, 'uzs');
    render(<ItemAssignmentDialog positions={positions.slice(1)} participants={participants} billId={1} currentUserId={10} ownerId={10} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Carol' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 2, is_assigned: true },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 3, is_assigned: true },
    ], []));
  });

  it('hands a line shared among all out to the people left on it', async () => {
    open(itemFixture({ count: 2, item_sum: 2000, is_shared_globally: true }));

    fireEvent.click(screen.getByRole('checkbox', { name: 'Carol' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 2, is_assigned: false },
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 3, is_assigned: false },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 1, is_assigned: false },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 2, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 3, is_assigned: false },
    ], [{ item_id: 1, is_shared_globally: false }]));
  });

  it('prices sharing among all the way the server will split it', () => {
    open(itemFixture({ item_sum: 100000, portions: [[]] }));

    expect(screen.getByText(/33 333–33 334/)).toBeInTheDocument();
  });

  it('has everyone share every dish when the dishes do not divide among them', async () => {
    open(itemFixture({ count: 3, item_sum: 3000, portions: [[], [], []] }));

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    expect(screen.getByText('Ticked people share all 3')).toBeInTheDocument();
    confirm();

    await waitFor(() => expect(vi.mocked(assignBillItemsBatch).mock.calls[0][2]).toHaveLength(6));
  });

  it('splits a line of several dishes among everyone at once', async () => {
    open(samsa);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Share among all' }));
    expect(screen.getByRole('checkbox', { name: 'Carol' })).toBeChecked();
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [], [{ item_id: 1, is_shared_globally: true }]));
  });

  it('spells out every dish when a shared line goes back to chosen people', async () => {
    const people = participants.slice(0, 2);
    open(itemFixture({ count: 2, item_sum: 2000, is_shared_globally: true }), { people });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 2, is_assigned: false },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 2, is_assigned: false },
    ], [{ item_id: 1, is_shared_globally: false }]));
  });

  it('stays unchanged when someone joins the bill while it is open', () => {
    const positions = billPositions([samsa], participants.slice(0, 2), 'uzs');
    const dialog = (people: BillParticipant[]) => (
      <ItemAssignmentDialog positions={positions} participants={people} billId={1} currentUserId={10} ownerId={10} onClose={vi.fn()} />
    );
    const { rerender } = render(dialog(participants.slice(0, 2)));

    rerender(dialog(participants));

    expect(screen.getByRole('checkbox', { name: 'Carol' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  });

  it('leads with sharing among all, priced per person', () => {
    open(samsa);

    const share = screen.getByRole('checkbox', { name: 'Share among all' });
    expect(share.closest('label')).toHaveTextContent(/3 participants · 1\s000 сум each/);
    expect(share.compareDocumentPosition(screen.getByRole('checkbox', { name: 'Alice' }))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('shares part of a line among all by putting everyone on its picked dishes', async () => {
    open(samsa, { portion: 2 });
    expect(screen.getByText('Samsa').closest('p')).not.toHaveTextContent('×');

    fireEvent.click(screen.getByRole('checkbox', { name: 'Share among all' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 2, is_assigned: true },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 3, is_assigned: true },
    ], []));
  });
});

describe('assigning dishes picked across lines', () => {
  const tea = itemFixture({ id: 2, name: 'Tea', item_sum: 500 });
  const openPicked = (positions = billPositions([samsa, tea], participants, 'uzs')) => render(
    <ItemAssignmentDialog positions={positions} participants={participants} billId={1} currentUserId={10} ownerId={10} onClose={vi.fn()} />,
  );

  it('counts the dishes and names each line they come from', () => {
    openPicked([...billPositions([samsa], participants, 'uzs').slice(1), ...billPositions([tea], participants, 'uzs')]);

    expect(screen.getByText('3 dishes')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Items' })).toHaveTextContent('Samsa · 2 of 3');
    expect(screen.getByRole('list', { name: 'Items' })).toHaveTextContent('Tea');
    expect(screen.getByText('Ticked people share each dish')).toBeInTheDocument();
  });

  it('puts a ticked person on every picked dish of every line', async () => {
    openPicked();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Carol' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 3, participant_id: 3, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 3, participant_id: 3, is_assigned: true },
      { item_id: 1, portion_index: 2, expected_count: 3, participant_id: 3, is_assigned: true },
      { item_id: 2, portion_index: 0, expected_count: 1, participant_id: 3, is_assigned: true },
    ], []));
  });

  it('shares every whole line among all at once', async () => {
    openPicked();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Share among all' }));
    confirm();

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [], [
      { item_id: 1, is_shared_globally: true },
      { item_id: 2, is_shared_globally: true },
    ]));
  });
});

describe('a participant who has paid', () => {
  const paidCarol = participants.map((p) => p.id === 3 ? { ...p, is_paid: true } : p);

  it('says they have paid and cannot be put on the dish', () => {
    open(samsa, { people: paidCarol });

    const carol = screen.getByRole('checkbox', { name: 'Carol' });
    expect(carol).toBeDisabled();
    expect(carol.closest('label')).toHaveTextContent('Already paid — can\'t be assigned');
    expect(screen.getByRole('img', { name: 'Paid' })).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Alice' })).toBeEnabled();
  });

  it('does not offer to share the line among all', () => {
    open(samsa, { people: paidCarol });

    expect(screen.queryByRole('checkbox', { name: 'Share among all' })).not.toBeInTheDocument();
  });

  it('keeps a dish they share as it is and explains why', () => {
    const paidAlice = participants.map((p) => p.id === 1 ? { ...p, is_paid: true } : p);
    render(
      <ItemAssignmentDialog positions={billPositions([samsa], paidAlice, 'uzs')} participants={paidAlice} billId={1} currentUserId={20} ownerId={20} onClose={vi.fn()} />,
    );

    expect(screen.getByRole('note')).toHaveTextContent('Undo payment before changing assigned items');
    expect(screen.getByRole('checkbox', { name: 'Carol' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reset selection' })).toBeDisabled();
  });
});
