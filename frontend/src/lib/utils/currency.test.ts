import { describe, it, expect, vi } from 'vitest';

// The currency label comes from the store; the formatting cases pin it to uzs
// (ru → «сум») so they test number formatting independent of the default.
vi.mock('@/lib/store/useStore', () => {
  const state: { language: string; currency?: string } = { language: 'ru', currency: 'uzs' };
  return { useStore: { getState: () => state } };
});

import { formatCurrency } from './currency';
import { CURRENCY_CODES, isCurrency, currencySymbolFor, tickerOf } from './currencyCatalog';
import { ORDERED_CURRENCIES } from '@/lib/utils/currencyCatalog';
import { useStore } from '@/lib/store/useStore';

const setCurrency = (c?: string) => {
  (useStore.getState() as { currency?: string }).currency = c;
};

describe('formatCurrency — rounding & formatting', () => {
  // The mock store has language 'ru', so UZS renders as «сум».
  it('trims binary-float tails to 2 decimals', () => {
    expect(formatCurrency(67199.97999999998)).toBe('67 199.98 сум');
  });

  it('drops a trailing .00 for whole amounts', () => {
    expect(formatCurrency(120000)).toBe('120 000 сум');
  });

  it('keeps a single significant decimal', () => {
    expect(formatCurrency(12.5)).toBe('12.5 сум');
  });

  it('rounds to 2 decimals', () => {
    expect(formatCurrency(12.345)).toBe('12.35 сум');
  });

  it('handles negatives (discounts) with thousands separators', () => {
    expect(formatCurrency(-67199.98)).toBe('-67 199.98 сум');
  });

  it('labels UZS per language but other currencies with a fixed symbol', () => {
    expect(formatCurrency(1000, 'uzs')).toBe('1 000 сум'); // ru
    expect(formatCurrency(1000, 'usd')).toBe('1 000 $');
    expect(formatCurrency(1000, 'rub')).toBe('1 000 руб');
    expect(formatCurrency(1000, 'byn')).toBe('1 000 Br');
    expect(formatCurrency(1000, 'kzt')).toBe('1 000 ₸');
    expect(formatCurrency(1000, 'eur')).toBe('1 000 €');
  });

  it('falls back to the store currency, then UZS when nothing is set', () => {
    setCurrency('usd');
    expect(formatCurrency(1000)).toBe('1 000 $');
    setCurrency('rub');
    expect(formatCurrency(1000)).toBe('1 000 руб');
    // No currency anywhere → UZS is the default.
    setCurrency(undefined);
    expect(formatCurrency(1000)).toBe('1 000 сум');
  });
});

describe('currency catalog — BYN', () => {
  it('is part of the catalog and validates', () => {
    expect(CURRENCY_CODES).toContain('byn');
    expect(isCurrency('byn')).toBe(true);
  });

  it('uses the Br symbol and BYN ticker', () => {
    expect(currencySymbolFor('byn')).toBe('Br');
    expect(tickerOf('byn')).toBe('BYN');
  });
});

describe('currency picker order', () => {
  it('puts BYN third, after сум (UZS) and RUB', () => {
    const codes = ORDERED_CURRENCIES.map((c) => c.code);
    expect(codes.slice(0, 3)).toEqual(['uzs', 'rub', 'byn']);
  });
});
