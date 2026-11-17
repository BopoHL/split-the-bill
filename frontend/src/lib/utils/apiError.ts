type Translate = (key: string, params?: Record<string, string>) => string;

/** Map known backend `detail` strings to a localized message. */
const KEY_BY_DETAIL: Record<string, string> = {
  'Cannot confirm payment for zero or negative amount': 'errors.cannotConfirmZero',
  'Not authorized to change payment status': 'errors.notAuthorizedPayment',
  'Bill is closed': 'errors.billClosed',
  'Bill is not open': 'errors.actionNotAllowed',
  POSITION_STALE: 'errors.positionChanged',
  POSITION_OUT_OF_RANGE: 'errors.positionChanged',
  PAID_ALLOCATION_LOCKED: 'bill.paidPositionLocked',
  PAID_ASSIGNMENT_LOCKED: 'bill.paidPositionLocked',
  SPLIT_BY_HAND: 'bill.splitByHand',
  SHARED_POSITION_EDIT_UNSUPPORTED: 'bill.sharedPositionEditHint',
  'Action not allowed on this bill state': 'errors.actionNotAllowed',
  'Only owner can finalize the bill': 'errors.onlyOwnerClose',
  'Bill is full': 'errors.billFull',
  BILL_FULL: 'errors.billFull',
  SEATS_IN_USE: 'bill.seatsInUse',
  SEAT_TAKEN: 'bill.seatAlreadyTaken',
  OWNER_SEAT_FIXED: 'bill.ownerSeatFixed',
  SEAT_PAID: 'bill.seatPaidMove',
  BOT_BLOCKED: 'bill.assignUserUnreachable',
  ALREADY_IN_BILL: 'bill.assignUserAlreadyIn',
  'Participant not found for this bill': 'errors.participantNotFound',
  'Owner is not a participant in this bill': 'errors.ownerNotParticipant',
  'User not found': 'errors.userNotFound',
  PRO_REQUIRED: 'pro.required',
  SCAN_LIMIT: 'pro.scanLimit',
  VOICE_EMPTY: 'voice.empty',
  VOICE_FAILED: 'voice.failed',
  VOICE_FORMAT: 'voice.format',
  VOICE_TOO_LONG: 'voice.tooLong',
};

/**
 * Translate a backend error `detail` into the UI language. Handles the dynamic
 * "Amount exceeds…" message, maps the known fixed ones, and falls back to the
 * raw detail (or a generic error) for anything unrecognized.
 */
export function translateApiError(detail: unknown, t: Translate): string {
  if (!detail) return t('common.error');
  if (typeof detail === 'object') {
    const error = detail as { code?: unknown; message?: unknown };
    const key = typeof error.code === 'string' ? KEY_BY_DETAIL[error.code] : undefined;
    if (key) return t(key);
    return typeof error.message === 'string' ? translateApiError(error.message, t) : t('common.error');
  }
  if (typeof detail !== 'string') return t('common.error');
  const d = detail.trim();

  if (d.startsWith('Amount exceeds unallocated sum')) {
    const m = d.match(/Max available:\s*([\d.,\s]+)/i);
    return m ? t('errors.amountExceeds', { max: m[1].trim() }) : t('errors.amountExceedsNoMax');
  }

  const key = KEY_BY_DETAIL[d];
  return key ? t(key) : detail;
}
