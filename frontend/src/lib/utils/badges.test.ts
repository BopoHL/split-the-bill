import { describe, expect, it } from 'vitest';
import { shownBadge } from './badges';

describe('shownBadge', () => {
  it('shows Pro by itself, a picked title always, and nothing when asked', () => {
    expect(shownBadge(undefined, true)).toBe('pro');
    expect(shownBadge(undefined, false)).toBeNull();
    expect(shownBadge('pro', false)).toBeNull();
    expect(shownBadge('night_owl', false)).toBe('night_owl');
    expect(shownBadge('none', true)).toBeNull();
  });
});
