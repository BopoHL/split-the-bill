import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { billFixture, participantFixture } from '@/test/billFixtures';
import ParticipantList from './ParticipantList';

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({ 'bill.participants': 'Participants', 'bill.paidProgress': 'Paid' })[key] ?? key,
  }),
}));

const owner = participantFixture({ id: 1, user_id: 10, name: 'Owner', allocated_amount: 300 });
const bob = participantFixture({ id: 2, user_id: 20, name: 'Bob', allocated_amount: 400, is_paid: true });
const carol = participantFixture({ id: 3, user_id: 30, name: 'Carol', allocated_amount: 500 });
const emptySeat = participantFixture({
  id: 4, user_id: null, name: null, is_guest: true, seat_index: 4, allocated_amount: 0,
});
const bill = billFixture({ owner_id: 10, expected_people: 4, participants: [owner, bob, carol] });

const rowNames = () => screen.getAllByRole('listitem').map((row) => row.textContent);

describe('ParticipantList', () => {
  it('puts the viewer first, parted from the rest like any other seat', () => {
    render(<ParticipantList bill={bill} currentUserId={30} renderRow={(p) => p.name} />);

    expect(rowNames()).toEqual(['Carol', 'Owner', 'Bob']);
    expect(screen.getAllByRole('listitem', { hidden: true })).toHaveLength(3);
  });

  it('keeps the original order for someone who is not seated', () => {
    render(<ParticipantList bill={bill} currentUserId={99} renderRow={(p) => p.name} />);

    expect(rowNames()).toEqual(['Owner', 'Bob', 'Carol']);
  });

  it('counts payments over every seat but the owner\'s, empty ones included', () => {
    const seated = billFixture({ ...bill, participants: [owner, bob, carol, emptySeat] });
    render(<ParticipantList bill={seated} currentUserId={10} renderRow={(p) => p.name} />);

    expect(screen.getByTestId('paid-progress')).toHaveTextContent('Paid 1/3');
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('lets the caller replace the headcount and add a footer', () => {
    render(
      <ParticipantList bill={bill} currentUserId={10} headcount={<span>editor</span>} renderRow={(p) => p.name}>
        <p>Footer</p>
      </ParticipantList>,
    );

    expect(screen.getByText('editor')).toBeInTheDocument();
    expect(screen.queryByText('3')).toBeNull();
    expect(screen.getByText('Footer')).toBeInTheDocument();
    expect(within(screen.getByRole('list')).queryByText('Footer')).toBeNull();
  });
});
