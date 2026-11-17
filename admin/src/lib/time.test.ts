/**
 * The point of these: the machine running the panel is on some other timezone,
 * and none of the answers below may move because of it.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { formatTashkent, parseUtc, tashkentToUtcIso } from './time';

describe('time', () => {
  const hostZone = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = 'America/New_York';
  });
  afterAll(() => {
    process.env.TZ = hostZone;
  });

  it('reads a wall clock as Tashkent, not as the browser locale', () => {
    expect(tashkentToUtcIso('2026-08-20T21:30')).toBe('2026-08-20T16:30:00.000Z');
  });

  it('treats a naive timestamp from the API as UTC', () => {
    expect(parseUtc('2026-08-20T16:30:00').toISOString()).toBe('2026-08-20T16:30:00.000Z');
    expect(parseUtc('2026-08-20T16:30:00Z').toISOString()).toBe('2026-08-20T16:30:00.000Z');
  });

  it('shows the hour back in Tashkent', () => {
    expect(formatTashkent('2026-08-20T16:30:00')).toContain('21:30');
  });

  it('survives a round trip', () => {
    const utc = tashkentToUtcIso('2026-01-05T09:05');
    expect(formatTashkent(utc)).toContain('09:05');
  });
});
