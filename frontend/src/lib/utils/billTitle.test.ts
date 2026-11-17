import { describe, expect, it } from 'vitest';
import { buildDefaultBillTitle } from './billTitle';
import type { Bill } from '@/types/api';

// Identity translator that resolves the two placeholders we care about
// in this util, mirroring what the real `t()` does in production.
const fakeT = (path: string, params?: Record<string, string>) => {
  const tpl =
    path === 'bill.defaultTitle'
      ? 'Bill {date}'
      : path === 'bill.defaultTitleN'
        ? 'Bill {date} #{n}'
        : path;
  return tpl
    .replace('{date}', params?.date ?? '')
    .replace('{n}', params?.n ?? '');
};

const mkBill = (overrides: Partial<Bill> & Pick<Bill, 'created_at'>): Bill =>
  ({
    id: 0,
    owner_id: 1,
    total_sum: 0,
    title: null,
    payment_details: null,
    split_type: 'manual',
    status: 'open',
    unallocated_sum: 0,
    participants_count: 0,
    ...overrides,
  }) as Bill;

describe('buildDefaultBillTitle', () => {
  const NOW = new Date('2026-03-15T12:00:00Z');

  it('no bills today → no counter suffix', () => {
    const result = buildDefaultBillTitle([], 'en', fakeT, { now: NOW });
    expect(result).toMatch(/^Bill /);
    expect(result).not.toMatch(/#/);
  });

  it('one bill today → suffix is #2', () => {
    const bills = [mkBill({ created_at: '2026-03-15T08:00:00Z' })];
    expect(buildDefaultBillTitle(bills, 'en', fakeT, { now: NOW })).toMatch(/#2$/);
  });

  it('counts only same calendar day, ignoring yesterday', () => {
    const bills = [
      mkBill({ created_at: '2026-03-14T23:30:00Z' }), // yesterday
      mkBill({ created_at: '2026-03-15T01:00:00Z' }), // today
      mkBill({ created_at: '2026-03-15T11:00:00Z' }), // today
    ];
    expect(buildDefaultBillTitle(bills, 'en', fakeT, { now: NOW })).toMatch(/#3$/);
  });

  it("counts today's bills separately for each owner", () => {
    const bills = [
      mkBill({ owner_id: 1, created_at: '2026-03-15T08:00:00Z' }),
      mkBill({ owner_id: 2, created_at: '2026-03-15T09:00:00Z' }),
    ];

    expect(
      buildDefaultBillTitle(bills, 'en', fakeT, { ownerId: 1, now: NOW }),
    ).toMatch(/#2$/);
    expect(
      buildDefaultBillTitle(bills, 'en', fakeT, { ownerId: 2, now: NOW }),
    ).toMatch(/#2$/);
  });

  it('locale changes the date string but template stays', () => {
    const en = buildDefaultBillTitle([], 'en', fakeT, { now: NOW });
    const ru = buildDefaultBillTitle([], 'ru', fakeT, { now: NOW });
    // both start with "Bill " (fakeT mirrors the English template) and
    // differ in the date portion only
    expect(en.startsWith('Bill ')).toBe(true);
    expect(ru.startsWith('Bill ')).toBe(true);
    expect(en).not.toBe(ru);
  });
});
