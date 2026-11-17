import { describe, expect, it } from 'vitest';
import { BillStatus, type ParticipantReminder } from '@/types/api';
import { billFixture, participantFixture } from '@/test/billFixtures';
import { translations } from '@/lib/i18n/translations';
import { canBeReminded, countdown, latestOf, reminderState, sinceLabel, shortDuration, whyNobody } from './reminders';

const NOW = new Date('2026-10-01T12:00:00Z');
const minutes = (n: number) => new Date(NOW.getTime() + n * 60_000).toISOString();
const reminder = (overrides: Partial<ParticipantReminder>): ParticipantReminder => ({
  status: 'sent', at: minutes(-5), failure: null, next_at: minutes(55), ...overrides,
});

const t = (path: string, params?: Record<string, string>) => {
  const [section, key] = path.split('.');
  const template = (translations.en as unknown as Record<string, Record<string, string>>)[section][key];
  return Object.entries(params ?? {}).reduce((text, [name, value]) => text.replace(`{${name}}`, value), template);
};

describe('reminderState', () => {
  it('is ready with no reminder yet, or once the hour has passed', () => {
    expect(reminderState(null, NOW)).toEqual({ kind: 'ready', lastFailed: false });
    expect(reminderState(reminder({ next_at: minutes(-1) }), NOW)).toEqual({ kind: 'ready', lastFailed: false });
  });

  it('holds the hour after a reminder that went out', () => {
    expect(reminderState(reminder({}), NOW)).toEqual({ kind: 'reminded', at: new Date(minutes(-5)), nextAt: new Date(minutes(55)) });
  });

  it('shows one on its way', () => {
    expect(reminderState(reminder({ status: 'pending', next_at: minutes(9) }), NOW)).toEqual({ kind: 'sending' });
  });

  it('holds the hour for someone nobody can reach, and lets a lost one be sent again', () => {
    expect(reminderState(reminder({ status: 'failed', failure: 'unreachable' }), NOW).kind).toBe('unreachable');
    expect(reminderState(reminder({ status: 'failed', failure: 'no_senders', next_at: null }), NOW))
      .toEqual({ kind: 'ready', lastFailed: true });
    expect(reminderState(reminder({ status: 'failed', failure: 'settled', next_at: null }), NOW))
      .toEqual({ kind: 'ready', lastFailed: false });
  });
});

describe('canBeReminded', () => {
  const bill = billFixture({ owner_id: 10 });

  it('is for someone who joined, owes and has not paid', () => {
    expect(canBeReminded(bill, participantFixture({ user_id: 20, allocated_amount: 500 }))).toBe(true);
    expect(canBeReminded(bill, participantFixture({ user_id: null, is_guest: true, allocated_amount: 500 }))).toBe(false);
    expect(canBeReminded(bill, participantFixture({ user_id: 10, allocated_amount: 500 }))).toBe(false);
    expect(canBeReminded(bill, participantFixture({ user_id: 20, allocated_amount: 500, is_paid: true }))).toBe(false);
    expect(canBeReminded(bill, participantFixture({ user_id: 20, allocated_amount: 0 }))).toBe(false);
    expect(canBeReminded(billFixture({ owner_id: 10, status: BillStatus.CLOSED }), participantFixture({ user_id: 20, allocated_amount: 500 }))).toBe(false);
  });
});

describe('whyNobody', () => {
  const owner = participantFixture({ id: 1, user_id: 10, allocated_amount: 500 });
  const joined = participantFixture({ id: 2, user_id: 20 });
  const guest = participantFixture({ id: 3, user_id: null, is_guest: true });
  const why = (...others: typeof owner[]) => whyNobody(billFixture({ owner_id: 10, participants: [owner, ...others] }));

  it('names the first thing to do, in the order the server asks it', () => {
    expect(why()).toBe('no_people');
    // Someone who joined owes nothing yet: their items come before the guests.
    expect(why(joined, { ...guest, allocated_amount: 300 })).toBe('unassigned');
    expect(why({ ...joined, is_paid: true }, { ...guest, allocated_amount: 300 })).toBe('guests');
    expect(why(guest)).toBe('unassigned');
    expect(why({ ...joined, allocated_amount: 500, is_paid: true })).toBe('all_paid');
  });
});

describe('durations', () => {
  it('reads in minutes, then hours', () => {
    expect(shortDuration(30_000, t)).toBe('1 min');
    expect(shortDuration(45 * 60_000, t)).toBe('45 min');
    expect(shortDuration(150 * 60_000, t)).toBe('3 h');
  });

  it('says just now for the first minute', () => {
    expect(sinceLabel(new Date(NOW.getTime() - 20_000), NOW, t)).toBe('just now');
    expect(sinceLabel(new Date(minutes(-5)), NOW, t)).toBe('5 min ago');
  });
});

describe('countdown', () => {
  it('counts to the second, in minutes and then hours', () => {
    expect(countdown(59 * 60_000 + 7_000)).toBe('59:07');
    expect(countdown(5_500)).toBe('0:06');
    expect(countdown(3_723_000)).toBe('1:02:03');
    expect(countdown(-1)).toBe('0:00');
  });

  it('ticks until the last of the moments it is given', () => {
    expect(latestOf([minutes(30), null, minutes(50), undefined])).toBe(Date.parse(minutes(50)));
    expect(latestOf([null, undefined])).toBeNull();
  });
});
