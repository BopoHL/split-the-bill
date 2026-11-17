import { describe, it, expect } from 'vitest';
import { translateApiError } from './apiError';

// Stub translator: echoes the key and interpolates {max}.
const t = (key: string, params?: Record<string, string>) =>
  params ? `${key}:${params.max}` : key;

describe('translateApiError', () => {
  it('falls back to a generic error when detail is empty', () => {
    expect(translateApiError(undefined, t)).toBe('common.error');
  });

  it('maps the dynamic «amount exceeds» message and extracts the max', () => {
    expect(
      translateApiError('Amount exceeds unallocated sum. Max available: 50000', t),
    ).toBe('errors.amountExceeds:50000');
  });

  it('maps known fixed messages', () => {
    expect(translateApiError('Bill is closed', t)).toBe('errors.billClosed');
    expect(translateApiError('Cannot confirm payment for zero or negative amount', t)).toBe(
      'errors.cannotConfirmZero',
    );
  });

  it('passes through an unknown detail unchanged', () => {
    expect(translateApiError('Some new server error', t)).toBe('Some new server error');
  });

  it('handles structured position errors and validation lists without throwing', () => {
    expect(translateApiError({ code: 'POSITION_STALE', actual_count: 2 }, t)).toBe('errors.positionChanged');
    expect(translateApiError({ code: 'PAID_ALLOCATION_LOCKED', participant_ids: [1] }, t)).toBe('bill.paidPositionLocked');
    expect(translateApiError([{ msg: 'Invalid value' }], t)).toBe('common.error');
  });
});
