import { describe, expect, it } from 'vitest';
import { itemFixture, participantFixture } from '@/test/billFixtures';
import type { BillItem } from '@/types/api';
import { splitInSteps, tableSplit } from './itemSplit';

const OWNER_USER = 10;
const owner = participantFixture({ id: 1, user_id: OWNER_USER });
const guest = (id: number) => participantFixture({ id, user_id: null });
const table = [owner, guest(2), guest(3), guest(4), guest(5), guest(6)];

const sharesOf = (item: BillItem, currency: 'uzs' | 'usd' = 'uzs', participants = table) =>
  Object.fromEntries(tableSplit(participants, OWNER_USER, currency).splitItems([item]).get(item.id)!);

describe('splitInSteps', () => {
  it('cuts into whole steps, larger parts first, odd cents on the first', () => {
    expect(splitInSteps(10_000_000, 3, 100)).toEqual([3_333_400, 3_333_300, 3_333_300]);
    expect(splitInSteps(-1_234_560, 3, 100)).toEqual([-411_460, -411_500, -411_600]);
    expect(splitInSteps(10_000, 3, 1)).toEqual([3_334, 3_333, 3_333]);
  });
});

describe('tableSplit.splitItems', () => {
  it('splits dishes eaten by the same guests evenly and spares the owner', () => {
    const raketki = itemFixture({ count: 3, item_sum: 105000, portions: [[2, 3, 4], [2, 3, 4], [2, 3, 4]] });
    expect(sharesOf(raketki)).toEqual({ 2: 35000, 3: 35000, 4: 35000 });
  });

  it('keeps the rounding of each group of eaters to that group', () => {
    const shares = sharesOf(itemFixture({ count: 3, item_sum: 105000, portions: [[1, 2, 3], [4, 5, 6], [4, 5, 6]] }));
    expect(shares[1] + shares[2] + shares[3]).toBe(35000);
    expect(shares[4] + shares[5] + shares[6]).toBe(70000);
  });

  it('gives the larger whole sum to a guest on the dish, or to the owner when they share it', () => {
    expect(sharesOf(itemFixture({ item_sum: 100000, portions: [[2, 3, 4]] }))).toEqual({ 2: 33334, 3: 33333, 4: 33333 });
    expect(sharesOf(itemFixture({ item_sum: 100000, portions: [[2, 1, 3]] }))).toEqual({ 1: 33334, 2: 33333, 3: 33333 });
  });

  it('leaves odd tiyins with one eater', () => {
    expect(sharesOf(itemFixture({ item_sum: -12345.6, portions: [[2, 1, 3]] }))).toEqual({ 1: -4114.6, 2: -4115, 3: -4116 });
  });

  it('keeps cents in a currency that pays them', () => {
    expect(sharesOf(itemFixture({ item_sum: 100, portions: [[2, 3, 4]] }), 'usd')).toEqual({ 2: 33.34, 3: 33.33, 4: 33.33 });
  });

  it('shares a line among all over every seat', () => {
    expect(sharesOf(itemFixture({ count: 2, item_sum: 10000, is_shared_globally: true }), 'uzs', table.slice(0, 3)))
      .toEqual({ 1: 3334, 2: 3333, 3: 3333 });
  });
});

describe('tableSplit.splitItems across lines', () => {
  it('shares the same eaters once whatever lines their dishes are on, each line adding up', () => {
    const lines = [1, 2, 3].map((id) => itemFixture({ id, item_sum: 35000, portions: [[2, 3, 4]] }));
    const shares = tableSplit(table, OWNER_USER, 'uzs').splitItems(lines);

    const total = (seat: number) => lines.reduce((sum, line) => sum + shares.get(line.id)!.get(seat)!, 0);
    expect([total(2), total(3), total(4)]).toEqual([35000, 35000, 35000]);
    for (const line of lines) expect([...shares.get(line.id)!.values()].reduce((a, b) => a + b, 0)).toBe(35000);
  });
});

describe('golden cases shared with the server', () => {
  // The same cases are asserted in backend/tests/test_item_split.py.
  it('matches split_items', () => {
    expect(sharesOf(itemFixture({ count: 3, item_sum: 100000, portions: [[], [2], []] }))).toEqual({ 2: 33333 });
    expect(sharesOf(itemFixture({ count: 2, item_sum: 50000, portions: [[4, 5, 6], [2, 3, 1]] })))
      .toEqual({ 1: 8334, 2: 8333, 3: 8333, 4: 8334, 5: 8333, 6: 8333 });
  });
});
