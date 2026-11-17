import type { Analytics } from '@/types/analytics';

/** September 2026 as the analytics endpoint tells it. */
export const analyticsFixture = (overrides: Partial<Analytics> = {}): Analytics => ({
  period: { kind: 'month', year: 2026, month: 9, first_year: 2026, first_month: 8 },
  locked: false,
  currency: 'uzs',
  other_currency_bills: 0,
  overview: {
    bills: 3, owned: 1, joined: 2, spent: 145000, spent_change: 45, average_bill: 195000, average_share: 72500,
    biggest: { id: 1, title: 'Ужин', created_at: '2026-09-05T14:30:00Z', total: 300000, share: 100000, people: 3 },
    smallest: { id: 2, title: 'Кофе', created_at: '2026-09-20T10:00:00Z', total: 90000, share: 45000, people: 2 },
    collected: 120000, transferred: 45000,
    timeline: [
      { key: '2026-09-01', amount: 0, bills: 0 },
      { key: '2026-09-05', amount: 100000, bills: 1 },
      { key: '2026-09-20', amount: 45000, bills: 1 },
    ],
    weekdays: [0, 0, 0, 1, 0, 2, 1],
    day_parts: [0, 1, 2, 0],
  },
  people: {
    companions: [
      { user_id: 2, name: 'Alice', avatar_url: null, together: 2, invited: 1, invited_me: 1, paid_me: 120000, paid_them: 45000 },
      { user_id: 3, name: 'Bob', avatar_url: null, together: 1, invited: 1, invited_me: 0, paid_me: 0, paid_them: 0 },
    ],
    speed: [{ user_id: 2, name: 'Alice', minutes: 12, payments: 1 }],
    distinct: 2,
  },
  food: {
    groups: [{ group: 'food', amount: 77000 }, { group: 'drink', amount: 33000 }, { group: 'fee', amount: 10000 }],
    top: [{ kind: 'burger', name: 'Бургер', count: 2 }, { kind: 'cappuccino', name: 'Капучино', count: 2 }],
    champions: [{ kind: 'burger', name: 'Бургер', often: 'Burger Double', often_count: 1, priciest: 'Burger Black Angus', priciest_price: 54000 }],
    price_rises: [{ dish: 'Cappuccino', place: 'Caffeine', first_price: 30000, last_price: 36000, change: 20, since: '2026-09-05T14:30:00Z' }],
    fees: 10000,
    labeled: 1,
  },
  places: {
    top: [{ id: 1, name: 'Caffeine', visits: 2, spent: 145000, average_bill: 195000, last_visit: '2026-09-20T10:00:00Z' }],
    new: ['Caffeine'],
    unplaced: 0,
  },
  badges: [{ key: 'regular', value: 2, subject: 'Caffeine' }],
  ...overrides,
});
