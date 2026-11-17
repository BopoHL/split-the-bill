import type { Bill } from '@/types/api';
import { DEFAULT_CURRENCY, formatCurrency, type Currency } from '@/lib/utils/currency';

export interface ActiveSections {
  /** Bills the person owns: they collect from the others. */
  collecting: Bill[];
  /** Bills they joined and have not said they paid. */
  owing: Bill[];
  /** Bills they joined and paid, open until the owner closes them. */
  settled: Bill[];
}

export function sortActive(bills: Bill[], userId: number): ActiveSections {
  const sections: ActiveSections = { collecting: [], owing: [], settled: [] };
  for (const bill of bills) {
    if (bill.owner_id === userId) sections.collecting.push(bill);
    else if (bill.my_seat?.is_paid) sections.settled.push(bill);
    else sections.owing.push(bill);
  }
  return sections;
}

export interface CurrencyTotal {
  currency: Currency;
  amount: number;
}

/** Amounts summed per currency, in the order the currencies first appear. */
export function totalsByCurrency(bills: Bill[], amountOf: (bill: Bill) => number): CurrencyTotal[] {
  const totals: CurrencyTotal[] = [];
  for (const bill of bills) {
    const currency = bill.currency ?? DEFAULT_CURRENCY;
    const total = totals.find((entry) => entry.currency === currency);
    if (total) total.amount += amountOf(bill);
    else totals.push({ currency, amount: amountOf(bill) });
  }
  return totals.filter((total) => total.amount > 0);
}

export function formatTotals(totals: CurrencyTotal[]): string {
  return totals.map((total) => formatCurrency(total.amount, total.currency)).join(' + ');
}

export interface MonthGroup {
  key: string;
  month: Date;
  bills: Bill[];
  /** Whether every bill of the month is here — the last one may still be paging in. */
  complete: boolean;
}

/** Bills, newest first, gathered under the month they were made in. */
export function groupByMonth(bills: Bill[], allLoaded: boolean): MonthGroup[] {
  const groups: MonthGroup[] = [];
  for (const bill of bills) {
    const created = new Date(bill.created_at);
    const key = `${created.getFullYear()}-${created.getMonth()}`;
    const last = groups[groups.length - 1];
    if (last?.key === key) last.bills.push(bill);
    else groups.push({ key, month: new Date(created.getFullYear(), created.getMonth(), 1), bills: [bill], complete: true });
  }
  if (!allLoaded && groups.length > 0) groups[groups.length - 1].complete = false;
  return groups;
}

const capitalized = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);

/** «Сентябрь», or «Сентябрь 2025» for a month of another year. */
export function monthLabel(month: Date, language: string, now: Date = new Date()): string {
  const name = capitalized(new Intl.DateTimeFormat(language, { month: 'long' }).format(month));
  return month.getFullYear() === now.getFullYear() ? name : `${name} ${month.getFullYear()}`;
}

/** The day and short month a bill was made on, for the archive's date column. */
export function dayAndMonth(createdAt: string, language: string): { day: string; month: string } {
  const created = new Date(createdAt);
  return {
    day: String(created.getDate()).padStart(2, '0'),
    month: new Intl.DateTimeFormat(language, { month: 'short' }).format(created).replace('.', ''),
  };
}
