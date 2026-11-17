import type { BillItem, BillParticipant } from '@/types/api';
import { shareStepCents, type Currency } from '@/lib/utils/currencyCatalog';

// How a bill's money is owed by the seats at its table. Mirrors item_split.py
// on the server, so the amounts a seat sees add up to what it is asked to pay.

export const toCents = (amount: number) => Math.round((amount + Number.EPSILON) * 100);

/** `totalCents` cut into `parts` as even as whole steps allow, larger parts first; odd cents stay with the first. */
export function splitInSteps(totalCents: number, parts: number, stepCents: number): number[] {
  const steps = Math.floor(totalCents / stepCents);
  const odd = totalCents - steps * stepCents;
  const base = Math.floor(steps / parts);
  const extra = steps - base * parts;
  return Array.from({ length: parts }, (_, index) => (base + (index < extra ? 1 : 0)) * stepCents + (index === 0 ? odd : 0));
}

export const dishCount = (item: BillItem) => Math.max(1, item.count || 1);

export function dishCents(item: BillItem, portionIndex: number, currency: Currency | undefined): number {
  return splitInSteps(toCents(item.item_sum), dishCount(item), shareStepCents(currency))[portionIndex];
}

/** Seats on one dish of a line: everyone at the table for a line shared among all. */
export function dishEaters(item: BillItem, portionIndex: number, participants: BillParticipant[]): number[] {
  const known = new Set(participants.map((p) => p.id));
  const eaters = item.is_shared_globally
    ? participants.map((p) => p.id)
    : item.portions?.[portionIndex] ?? item.assigned_participant_ids;
  return [...new Set(eaters)].filter((id) => known.has(id));
}

export interface TableSplit {
  /** `totalCents` shared equally, in cents; the owner, when among them, takes the larger part. */
  splitEvenly(totalCents: number, among: number[]): Map<number, number>;
  /**
   * What each seat owes for each line, by item id, in the bill's currency.
   * Every dish eaten by the same people, on whatever line, is shared once, and
   * the group's shares are laid back over its lines in receipt order.
   */
  splitItems(items: BillItem[]): Map<number, Map<number, number>>;
}

export function tableSplit(participants: BillParticipant[], ownerId: number | undefined, currency: Currency | undefined): TableSplit {
  const step = shareStepCents(currency);
  const ownerSeat = participants.find((p) => p.user_id === ownerId)?.id;
  const rank = new Map(participants.map((p, index) => [p.id, p.id === ownerSeat ? -1 : index]));

  const splitEvenly = (totalCents: number, among: number[]) => {
    const recipients = [...among].sort((a, b) => rank.get(a)! - rank.get(b)!);
    const parts = splitInSteps(totalCents, recipients.length, step);
    return new Map(recipients.map((id, index) => [id, parts[index]]));
  };

  const splitItems = (items: BillItem[]) => {
    const ordered = [...items].sort((a, b) => a.id - b.id);
    const groups = new Map<string, { eaters: number[]; lines: Map<number, number> }>();
    ordered.forEach((item) => {
      splitInSteps(toCents(item.item_sum), dishCount(item), step).forEach((cents, portionIndex) => {
        const eaters = dishEaters(item, portionIndex, participants).sort((a, b) => a - b);
        if (eaters.length === 0) return;
        const key = eaters.join(',');
        const group = groups.get(key) ?? { eaters, lines: new Map<number, number>() };
        group.lines.set(item.id, (group.lines.get(item.id) ?? 0) + cents);
        groups.set(key, group);
      });
    });

    const shares = new Map<number, Map<number, number>>(ordered.map((item) => [item.id, new Map()]));
    for (const { eaters, lines } of groups.values()) {
      let settled = new Map(eaters.map((id) => [id, 0]));
      let running = 0;
      for (const [itemId, cents] of lines) {
        running += cents;
        const cumulative = splitEvenly(running, eaters);
        const line = shares.get(itemId)!;
        for (const id of eaters) line.set(id, (line.get(id) ?? 0) + cumulative.get(id)! - settled.get(id)!);
        settled = cumulative;
      }
    }
    return new Map([...shares].map(([itemId, line]) => [itemId, new Map([...line].map(([id, cents]) => [id, cents / 100]))]));
  };

  return { splitEvenly, splitItems };
}
