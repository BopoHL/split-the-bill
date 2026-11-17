import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SplitType } from '@/types/api';
import { billFixture, itemFixture, participantFixture } from '@/test/billFixtures';
import ParticipantPositions from './ParticipantPositions';

vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector?: (state: { language: string }) => unknown) =>
    selector ? selector({ language: 'en' }) : { language: 'en' },
}));

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        'bill.items': 'Items',
      })[key] ?? key,
  }),
}));

const alice = participantFixture({ id: 1, allocated_amount: 1000 });
const bob = participantFixture({ id: 2, user_id: 20, name: 'Bob', allocated_amount: 0 });

describe('ParticipantPositions', () => {
  it('lists each dish with the participant’s own share of it', () => {
    const bill = billFixture({
      participants: [alice, { ...bob, allocated_amount: 500 }],
      items: [itemFixture({ name: 'Pizza', item_sum: 1000, portions: [[1, 2]], assigned_participant_ids: [1, 2] })],
    });

    render(<ParticipantPositions bill={bill} participant={bill.participants[1]} />);

    const line = screen.getByRole('listitem');
    expect(within(line).getByText('Pizza')).toBeInTheDocument();
    expect(within(line).getByText(/500/)).toBeInTheDocument();
  });

  it('folds several portions of one dish into a single ×N line', () => {
    const bill = billFixture({
      participants: [{ ...alice, allocated_amount: 3000 }, bob],
      items: [itemFixture({ name: 'Samsa', price: 1000, count: 3, item_sum: 3000, portions: [[1], [1], [1]], assigned_participant_ids: [1] })],
    });

    render(<ParticipantPositions bill={bill} participant={bill.participants[0]} />);

    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('×3')).toBeInTheDocument();
    expect(screen.getByText(/3[\s ]000/)).toBeInTheDocument();
  });

  it('counts the dishes they are on, shared ones whole, and not the table\'s shared lines', () => {
    const carol = participantFixture({ id: 3, user_id: 30, name: 'Carol', allocated_amount: 1000 });
    const bill = billFixture({
      participants: [{ ...alice, allocated_amount: 1500 }, { ...bob, allocated_amount: 1500 }, carol],
      items: [
        itemFixture({ id: 1, name: 'Beer', price: 1000, count: 3, item_sum: 3000, portions: [[1], [1], [2]], assigned_participant_ids: [1, 2] }),
        itemFixture({ id: 2, name: 'Pizza', price: 1000, count: 1, item_sum: 1000, portions: [[1, 2]], assigned_participant_ids: [1, 2] }),
        itemFixture({ id: 3, name: 'Bread', price: 1000, count: 2, item_sum: 2000, is_shared_globally: true }),
      ],
    });

    render(<ParticipantPositions bill={bill} participant={bill.participants[0]} />);

    const [beer, pizza, bread] = screen.getAllByRole('listitem');
    expect(within(beer).getByText('×2')).toBeInTheDocument();
    expect(within(pizza).queryByText(/×/)).not.toBeInTheDocument();
    expect(within(pizza).getByText(/500/)).toBeInTheDocument();
    expect(within(bread).queryByText(/×/)).not.toBeInTheDocument();
  });

  it('stays quiet when nothing is assigned and for a manual share', () => {
    const empty = billFixture({ participants: [alice, bob], items: [] });
    const { container: nothing, unmount } = render(<ParticipantPositions bill={empty} participant={bob} />);
    expect(nothing).toBeEmptyDOMElement();
    unmount();

    const manual = billFixture({
      split_type: SplitType.MANUAL,
      participants: [alice, bob],
      items: [itemFixture({ portions: [[1]], assigned_participant_ids: [1] })],
    });
    const { container } = render(<ParticipantPositions bill={manual} participant={alice} />);
    expect(container).toBeEmptyDOMElement();
  });
});
