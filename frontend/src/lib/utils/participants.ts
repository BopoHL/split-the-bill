import { BillDetail, BillParticipant, BillStatus, SplitType } from '@/types/api';

/** Whether the bill is shared out by dishes. A bill with dishes that nobody
 *  has given a sum by hand yet counts too: the first dish taken makes it one. */
export function splitsByDishes(bill: BillDetail): boolean {
  return bill.split_type === SplitType.BY_ITEMS
    || (bill.items.length > 0 && bill.participants.every((p) => p.allocated_amount === 0));
}

/** Whether someone may tick their own dishes on this bill: it is open, split
 *  by what each ate, and they have not paid yet. */
export function canPickOwnItems(bill: BillDetail, seat: BillParticipant): boolean {
  return bill.status === BillStatus.OPEN && splitsByDishes(bill) && !seat.is_paid;
}

/**
 * Order participants so the current user's own card comes first.
 * Stable for everyone else (preserves the original order).
 */
export function sortParticipantsSelfFirst(
  participants: BillParticipant[],
  userId?: number,
): BillParticipant[] {
  if (!userId) return participants;
  return [...participants].sort((a, b) => {
    if (a.user_id === userId) return -1;
    if (b.user_id === userId) return 1;
    return 0;
  });
}

/**
 * What to call a seat.
 *
 * A claimed seat shows the person's Telegram name. An unclaimed one shows the
 * owner's label if they gave it one, and otherwise a «Guest N» built from the
 * seat position — the default is generated here rather than stored, so it
 * follows the reader's language instead of the language of whoever created the
 * bill.
 */
export function participantLabel(
  p: Pick<BillParticipant, 'name' | 'surname' | 'username' | 'guest_name' | 'seat_index' | 'user_id'>,
  t: (key: string, params?: Record<string, string>) => string,
): string {
  if (p.user_id) return p.name?.trim() || p.surname?.trim() || p.username || `#${p.user_id}`;
  if (p.guest_name?.trim()) return p.guest_name;
  return t('bill.guestN', { n: String(p.seat_index) });
}

/**
 * First letter for an avatar placeholder. Shares the label logic so a guest's
 * initial matches the name shown next to it.
 */
export function participantInitial(
  p: Parameters<typeof participantLabel>[0],
  t: (key: string, params?: Record<string, string>) => string,
): string {
  return participantLabel(p, t).charAt(0).toUpperCase() || 'U';
}
