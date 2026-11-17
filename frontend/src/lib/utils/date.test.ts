import { describe, expect, it } from 'vitest';
import { formatRelativeDate } from './date';

const fakeT = (path: string, params?: Record<string, string>) => {
  if (path === 'date.today') return 'today';
  if (path === 'date.yesterday') return 'yesterday';
  if (path === 'date.daysAgo') return `${params?.count} days ago`;
  return path;
};

describe('formatRelativeDate', () => {
  const NOW = new Date('2026-03-15T12:00:00Z');

  it('returns "today" for same calendar day, even with a few hours diff', () => {
    expect(formatRelativeDate('2026-03-15T01:00:00Z', 'en', fakeT, NOW)).toBe(
      'today',
    );
    expect(formatRelativeDate('2026-03-15T23:30:00Z', 'en', fakeT, NOW)).toBe(
      'today',
    );
  });

  it('returns "yesterday" exactly one calendar day earlier', () => {
    expect(formatRelativeDate('2026-03-14T01:00:00Z', 'en', fakeT, NOW)).toBe(
      'yesterday',
    );
  });

  it('returns "N days ago" for 2..6 day diff', () => {
    expect(formatRelativeDate('2026-03-13T12:00:00Z', 'en', fakeT, NOW)).toBe(
      '2 days ago',
    );
    expect(formatRelativeDate('2026-03-09T12:00:00Z', 'en', fakeT, NOW)).toBe(
      '6 days ago',
    );
  });

  it('falls back to absolute date past one week', () => {
    const result = formatRelativeDate('2026-03-01T12:00:00Z', 'en', fakeT, NOW);
    expect(result).not.toMatch(/days ago/);
    expect(result).not.toBe('today');
    expect(result).toMatch(/Mar/);
  });

  it('includes year when out of the current calendar year', () => {
    const result = formatRelativeDate('2024-12-01T12:00:00Z', 'en', fakeT, NOW);
    expect(result).toMatch(/2024/);
  });

  it('returns empty string for invalid dates', () => {
    expect(formatRelativeDate('not a date', 'en', fakeT, NOW)).toBe('');
  });
});
