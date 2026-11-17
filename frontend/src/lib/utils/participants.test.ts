import { describe, expect, it } from 'vitest';
import { BillStatus, SplitType } from '@/types/api';
import { billFixture, participantFixture } from '@/test/billFixtures';
import { canPickOwnItems, participantLabel, splitsByDishes } from './participants';

const t = (key: string, params?: Record<string, string>) =>
  key === 'bill.guestN' ? `Guest ${params?.n}` : key;

const seat = (over: Parameters<typeof participantLabel>[0]) => over;

describe('participantLabel', () => {
  it('uses the account name once a seat is claimed', () => {
    expect(
      participantLabel(
        seat({ user_id: 7, name: 'Leonid', surname: 'Petrov', username: 'lv', guest_name: null, seat_index: 0 }),
        t,
      ),
    ).toBe('Leonid');
  });

  it('falls back to the account surname when the first name is blank', () => {
    expect(
      participantLabel(
        seat({ user_id: 7, name: '   ', surname: 'Petrov', username: 'lv', guest_name: null, seat_index: 0 }),
        t,
      ),
    ).toBe('Petrov');
  });

  it('prefers the owner-given label for an unclaimed seat', () => {
    expect(
      participantLabel(
        seat({ user_id: null, name: null, surname: null, username: null, guest_name: 'Жена', seat_index: 2 }),
        t,
      ),
    ).toBe('Жена');
  });

  it('falls back to a numbered guest built from the seat position', () => {
    expect(
      participantLabel(
        seat({ user_id: null, name: null, surname: null, username: null, guest_name: null, seat_index: 3 }),
        t,
      ),
    ).toBe('Guest 3');
  });

  it('treats a blank label as no label at all', () => {
    expect(
      participantLabel(
        seat({ user_id: null, name: null, surname: null, username: null, guest_name: '   ', seat_index: 1 }),
        t,
      ),
    ).toBe('Guest 1');
  });
});

describe('splitsByDishes', () => {
  const unsplit = billFixture({ split_type: SplitType.MANUAL });

  it('holds for a bill split by dishes', () => {
    expect(splitsByDishes(billFixture())).toBe(true);
  });

  it('holds for a bill with dishes nobody has given a sum yet', () => {
    expect(splitsByDishes(unsplit)).toBe(true);
  });

  it('does not hold once someone has a sum by hand', () => {
    const [first, second] = unsplit.participants;
    expect(splitsByDishes({ ...unsplit, participants: [{ ...first, allocated_amount: 300 }, second] })).toBe(false);
  });

  it('does not hold for a bill without dishes', () => {
    expect(splitsByDishes({ ...unsplit, items: [] })).toBe(false);
  });
});

describe('canPickOwnItems', () => {
  const seat = participantFixture({ id: 2, user_id: 20 });

  it('lets a guest pick on an open bill split by dishes', () => {
    expect(canPickOwnItems(billFixture({ split_type: SplitType.MANUAL }), seat)).toBe(true);
  });

  it('stops once they have paid or the bill is closed', () => {
    expect(canPickOwnItems(billFixture(), { ...seat, is_paid: true })).toBe(false);
    expect(canPickOwnItems(billFixture({ status: BillStatus.CLOSED }), seat)).toBe(false);
  });
});
