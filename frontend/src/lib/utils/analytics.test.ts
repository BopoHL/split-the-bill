import { describe, expect, it } from 'vitest';
import {
  canShift, cumulative, currentPeriod, downloadAddress, peak, periodLabel, shiftPeriod, timelineTick, weekdayNames,
} from './analytics';

const NOW = new Date(2026, 9, 3);
const t = (path: string) => (path === 'analytics.allTime' ? 'All time' : path);

describe('periods', () => {
  it('starts at the month or year we are in', () => {
    expect(currentPeriod('month', NOW)).toEqual({ kind: 'month', year: 2026, month: 10 });
    expect(currentPeriod('year', NOW)).toEqual({ kind: 'year', year: 2026 });
    expect(currentPeriod('all', NOW)).toEqual({ kind: 'all' });
  });

  it('steps over the turn of a year', () => {
    expect(shiftPeriod({ kind: 'month', year: 2026, month: 1 }, -1)).toEqual({ kind: 'month', year: 2025, month: 12 });
    expect(shiftPeriod({ kind: 'month', year: 2025, month: 12 }, 1)).toEqual({ kind: 'month', year: 2026, month: 1 });
    expect(shiftPeriod({ kind: 'year', year: 2026 }, -1)).toEqual({ kind: 'year', year: 2025 });
  });

  it('goes back no further than the first bill and forward no further than today', () => {
    const known = { first_year: 2026, first_month: 8 };
    expect(canShift({ kind: 'month', year: 2026, month: 9 }, -1, known, NOW)).toBe(true);
    expect(canShift({ kind: 'month', year: 2026, month: 8 }, -1, known, NOW)).toBe(false);
    expect(canShift({ kind: 'month', year: 2026, month: 10 }, 1, known, NOW)).toBe(false);
    expect(canShift({ kind: 'month', year: 2026, month: 9 }, 1, known, NOW)).toBe(true);
    expect(canShift({ kind: 'year', year: 2026 }, -1, known, NOW)).toBe(false);
    expect(canShift({ kind: 'all' }, -1, known, NOW)).toBe(false);
  });

  it('names a period briefly', () => {
    expect(periodLabel({ kind: 'month', year: 2026, month: 9 }, 'en', t)).toBe('Sep 2026');
    expect(periodLabel({ kind: 'year', year: 2026 }, 'en', t)).toBe('2026');
    expect(periodLabel({ kind: 'all' }, 'en', t)).toBe('All time');
  });
});

describe('charts', () => {
  it('runs a total along the timeline', () => {
    expect(cumulative([{ key: 'a', amount: 10, bills: 1 }, { key: 'b', amount: 0, bills: 0 }, { key: 'c', amount: 5, bills: 1 }])).toEqual([10, 10, 15]);
  });

  it('ticks days by number and months by short name', () => {
    expect(timelineTick('2026-09-14', 'en')).toBe('14');
    expect(timelineTick('2026-09', 'en')).toBe('Sep');
    expect(timelineTick('2026-09', 'ru')).toBe('сент');
  });

  it('names weekdays from Monday and finds the busiest', () => {
    expect(weekdayNames('en', 'short')[0]).toBe('Mon');
    expect(peak([1, 0, 3, 3])).toBe(2);
  });
});

describe('pictures', () => {
  it('asks for a signed picture as a file, keeping its signature', () => {
    expect(downloadAddress('https://x.test/api/public/analytics/1/receipt.jpg?period=year&sig=abc')).toBe(
      'https://x.test/api/public/analytics/1/receipt.jpg?period=year&sig=abc&download=true',
    );
  });
});
