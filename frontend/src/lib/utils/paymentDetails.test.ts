import { describe, expect, it } from 'vitest';
import { cardBrand, displayDetails, formatDetails, sameDetails } from './paymentDetails';

describe('payment details', () => {
  it('types a card number in groups of four and keeps a phone number’s plus', () => {
    expect(formatDetails('8600123456789012')).toBe('8600 1234 5678 9012');
    expect(formatDetails('8600 12a3-4')).toBe('8600 1234');
    expect(formatDetails('8600 1234 5678 9012 3456 78')).toBe('8600 1234 5678 9012 345');
    expect(formatDetails(' +998 90 123-45-67')).toBe('+998901234567');
    expect(formatDetails('')).toBe('');
  });

  it('tells the payment system from the first four digits', () => {
    expect(cardBrand('8600 1234')).toBe('UZCARD');
    expect(cardBrand('9860 0000 1111')).toBe('HUMO');
    expect(cardBrand('4169 5858')).toBe('VISA');
    expect(cardBrand('5425 2334')).toBe('MASTERCARD');
    expect(cardBrand('2201 0000')).toBe('MIR');
    expect(cardBrand('860')).toBeNull();
    expect(cardBrand('+998901234567')).toBeNull();
  });

  it('shows a saved card number in groups of four, and other details as they are', () => {
    expect(displayDetails('8600123456789012')).toBe('8600 1234 5678 9012');
    expect(displayDetails('+998901234567')).toBe('+998901234567');
    expect(displayDetails('1235')).toBe('1235');
  });

  it('matches details however they are spaced', () => {
    expect(sameDetails('8600 1234 5678 9012', '8600123456789012')).toBe(true);
    expect(sameDetails('8600 1234', '8600 1235')).toBe(false);
    expect(sameDetails('', '')).toBe(false);
  });
});
