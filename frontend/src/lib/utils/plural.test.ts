import { describe, expect, it } from 'vitest';
import { dishUnit } from './plural';

describe('dishUnit', () => {
  it('agrees with the count in Russian', () => {
    expect([1, 2, 5, 11, 21, 22, 25].map((n) => dishUnit(n, 'ru'))).toEqual(['блюдо', 'блюда', 'блюд', 'блюд', 'блюдо', 'блюда', 'блюд']);
  });

  it('counts dishes in English and Uzbek', () => {
    expect([dishUnit(1, 'en'), dishUnit(3, 'en'), dishUnit(3, 'uz')]).toEqual(['dish', 'dishes', 'ta taom']);
  });
});
