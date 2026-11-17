import { describe, expect, it } from 'vitest';
import { billFixture, itemFixture, participantFixture } from '@/test/billFixtures';
import { billPositions, dealDishes, groupPositions, positionIsPaid, positionState, sortByState } from './billPositions';

describe('billPositions', () => {
  it('cuts a line in sums into whole-sum dishes', () => {
    const rows = billPositions([itemFixture({ count: 3, item_sum: 100000 })], [], 'uzs');
    expect(rows.map((p) => p.amount)).toEqual([33334, 33333, 33333]);
  });

  it('flattens quantity without losing exact cents or assignment coordinates', () => {
    const bill = billFixture({ items: [itemFixture({ count: 3, item_sum: 10, portions: [[1], [2], []] })] });
    const positions = billPositions(bill.items, bill.participants, 'usd');
    expect(positions.map((p) => [p.key, p.amount, p.participantIds])).toEqual([
      ['1:0', 3.34, [1]], ['1:1', 3.33, [2]], ['1:2', 3.33, []],
    ]);
  });

  it('uses Python-style floor remainder for negative discount lines too', () => {
    const rows = billPositions([itemFixture({ count: 3, item_sum: -10 })], [], 'usd');
    expect(rows.map((p) => p.amount)).toEqual([-3.33, -3.33, -3.34]);
  });

  it('shows payment only when every assignee is paid', () => {
    const bill = billFixture({ items: [itemFixture({ portions: [[1, 2]] })] });
    const position = billPositions(bill.items, bill.participants, bill.currency)[0];
    expect(positionIsPaid(position, bill.participants)).toBe(false);
    expect(positionIsPaid(position, bill.participants.map((p) => ({ ...p, is_paid: p.id === 1 })))).toBe(false);
    expect(positionIsPaid(position, bill.participants.map((p) => ({ ...p, is_paid: true })))).toBe(true);
    expect(positionIsPaid({ ...position, participantIds: [] }, bill.participants)).toBe(false);
  });

  it('tells open, taken and settled dishes apart', () => {
    const bill = billFixture({
      owner_id: 10,
      participants: billFixture().participants.map((p) => ({ ...p, is_paid: p.id === 2 })),
      items: [itemFixture({ count: 3, item_sum: 30, portions: [[], [1], [2]] })],
    });
    const [open, taken, settled] = billPositions(bill.items, bill.participants, bill.currency);
    expect(positionState(open, bill.participants, 10)).toBe('open');
    expect(positionState(taken, bill.participants, 10)).toBe('taken');
    expect(positionState(settled, bill.participants, 10)).toBe('settled');
  });

  it('keeps a dish only the creator has taken, not settled, even once they are marked paid', () => {
    const bill = billFixture({ owner_id: 10, items: [itemFixture({ portions: [[1]] })] });
    const [owners] = billPositions(bill.items, bill.participants, bill.currency);
    const closed = bill.participants.map((p) => ({ ...p, is_paid: p.user_id === 10 }));

    expect(positionIsPaid(owners, bill.participants, 10)).toBe(false);
    expect(positionIsPaid(owners, closed, 10)).toBe(false);
    expect(positionState(owners, closed, 10)).toBe('taken');
  });

  it('puts open dishes first and settled ones last without shuffling the rest', () => {
    const bill = billFixture({
      owner_id: 99,
      participants: billFixture().participants.map((p) => ({ ...p, is_paid: p.id === 1 })),
      items: [
        itemFixture({ id: 1, name: 'Paid', portions: [[1]] }),
        itemFixture({ id: 2, name: 'Taken A', portions: [[2]] }),
        itemFixture({ id: 3, name: 'Open A', portions: [[]] }),
        itemFixture({ id: 4, name: 'Taken B', portions: [[2]] }),
        itemFixture({ id: 5, name: 'Open B', portions: [[]] }),
      ],
    });
    const sorted = sortByState(billPositions(bill.items, bill.participants, bill.currency), bill.participants, 99);
    expect(sorted.map((p) => p.item.name)).toEqual(['Open A', 'Open B', 'Taken A', 'Taken B', 'Paid']);
  });

  it('gathers dishes back into their line, each line where its first dish stands', () => {
    const bill = billFixture({
      owner_id: 99,
      items: [
        itemFixture({ id: 1, name: 'Samsa', count: 3, item_sum: 30, portions: [[1], [], [2]] }),
        itemFixture({ id: 2, name: 'Tea', portions: [[2]] }),
      ],
    });
    const groups = groupPositions(sortByState(billPositions(bill.items, bill.participants, bill.currency), bill.participants, 99));

    expect(groups.map((group) => [group.key, group.positions.map((p) => p.key), group.participantIds])).toEqual([
      ['1', ['1:1', '1:0', '1:2'], [1, 2]],
      ['2', ['2:0'], [2]],
    ]);
  });

  it('does not wait for the creator to pay themselves before showing a settled item', () => {
    const bill = billFixture({ items: [itemFixture({ portions: [[1, 2]] })] });
    const position = billPositions(bill.items, bill.participants, bill.currency)[0];
    expect(positionIsPaid(position, bill.participants, bill.owner_id)).toBe(false);
    expect(positionIsPaid(position, bill.participants.map((p) => ({ ...p, is_paid: p.id === 2 })), bill.owner_id)).toBe(true);
  });

  it('lets everyone keep the dishes they hold when dealing', () => {
    const dishes = billPositions([itemFixture({ count: 4, item_sum: 4000, portions: [[8], [7, 8], [], [7]] })], [
      participantFixture({ id: 7 }), participantFixture({ id: 8 }),
    ], 'uzs');
    expect(dealDishes(dishes, [7, 8])).toEqual(new Map([[0, [8]], [1, [7]], [2, [8]], [3, [7]]]));
  });

  it('deals dishes evenly in table order, or not at all', () => {
    const dishes = billPositions([itemFixture({ count: 4, item_sum: 4000 })], [], 'uzs');
    expect(dealDishes(dishes, [7, 8])).toEqual(new Map([[0, [7]], [1, [7]], [2, [8]], [3, [8]]]));
    expect(dealDishes(dishes.slice(0, 2), [5, 6, 7, 8])).toEqual(new Map([[0, [5, 6]], [1, [7, 8]]]));
    expect(dealDishes(dishes.slice(0, 3), [7, 8])).toBeNull();
    expect(dealDishes(dishes, [7])).toBeNull();
  });
});
