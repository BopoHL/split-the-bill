import { describe, expect, it } from 'vitest';
import { listedBillFixture } from '@/test/billFixtures';
import { dayAndMonth, groupByMonth, monthLabel, sortActive, totalsByCurrency } from './home';
import { billUnit } from './plural';

const ME = 10;

describe('sortActive', () => {
  it('puts my bills under collecting, unpaid joined ones under owing, paid ones under settled', () => {
    const mine = listedBillFixture({ id: 1, owner_id: ME });
    const owing = listedBillFixture({ id: 2, owner_id: 20, my_seat: { id: 5, amount: 42500, is_paid: false } });
    const settled = listedBillFixture({ id: 3, owner_id: 20, my_seat: { id: 6, amount: 38000, is_paid: true } });

    expect(sortActive([mine, owing, settled], ME)).toEqual({ collecting: [mine], owing: [owing], settled: [settled] });
  });
});

describe('totalsByCurrency', () => {
  it('sums per currency and leaves out what comes to nothing', () => {
    const bills = [
      listedBillFixture({ id: 1, total_sum: 100, currency: 'uzs' }),
      listedBillFixture({ id: 2, total_sum: 20, currency: 'usd' }),
      listedBillFixture({ id: 3, total_sum: 50, currency: 'uzs' }),
      listedBillFixture({ id: 4, total_sum: 0, currency: 'rub' }),
    ];

    expect(totalsByCurrency(bills, (bill) => bill.total_sum)).toEqual([
      { currency: 'uzs', amount: 150 },
      { currency: 'usd', amount: 20 },
    ]);
  });
});

describe('groupByMonth', () => {
  const bills = [
    listedBillFixture({ id: 1, created_at: '2026-09-28T12:00:00' }),
    listedBillFixture({ id: 2, created_at: '2026-09-06T12:00:00' }),
    listedBillFixture({ id: 3, created_at: '2026-08-30T12:00:00' }),
  ];

  it('gathers bills under their month, newest first', () => {
    const groups = groupByMonth(bills, true);

    expect(groups.map((group) => group.bills.map((bill) => bill.id))).toEqual([[1, 2], [3]]);
    expect(groups.every((group) => group.complete)).toBe(true);
  });

  it('marks the last month incomplete while more pages are coming', () => {
    const groups = groupByMonth(bills, false);

    expect(groups.map((group) => group.complete)).toEqual([true, false]);
  });
});

describe('labels', () => {
  const now = new Date('2026-10-02T12:00:00');

  it('names the month, with the year only when it is not this one', () => {
    expect(monthLabel(new Date(2026, 8, 1), 'ru', now)).toBe('Сентябрь');
    expect(monthLabel(new Date(2025, 11, 1), 'en', now)).toBe('December 2025');
  });

  it('gives the day and a short month without a dot', () => {
    expect(dayAndMonth('2026-09-06T12:00:00', 'ru')).toEqual({ day: '06', month: 'сент' });
  });

  it('counts bills in Russian', () => {
    expect([1, 3, 5, 11, 22].map((n) => billUnit(n, 'ru'))).toEqual(['счёт', 'счёта', 'счетов', 'счетов', 'счёта']);
  });
});
