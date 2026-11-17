import { describe, it, expect } from 'vitest';
import { parseSoliqUrl, isSoliqUrl } from './soliq';

const VALID =
  'https://ofd.soliq.uz/check?t=LG420211643372&r=11975&c=20260619124101&s=133935061946';

describe('parseSoliqUrl', () => {
  it('accepts a valid check link unchanged', () => {
    expect(parseSoliqUrl(VALID)).toBe(VALID);
  });

  it('accepts an epi link and forces https', () => {
    const out = parseSoliqUrl('http://ofd.soliq.uz/epi?t=EZ1&r=1&c=20240101000000&s=9');
    expect(out).toBe('https://ofd.soliq.uz/epi?t=EZ1&r=1&c=20240101000000&s=9');
  });

  it('trims surrounding whitespace', () => {
    expect(parseSoliqUrl(`  ${VALID}  `)).toBe(VALID);
  });

  it.each([
    ['', 'empty'],
    ['just some text', 'not a url'],
    ['https://evil.com/check?t=1&r=1&c=1&s=1', 'wrong host'],
    ['https://ofd.soliq.uz.evil.com/check?t=1&r=1&c=1&s=1', 'look-alike host'],
    ['https://ofd.soliq.uz/check?t=1&r=1', 'missing params'],
    ['https://ofd.soliq.uz/other?t=1&r=1&c=1&s=1', 'wrong path'],
  ])('rejects %s (%s)', (bad) => {
    expect(parseSoliqUrl(bad)).toBeNull();
  });

  it('isSoliqUrl mirrors parse result', () => {
    expect(isSoliqUrl(VALID)).toBe(true);
    expect(isSoliqUrl('https://example.com')).toBe(false);
  });
});
