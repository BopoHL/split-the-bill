import { describe, expect, it } from 'vitest';
import { fitFontSize } from './useFittedFontSize';

describe('fitFontSize', () => {
  it('keeps the largest size while the line fits', () => {
    expect(fitFontSize(180, 210, 20, 12)).toEqual({ size: 20, clipped: false });
  });

  it('shrinks a line that is too wide, in half pixels', () => {
    // 19 characters of a card number, 12px each at 20px, in 211px.
    expect(fitFontSize(228, 211, 20, 12)).toEqual({ size: 18.5, clipped: false });
  });

  it('stops at the smallest size and says the line is still cut off', () => {
    expect(fitFontSize(480, 211, 20, 12)).toEqual({ size: 12, clipped: true });
  });
});
