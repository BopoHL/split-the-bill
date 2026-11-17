import { describe, expect, it } from 'vitest';
import { clearSessionCaches, createSessionCache } from './sessionCache';

describe('session cache', () => {
  it('keeps the newest answers up to its limit and forgets the oldest', () => {
    const cache = createSessionCache<number>(2);
    cache.set('a', 1);
    cache.set('b', 2);
    cache.set('a', 3);
    cache.set('c', 4);

    expect(cache.entries()).toEqual([['a', 3], ['c', 4]]);
    expect(cache.get('b')).toBeUndefined();
  });

  it('changes every answer at once and is cleared with the rest', () => {
    const cache = createSessionCache<number>();
    cache.set('a', 1);
    cache.set('b', 2);
    cache.update((value) => value * 10);
    expect(cache.entries()).toEqual([['a', 10], ['b', 20]]);

    clearSessionCaches();
    expect(cache.entries()).toEqual([]);
  });
});
