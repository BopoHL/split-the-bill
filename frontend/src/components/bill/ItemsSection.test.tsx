import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { billFixture, itemFixture, participantFixture } from '@/test/billFixtures';
import type { ComponentProps } from 'react';
import type { Receipt } from '@/types/api';
import { useDishSelection } from '@/hooks/useDishSelection';
import ItemsSection from './ItemsSection';
import { assignBillItemsBatch, deleteBillItem, getBill, updateBillItem } from '@/lib/api/bills';
import { showToast } from '@/lib/toast';

vi.mock('@/lib/store/useStore', () => ({ useStore: (selector?: (state: { language: string }) => unknown) => selector ? selector({ language: 'en' }) : { language: 'en' } }));
vi.mock('@/lib/api/bills', () => ({ assignBillItemsBatch: vi.fn(), updateBillItem: vi.fn(), deleteBillItem: vi.fn(), getBill: vi.fn() }));
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));

const props = { billId: 1, currentUserId: 10, participants: billFixture().participants, isCreator: false, isClosed: false };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(assignBillItemsBatch).mockResolvedValue(billFixture());
  vi.mocked(getBill).mockResolvedValue(billFixture());
});

describe('receipt positions', () => {
  it('folds a line of several dishes into one «name ×N» row that opens to dishes named like it', () => {
    render(<ItemsSection {...props} items={[itemFixture({ count: 3, item_sum: 3000, portions: [[2], [], []] })]} />);
    const line = screen.getByRole('button', { name: 'Pizza ×3' });

    expect(line).toHaveAttribute('aria-expanded', 'false');
    expect(line.closest('li')).toHaveTextContent('Pizza ×3');
    expect(line.closest('li')).toHaveTextContent(/3\s000/);
    expect(line.closest('li')).not.toHaveTextContent(/free/);
    expect(screen.getByTitle('Bob')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take' })).not.toBeInTheDocument();

    fireEvent.click(line);
    expect(line).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByText('Pizza')).toHaveLength(4);
    expect(screen.getAllByRole('button', { name: 'Take' })).toHaveLength(3);
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByText(/Portion/)).not.toBeInTheDocument();

    fireEvent.click(line);
    expect(line).toHaveAttribute('aria-expanded', 'false');
  });

  it('takes the next free dish straight from the folded line', async () => {
    render(<ItemsSection {...props} items={[itemFixture({ count: 3, item_sum: 3000, portions: [[2], [], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Take 1: Pizza ×3' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [{ item_id: 1, participant_id: 1, portion_index: 1, expected_count: 3, is_assigned: true }]));
  });

  it('keeps a line shared among everyone folded, with nothing to take', () => {
    render(<ItemsSection {...props} items={[itemFixture({ count: 3, item_sum: 3000, is_shared_globally: true })]} />);
    expect(screen.getByText('Pizza').closest('li')).toHaveTextContent('Pizza ×3');
    expect(screen.getByText('Shared')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Pizza ×3' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Take/ })).not.toBeInTheDocument();
    // The whole table is on it: «Shared» says so, without everyone's face.
    expect(screen.queryByTitle('Bob')).not.toBeInTheDocument();
  });

  it('takes a single row and applies the server response immediately', async () => {
    const onBillUpdate = vi.fn();
    render(<ItemsSection {...props} onBillUpdate={onBillUpdate} items={[itemFixture({ count: 2, item_sum: 2000, portions: [[], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pizza ×2' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Take' })[1]);
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [{ item_id: 1, participant_id: 1, portion_index: 1, expected_count: 2, is_assigned: true }]));
    expect(onBillUpdate).toHaveBeenCalledWith(billFixture());
  });

  it('leaves a dish nobody has taken without a caption', () => {
    render(<ItemsSection {...props} items={[itemFixture()]} />);
    expect(screen.getByText('Pizza').closest('li')).not.toHaveTextContent('Unassigned');
  });

  it('drops only the viewer’s assignment', async () => {
    render(<ItemsSection {...props} items={[itemFixture({ portions: [[1, 2]], assigned_participant_ids: [1, 2] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Drop' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [{ item_id: 1, participant_id: 1, portion_index: 0, expected_count: 1, is_assigned: false }]));
  });

  it('shows avatars, a green dollar status, and no strikethrough for a paid position', () => {
    render(<ItemsSection {...props} participants={props.participants.map((p) => ({ ...p, is_paid: true }))} items={[itemFixture({ portions: [[1, 2]] })]} />);
    expect(screen.getByText('Pizza').closest('li')).toHaveClass('bg-green-weak');
    expect(screen.getByLabelText('Paid')).toBeInTheDocument();
    expect(screen.getByText('Pizza').className).not.toContain('line-through');
    expect(screen.getByTitle('Alice')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take' })).not.toBeInTheDocument();
  });

  it('leaves a dish only the creator has open for a guest to share', async () => {
    render(<ItemsSection {...props} currentUserId={20} ownerId={10} items={[itemFixture({ portions: [[1]] })]} />);
    expect(screen.getByText('Pizza').closest('li')).not.toHaveClass('bg-green-weak');
    expect(screen.queryByLabelText('Paid')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Take' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 20, [{ item_id: 1, participant_id: 2, portion_index: 0, expected_count: 1, is_assigned: true }]));
  });

  it('does not mark a partially paid position as paid or let a guest change its split', () => {
    render(<ItemsSection {...props} participants={props.participants.map((p) => ({ ...p, is_paid: p.id === 2 }))} items={[itemFixture({ portions: [[1, 2]] })]} />);
    expect(screen.queryByLabelText('Paid')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Drop' })).toBeDisabled();
  });

  it('locks take actions for a paid viewer and hides all mutations on closed bills', () => {
    const { rerender } = render(<ItemsSection {...props} participants={[participantFixture({ is_paid: true })]} items={[itemFixture()]} />);
    expect(screen.getByRole('button', { name: 'Take' })).toBeDisabled();
    rerender(<ItemsSection {...props} isCreator isClosed items={[itemFixture()]} onStartAdd={vi.fn()} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('keeps global sharing distinct and offers no self-drop on it', () => {
    render(<ItemsSection {...props} items={[itemFixture({ is_shared_globally: true, assigned_participant_ids: [1, 2] })]} />);
    expect(screen.getByText('Shared')).toBeInTheDocument();
    expect(screen.queryByTitle('Bob')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Drop' })).not.toBeInTheDocument();
  });

  it('stages an owner assignment until confirmation and does not promote all-selected to global', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [
      { item_id: 1, participant_id: 1, portion_index: 0, expected_count: 1, is_assigned: true },
      { item_id: 1, participant_id: 2, portion_index: 0, expected_count: 1, is_assigned: true },
    ], []));
  });

  it('retains the explicit share-among-all action', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Share among all' }));
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [], [{ item_id: 1, is_shared_globally: true }]));
  });

  it('cancels without changing assignments and keeps drafts on API failure', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    expect(screen.getByRole('checkbox', { name: 'Bob' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    vi.mocked(assignBillItemsBatch).mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(showToast).toHaveBeenCalled());
    expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeChecked();
  });

  it('resets staged assignments without applying until confirm', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture({ portions: [[1]] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset selection' }));
    expect(screen.getByRole('checkbox', { name: 'Alice' })).not.toBeChecked();
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [{ item_id: 1, participant_id: 1, portion_index: 0, expected_count: 1, is_assigned: false }], []));
  });

  it('edits a line only as a whole and keeps deleting inside its edit form', () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture({ price: 500, count: 2, portions: [[], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pizza ×2' }));

    expect(screen.queryByRole('button', { name: 'Edit: Pizza' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument();
  });

  it('opens an edit as it is, with no field grabbing the keyboard', () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture()]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit: Pizza' }));

    expect(screen.getByRole('textbox', { name: 'Item Name' })).not.toHaveFocus();
    expect(document.activeElement?.tagName).not.toBe('INPUT');
  });

  it('puts the cursor in the name of a new line', () => {
    render(<ItemsSection {...props} isCreator isAdding onAddItem={vi.fn()} onStartAdd={vi.fn()} onCancelAdd={vi.fn()} items={[itemFixture()]} />);

    expect(screen.getByRole('textbox', { name: 'Item Name' })).toHaveFocus();
  });

  it('edits a single dish as a whole line too', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit: Pizza' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Item Name' }), { target: { value: 'Calzone' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateBillItem).toHaveBeenCalledWith(1, 1, { name: 'Calzone' }));
  });

  it('edits and deletes a whole line at once', async () => {
    const onBillUpdate = vi.fn();
    render(<ItemsSection {...props} isCreator onBillUpdate={onBillUpdate} items={[itemFixture({ price: 500, count: 2, portions: [[], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit: Pizza ×2' }));
    const price = screen.getByRole('textbox', { name: 'price/pc' });
    expect(price).toHaveValue('500');
    expect(screen.getByText(/Total: 1\s000/)).toBeInTheDocument();
    fireEvent.change(price, { target: { value: '600' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateBillItem).toHaveBeenCalledWith(1, 1, { price: 600 }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit: Pizza ×2' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Edit: Pizza ×2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Pizza ×2');
    expect(deleteBillItem).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteBillItem).toHaveBeenCalledWith(1, 1));
    await waitFor(() => expect(onBillUpdate).toHaveBeenCalledTimes(2));
    expect(getBill).toHaveBeenLastCalledWith(1, 10);
  });

  it('changes how many dishes a line has from its editor', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture({ price: 500, count: 2, portions: [[], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit: Pizza ×2' }));
    const quantity = within(screen.getByRole('group', { name: 'Qty' }));

    fireEvent.click(quantity.getByRole('button', { name: '+' }));
    expect(quantity.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/Total: 1\s500/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateBillItem).toHaveBeenCalledWith(1, 1, { count: 3 }));
  });

  it('renames a line without moving a total its rounded unit price cannot express', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture({ price: 33.33, count: 3, item_sum: 100, portions: [[], [], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit: Pizza ×3' }));
    expect(screen.getByText(/Total: 100\s/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Item Name' }), { target: { value: 'Samsa' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateBillItem).toHaveBeenCalledWith(1, 1, { name: 'Samsa' }));
  });

  it('assigns or shares a whole line from its row', async () => {
    render(<ItemsSection {...props} isCreator items={[itemFixture({ count: 2, portions: [[], []] })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Share among all' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledWith(1, 10, [], [{ item_id: 1, is_shared_globally: true }]));
  });

  it('locks a whole line while someone on any of its dishes has paid', () => {
    const participants = props.participants.map((p) => ({ ...p, is_paid: p.id === 2 }));
    render(<ItemsSection {...props} isCreator participants={participants} items={[itemFixture({ count: 2, portions: [[2], []] })]} />);
    expect(screen.getByRole('button', { name: 'Edit: Pizza ×2' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Assign' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Pizza ×2' }));
    expect(screen.getAllByRole('button', { name: 'Assign' }).map((button) => (button as HTMLButtonElement).disabled)).toEqual([true, false, true]);
  });

  it('adds an item with its quantity, with the add action after all positions', async () => {
    const onAddItem = vi.fn();
    const { rerender } = render(<ItemsSection {...props} isCreator items={[itemFixture()]} onStartAdd={vi.fn()} />);
    expect(screen.getByText('Pizza').compareDocumentPosition(screen.getByRole('button', { name: 'Add Item' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    rerender(<ItemsSection {...props} isCreator items={[]} isAdding onAddItem={onAddItem} />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Item Name' }), { target: { value: 'Tea' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Price' }), { target: { value: '25+5' } });
    fireEvent.click(within(screen.getByRole('group', { name: 'Qty' })).getByRole('button', { name: '+' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onAddItem).toHaveBeenCalledWith('Tea', 30, 2));
  });

  it('shows dishes still to hand out first and paid ones last', () => {
    const participants = billFixture().participants.map((p) => ({ ...p, is_paid: p.id === 2 }));
    const items = [
      itemFixture({ id: 1, name: 'Soup', portions: [[2]] }),
      itemFixture({ id: 2, name: 'Tea', portions: [[1]] }),
      itemFixture({ id: 3, name: 'Bread', portions: [[]] }),
    ];
    const order = () => [...document.querySelectorAll('[data-position-key]')].map((row) => row.textContent?.match(/Soup|Tea|Bread/)?.[0]);

    const { rerender } = render(<ItemsSection {...props} participants={participants} ownerId={99} items={items} />);
    expect(order()).toEqual(['Bread', 'Tea', 'Soup']);

    rerender(<ItemsSection {...props} participants={participants} ownerId={99} items={items} requiresRecalculation />);
    expect(order()).toEqual(['Soup', 'Tea', 'Bread']);
  });

  it('keeps multi-receipt headings and orphan/manual positions visible', () => {
    const receipts = [1, 2].map((n) => ({ task_id: n, index: n, merchant_name: `Cafe ${n}`, items_count: 1 } as Receipt));
    render(<ItemsSection {...props} receipts={receipts} items={[itemFixture({ receipt_task_id: 1 }), itemFixture({ id: 2, receipt_task_id: 2 }), itemFixture({ id: 3, name: 'Tea', receipt_task_id: 99 })]} />);
    expect(screen.getByText('1. Cafe 1')).toBeInTheDocument();
    expect(screen.getByText('2. Cafe 2')).toBeInTheDocument();
    expect(screen.getByText('No receipt')).toBeInTheDocument();
    expect(screen.getByText('Tea')).toBeInTheDocument();
  });

  it('does not let a guest silently replace a manual split by taking an item', () => {
    render(<ItemsSection {...props} requiresRecalculation items={[itemFixture()]} />);
    expect(screen.queryByRole('button', { name: 'Take' })).not.toBeInTheDocument();
  });

  it('warns the owner before replacing a manual split with item assignments', async () => {
    render(<ItemsSection {...props} isCreator requiresRecalculation items={[itemFixture()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    expect(screen.getByRole('note')).toHaveTextContent('replace the current split');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }));
    expect(assignBillItemsBatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Recalculate and assign' }));
    await waitFor(() => expect(assignBillItemsBatch).toHaveBeenCalledTimes(1));
  });
});

describe('picking several dishes', () => {
  function Picking(overrides: Partial<ComponentProps<typeof ItemsSection>>) {
    const selection = useDishSelection();
    return (
      <>
        <ItemsSection {...props} isCreator items={[pizzas, tea]} selection={selection} {...overrides} />
        <output data-testid="picked">{[...selection.keys].join(' ')}</output>
      </>
    );
  }
  const pizzas = itemFixture({ count: 2, item_sum: 2000, portions: [[], []] });
  const tea = itemFixture({ id: 2, name: 'Tea', item_sum: 500 });
  const picked = () => screen.getByTestId('picked').textContent;
  const startPicking = () => fireEvent.click(screen.getByRole('button', { name: 'Select several' }));

  it('is offered to the owner once the receipt has more than one dish', () => {
    const { unmount } = render(<Picking items={[tea]} />);
    expect(screen.queryByRole('button', { name: 'Select several' })).not.toBeInTheDocument();
    unmount();

    render(<Picking />);
    expect(screen.getByRole('button', { name: 'Select several' })).toBeInTheDocument();
  });

  it('turns the rows into round ticks and puts their actions and the add button aside', () => {
    render(<Picking onStartAdd={vi.fn()} />);
    startPicking();

    expect(screen.getByRole('checkbox', { name: 'Pizza ×2' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Tea' })).not.toBeChecked();
    expect(screen.queryByRole('button', { name: 'Assign' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit: Pizza ×2' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add Item' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Add Item' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Tea' })).not.toBeInTheDocument();
  });

  it('picks every dish of a folded line with one tap', () => {
    render(<Picking />);
    startPicking();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Pizza ×2' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tea' }));

    expect(picked()).toBe('1:0 1:1 2:0');
    expect(screen.getByRole('checkbox', { name: 'Pizza ×2' })).toBeChecked();
  });

  it('opens a line by its chevron only, and picks its dishes one by one', () => {
    render(<Picking />);
    startPicking();

    fireEvent.click(screen.getByRole('button', { name: 'Show dishes: Pizza ×2' }));
    expect(picked()).toBe('');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Pizza · 2 of 2' }));

    expect(picked()).toBe('1:1');
    expect(screen.getByRole('checkbox', { name: 'Pizza ×2' })).toBePartiallyChecked();
    expect(screen.getByRole('checkbox', { name: 'Pizza · 1 of 2' }).closest('li')).not.toHaveClass('bg-accent-weak');
    expect(screen.getByRole('checkbox', { name: 'Pizza · 2 of 2' }).closest('li')).toHaveClass('bg-accent-weak');
  });

  it('leaves a dish someone has paid for out of the pick', () => {
    const participants = props.participants.map((p) => ({ ...p, is_paid: p.id === 2 }));
    render(<Picking participants={participants} items={[itemFixture({ count: 2, item_sum: 2000, portions: [[2], []] }), tea]} />);
    startPicking();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Pizza ×2' }));
    expect(picked()).toBe('1:1');
    expect(screen.getByRole('checkbox', { name: 'Pizza ×2' })).toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: 'Show dishes: Pizza ×2' }));
    expect(screen.getByRole('checkbox', { name: 'Pizza · 1 of 2' })).toBeDisabled();
  });
});
