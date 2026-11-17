import { BillStatus, type BillDetail, type BillParticipant, type ParticipantReminder, type WhyNobody } from '@/types/api';

type Translate = (path: string, params?: Record<string, string>) => string;

/** Where a seat stands with the owner's reminders, right now. */
export type ReminderState =
  | { kind: 'ready'; lastFailed: boolean }
  | { kind: 'sending' }
  | { kind: 'reminded'; at: Date; nextAt: Date }
  | { kind: 'unreachable'; nextAt: Date };

/** Someone who joined, owes, and has not said they paid. */
export function canBeReminded(bill: BillDetail, participant: BillParticipant): boolean {
  return bill.status === BillStatus.OPEN
    && !participant.is_guest
    && participant.user_id !== bill.owner_id
    && !participant.is_paid
    && participant.allocated_amount > 0;
}

/** For a bill with nobody to remind and nobody to wait for: the step that
 *  would bring somebody — asked in the order the server asks it of all the
 *  owner's bills. */
export function whyNobody(bill: BillDetail): Exclude<WhyNobody, 'no_bills'> {
  const others = bill.participants.filter((participant) => participant.user_id !== bill.owner_id);
  if (others.length === 0) return 'no_people';
  const unpaid = others.filter((participant) => !participant.is_paid);
  if (unpaid.some((participant) => !participant.is_guest && participant.allocated_amount <= 0)) return 'unassigned';
  if (unpaid.some((participant) => participant.is_guest && participant.allocated_amount > 0)) return 'guests';
  return unpaid.length > 0 ? 'unassigned' : 'all_paid';
}

export function reminderState(reminder: ParticipantReminder | null | undefined, now: Date): ReminderState {
  if (!reminder) return { kind: 'ready', lastFailed: false };
  const nextAt = reminder.next_at ? new Date(reminder.next_at) : null;
  if (!nextAt || nextAt <= now) {
    return { kind: 'ready', lastFailed: reminder.status === 'failed' && reminder.failure !== 'settled' };
  }
  if (reminder.status === 'pending') return { kind: 'sending' };
  if (reminder.status === 'failed') return { kind: 'unreachable', nextAt };
  return { kind: 'reminded', at: new Date(reminder.at), nextAt };
}

/** «5 min», «2 h»: how long, in the largest unit that is not zero. */
export function shortDuration(ms: number, t: Translate): string {
  const minutes = Math.max(1, Math.round(ms / 60_000));
  if (minutes < 60) return t('bill.minutesShort', { count: String(minutes) });
  return t('bill.hoursShort', { count: String(Math.round(minutes / 60)) });
}

/** «59:07», «1:02:03»: what is left, to the second, for a countdown. */
export function countdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}

/** The latest of these moments — how long a countdown over all of them has
 *  to tick; null when there are none. */
export function latestOf(moments: (string | null | undefined)[]): number | null {
  const times = moments.flatMap((moment) => (moment ? [Date.parse(moment)] : []));
  return times.length > 0 ? Math.max(...times) : null;
}

/** «just now», «5 min ago». */
export function sinceLabel(at: Date, now: Date, t: Translate): string {
  const ms = now.getTime() - at.getTime();
  return ms < 60_000 ? t('bill.justNow') : t('bill.ago', { duration: shortDuration(ms, t) });
}
