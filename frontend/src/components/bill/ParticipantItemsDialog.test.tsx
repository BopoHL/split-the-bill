import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { billFixture, itemFixture } from '@/test/billFixtures';
import ParticipantItemsDialog from './ParticipantItemsDialog';
import { assignBillItemsBatch } from '@/lib/api/bills';

vi.mock('@/lib/store/useStore', () => ({ useStore: (selector?: (state: { language: string }) => unknown) => selector ? selector({ language: 'en' }) : { language: 'en' } }));
vi.mock('@/lib/api/bills', () => ({ assignBillItemsBatch: vi.fn() }));
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));

const bill = billFixture({ items: [itemFixture({ portions: [[1]] }), itemFixture({ id: 2, name: 'Tea', portions: [[2]], item_sum: 20 }), itemFixture({ id: 3, name: 'Salad' })] });
beforeEach(() => { vi.resetAllMocks(); vi.mocked(assignBillItemsBatch).mockResolvedValue(bill); });
const setup = () => render(<ParticipantItemsDialog bill={bill} participant={bill.participants[1]} currentUserId={10} onClose={vi.fn()} onBillUpdate={vi.fn()} />);

describe('participant-to-items assignment', () => {
  it('lists nobody’s dishes first, then other people’s, then this participant’s own', () => {
    setup();
    const list = screen.getByRole('group', { name: 'Items' });
    const labels = within(list)
      .getAllByRole('checkbox')
      .map((checkbox) => checkbox.getAttribute('aria-label')?.split(',')[0]);

    expect(labels).toEqual(['Salad', 'Pizza', 'Tea']);
    const groups = [...list.querySelectorAll('[data-assignment-group]')].map((group) => group.getAttribute('data-assignment-group'));
    expect(groups).toEqual(['unassigned', 'others', 'assigned']);
  });

  it('sinks paid dishes to the end of their group', () => {
    const paidBill = billFixture({
      owner_id: 99,
      participants: billFixture().participants.map((p) => ({ ...p, is_paid: p.id === 1 })),
      items: [
        itemFixture({ id: 1, name: 'Paid soup', portions: [[1]] }),
        itemFixture({ id: 2, name: 'Bread', portions: [[1, 2]] }),
        itemFixture({ id: 3, name: 'Tea', portions: [[3]] }),
      ],
    });
    render(<ParticipantItemsDialog bill={{ ...paidBill, participants: [...paidBill.participants, { ...paidBill.participants[1], id: 3, user_id: 30 }] }} participant={paidBill.participants[1]} currentUserId={99} onClose={vi.fn()} onBillUpdate={vi.fn()} />);

    const labels = screen.getAllByRole('checkbox').map((checkbox) => checkbox.getAttribute('aria-label')?.split(',')[0]);
    expect(labels).toEqual(['Tea', 'Paid soup', 'Bread']);
  });

  it('names this person’s own dishes apart from other people’s', () => {
    setup();
    const headings = screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent);

    expect(headings).toEqual(['Unassigned', 'Taken by others', 'Already theirs']);
  });

  it('adds the selected participant without removing another person or existing items', async () => {
    setup();
    expect(screen.getByRole('checkbox', { name: /Tea/ })).toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: /Pizza/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Salad/ }));
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledTimes(1));
    const [billId, requesterId, ops] = vi.mocked(assignBillItemsBatch).mock.calls[0];
    expect([billId, requesterId]).toEqual([1, 10]);
    expect(ops).toHaveLength(2);
    expect(ops).toEqual(expect.arrayContaining([
      { item_id: 1, portion_index: 0, expected_count: 1, participant_id: 2, is_assigned: true },
      { item_id: 3, portion_index: 0, expected_count: 1, participant_id: 2, is_assigned: true },
    ]));
  });
  it('takes a person off a dish they already have', async () => {
    setup();

    fireEvent.click(screen.getByRole('checkbox', { name: /Tea/ }));
    expect(screen.getByText('To add: 0 · To remove: 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 2, portion_index: 0, expected_count: 1, participant_id: 2, is_assigned: false },
    ], []));
  });

  it('reset clears only new selection; cancel never calls the API', () => {
    setup();
    fireEvent.click(screen.getByRole('checkbox', { name: /Pizza/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Tea/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset selection' }));
    expect(screen.getByRole('checkbox', { name: /Pizza/ })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Tea/ })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
  });
  it('keeps the original count guard when a concurrent deletion shifts rows', async () => {
    const initial = billFixture({ items: [itemFixture({ count: 2, portions: [[], []] })] });
    const common = { participant: initial.participants[1], currentUserId: 10, onClose: vi.fn(), onBillUpdate: vi.fn() };
    const { rerender } = render(<ParticipantItemsDialog {...common} bill={initial} />);
    fireEvent.click(screen.getAllByRole('checkbox', { name: /^Pizza,/ })[1]);
    rerender(<ParticipantItemsDialog {...common} bill={{ ...initial, items: [itemFixture()] }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [{ item_id: 1, portion_index: 1, expected_count: 2, participant_id: 2, is_assigned: true }], []));
  });
  it('reads as choosing one’s own dishes when the viewer opens it for their seat', () => {
    const { unmount } = setup();
    expect(screen.getByRole('dialog', { name: 'Assign items' })).toBeInTheDocument();
    unmount();

    render(<ParticipantItemsDialog bill={bill} participant={bill.participants[1]} currentUserId={20} onClose={vi.fn()} onBillUpdate={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: 'Choose items' })).toBeInTheDocument();
  });

  it('shows a line of several dishes with its dishes, each named like the line', () => {
    const lineBill = billFixture({ items: [itemFixture({ name: 'Samsa', count: 3, item_sum: 3000, portions: [[1], [], [2]] })] });
    render(<ParticipantItemsDialog bill={lineBill} participant={lineBill.participants[1]} currentUserId={10} onClose={vi.fn()} onBillUpdate={vi.fn()} />);

    const line = screen.getByRole('checkbox', { name: /^Samsa ×3,/ });
    expect(line).toBePartiallyChecked();
    expect(line.closest('label')).not.toHaveTextContent(/free/);
    const dishes = screen.getAllByRole('checkbox', { name: /^Samsa,/ });
    // The free dish first, then the creator's and this person's in receipt order.
    expect(dishes.map((dish) => [(dish as HTMLInputElement).checked, (dish as HTMLInputElement).disabled])).toEqual([
      [false, false], [false, false], [true, false],
    ]);
    expect(screen.queryByText(/Portion/)).not.toBeInTheDocument();
  });

  it('takes and gives back every dish of a line nobody else is on with its one tick', async () => {
    const lineBill = billFixture({ items: [itemFixture({ name: 'Samsa', count: 4, item_sum: 4000, portions: [[1], [], [2], []] })] });
    render(<ParticipantItemsDialog bill={lineBill} participant={lineBill.participants[1]} currentUserId={10} onClose={vi.fn()} onBillUpdate={vi.fn()} />);
    const line = screen.getByRole('checkbox', { name: /^Samsa ×4,/ });
    expect(line).toBePartiallyChecked();

    fireEvent.click(line);
    expect(line).toBeChecked();
    expect(screen.getByText('To add: 2')).toBeInTheDocument();
    fireEvent.click(line);
    expect(screen.getByText('To add: 0 · To remove: 1')).toBeInTheDocument();
    expect(line).not.toBeChecked();
    expect(line).not.toBePartiallyChecked();

    fireEvent.click(line);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 1, expected_count: 4, participant_id: 2, is_assigned: true },
      { item_id: 1, portion_index: 3, expected_count: 4, participant_id: 2, is_assigned: true },
    ], []));
  });

  it('lets a person join someone else’s dish only dish by dish', async () => {
    const lineBill = billFixture({ items: [itemFixture({ name: 'Samsa', count: 2, item_sum: 2000, portions: [[1], [1]] })] });
    render(<ParticipantItemsDialog bill={lineBill} participant={lineBill.participants[1]} currentUserId={10} onClose={vi.fn()} onBillUpdate={vi.fn()} />);

    expect(screen.getByRole('checkbox', { name: /^Samsa ×2,/ })).toBeDisabled();
    fireEvent.click(screen.getAllByRole('checkbox', { name: /^Samsa,/ })[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 2, is_assigned: true },
    ], []));
  });

  it('does not offer assignments that would change a paid participant’s share', () => {
    render(<ParticipantItemsDialog bill={{ ...bill, owner_id: 99, participants: bill.participants.map((p) => ({ ...p, is_paid: p.id === 1 })) }} participant={bill.participants[1]} currentUserId={99} onClose={vi.fn()} onBillUpdate={vi.fn()} />);
    expect(screen.getByRole('checkbox', { name: /Pizza/ })).toBeDisabled();
  });

  it('takes a person off a dish shared among all and leaves it to everyone else', async () => {
    const sharedBill = billFixture({ items: [itemFixture({ name: 'Tea', count: 2, item_sum: 2000, is_shared_globally: true, portions: [[], []] })] });
    render(<ParticipantItemsDialog bill={sharedBill} participant={sharedBill.participants[1]} currentUserId={10} onClose={vi.fn()} onBillUpdate={vi.fn()} />);
    const line = screen.getByRole('checkbox', { name: /^Tea ×2,/ });
    expect(line).toBeChecked();

    fireEvent.click(line);
    expect(screen.getByText('To add: 0 · To remove: 2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 0, expected_count: 2, participant_id: 2, is_assigned: false },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 1, is_assigned: true },
      { item_id: 1, portion_index: 1, expected_count: 2, participant_id: 2, is_assigned: false },
    ], [{ item_id: 1, is_shared_globally: false }]));
  });

  it('keeps a dish shared among all as it is while someone on it has paid', () => {
    const sharedBill = billFixture({
      owner_id: 99,
      participants: billFixture().participants.map((p) => ({ ...p, is_paid: p.id === 1 })),
      items: [itemFixture({ name: 'Tea', is_shared_globally: true })],
    });
    render(<ParticipantItemsDialog bill={sharedBill} participant={sharedBill.participants[1]} currentUserId={99} onClose={vi.fn()} onBillUpdate={vi.fn()} />);

    expect(screen.getByRole('checkbox', { name: /Tea/ })).toBeDisabled();
  });

  it('marks a single dish shared among all as such, not with everyone’s faces', () => {
    const sharedBill = billFixture({ items: [itemFixture({ name: 'Tea', is_shared_globally: true, portions: [[1, 2]] })] });
    render(<ParticipantItemsDialog bill={sharedBill} participant={sharedBill.participants[1]} currentUserId={10} onClose={vi.fn()} onBillUpdate={vi.fn()} />);

    const dish = screen.getByRole('checkbox', { name: /Tea/ }).closest('label')!;
    expect(within(dish).getByText('Shared')).toBeInTheDocument();
    expect(within(dish).queryByRole('img')).toBeNull();
  });
});
