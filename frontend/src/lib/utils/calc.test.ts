import { describe, it, expect } from 'vitest';
import {
  evaluate,
  formatExpression,
  formatResult,
  hasBinaryOperator,
  collapseExpression,
} from './calc';

describe('evaluate', () => {
  it('applies × ÷ before + −', () => {
    expect(evaluate('2+3*4')).toBe(14);
    expect(evaluate('2+3×4')).toBe(14);
  });

  it('goes left to right within a precedence level', () => {
    expect(evaluate('10-3-2')).toBe(5);
    expect(evaluate('100/2/5')).toBe(10);
  });

  it('handles decimals and rounds to 2 places', () => {
    expect(evaluate('5000.5+0.5')).toBe(5001);
    expect(evaluate('0.1+0.2')).toBe(0.3);
  });

  it('supports a leading minus (discount)', () => {
    expect(evaluate('-5000')).toBe(-5000);
    expect(evaluate('-5000×2')).toBe(-10000);
  });

  it('subtracts to a negative result', () => {
    expect(evaluate('3000-5000')).toBe(-2000);
  });

  it('normalizes glyphs and decimal comma', () => {
    expect(evaluate('1500×3')).toBe(4500);
    expect(evaluate('1000÷4')).toBe(250);
    expect(evaluate('5000,5')).toBe(5000.5);
  });

  it('ignores a trailing operator for live preview', () => {
    expect(evaluate('52000+')).toBe(52000);
    expect(evaluate('52000+3000×')).toBe(55000);
  });

  it('returns null for empty, lone-sign or div-by-zero input', () => {
    expect(evaluate('')).toBeNull();
    expect(evaluate('-')).toBeNull();
    expect(evaluate('1000/0')).toBeNull();
  });
});

describe('formatExpression', () => {
  it('groups numbers and spaces glyph operators', () => {
    expect(formatExpression('52000+3000')).toBe('52 000 + 3 000');
    expect(formatExpression('1500*3')).toBe('1 500 × 3');
  });

  it('keeps a leading minus attached to the number', () => {
    expect(formatExpression('-5000')).toBe('−5 000');
  });

  it('preserves a trailing dot while typing decimals', () => {
    expect(formatExpression('5000.')).toBe('5 000.');
  });
});

describe('hasBinaryOperator', () => {
  it('is false for a plain or negative number', () => {
    expect(hasBinaryOperator('52000')).toBe(false);
    expect(hasBinaryOperator('-5000')).toBe(false);
  });

  it('is true once a binary operator is present', () => {
    expect(hasBinaryOperator('52000+')).toBe(true);
    expect(hasBinaryOperator('5000-2000')).toBe(true);
  });
});

describe('formatResult', () => {
  it('groups thousands, signs negatives and drops trailing zeros', () => {
    expect(formatResult(55000)).toBe('55 000');
    expect(formatResult(-5000)).toBe('−5 000');
    expect(formatResult(5000.5)).toBe('5 000.5');
  });
});

describe('collapseExpression', () => {
  it('reduces to a parseable plain numeric string', () => {
    expect(collapseExpression('52000+3000')).toBe('55000');
    expect(collapseExpression('-5000')).toBe('-5000');
    expect(collapseExpression('')).toBe('');
  });
});
