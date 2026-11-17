import type { BillItem, BillParticipant } from '@/types/api';
import type { Currency } from '@/lib/utils/currencyCatalog';
import { dishCents, dishCount, dishEaters } from '@/lib/utils/itemSplit';

export interface BillPosition {
  key: string;
  item: BillItem;
  portionIndex: number;
  amount: number;
  participantIds: number[];
}

// Keep legacy API coordinates, but expose quantity as individual dish rows.
export function billPositions(items: BillItem[], participants: BillParticipant[], currency: Currency | undefined): BillPosition[] {
  return items.flatMap((item) => Array.from({ length: dishCount(item) }, (_, portionIndex) => ({
    key: `${item.id}:${portionIndex}`,
    item,
    portionIndex,
    amount: dishCents(item, portionIndex, currency) / 100,
    participantIds: dishEaters(item, portionIndex, participants),
  })));
}

// The creator never pays themselves, so their own flag says nothing about a dish.
export const hasPaid = (participant: BillParticipant, ownerId?: number) =>
  participant.is_paid && participant.user_id !== ownerId;

/** What these dishes come to, to the cent. */
export function positionsTotal(positions: BillPosition[]): number {
  return Math.round(positions.reduce((sum, position) => sum + position.amount * 100, 0)) / 100;
}

/** Somebody on these dishes has paid, so their split stays as it is. */
export function heldByPayment(participantIds: number[], participants: BillParticipant[], ownerId?: number): boolean {
  return participants.some((p) => participantIds.includes(p.id) && hasPaid(p, ownerId));
}

/**
 * A dish is settled once a payment covers it: somebody on it has paid and
 * nobody on it still owes. The creator's own claim is not a payment — a dish
 * only they have stays open for others to share or be handed.
 */
export function positionIsPaid(position: BillPosition, participants: BillParticipant[], ownerId?: number): boolean {
  const holders = participants.filter((p) => position.participantIds.includes(p.id));
  return holders.some((p) => hasPaid(p, ownerId))
    && holders.every((p) => hasPaid(p, ownerId) || p.user_id === ownerId);
}

const STATE_ORDER = { open: 0, taken: 1, settled: 2 } as const;
export type PositionState = keyof typeof STATE_ORDER;

/** Where a dish stands: nobody has it yet, someone has it, or it is paid for. */
export function positionState(position: BillPosition, participants: BillParticipant[], ownerId?: number): PositionState {
  if (position.participantIds.length === 0) return 'open';
  return positionIsPaid(position, participants, ownerId) ? 'settled' : 'taken';
}

/** Dishes still to hand out first, settled ones last; receipt order within each. */
export function sortByState(positions: BillPosition[], participants: BillParticipant[], ownerId?: number): BillPosition[] {
  const rank = new Map(positions.map((position) => [position.key, STATE_ORDER[positionState(position, participants, ownerId)]]));
  return [...positions].sort((a, b) => rank.get(a.key)! - rank.get(b.key)!);
}

export interface BillPositionGroup {
  key: string;
  item: BillItem;
  positions: BillPosition[];
  /** Everyone on at least one of the line's dishes. */
  participantIds: number[];
}

/**
 * Dishes handed out evenly among people: three dishes for three people is one
 * each, four for two is two each, two for four is each dish shared by two.
 * Everyone keeps the dishes they already have as far as the even split allows;
 * the rest go out in dish and table order. Null when they don't divide evenly,
 * or there is nothing to hand out — then everyone shares every dish, which
 * comes to the same money.
 */
export function dealDishes(positions: BillPosition[], participantIds: number[]): Map<number, number[]> | null {
  const dishes = [...positions].sort((a, b) => a.portionIndex - b.portionIndex);
  const people = participantIds.length;
  if (dishes.length < 2 || people < 2) return null;
  if (dishes.length % people !== 0 && people % dishes.length !== 0) return null;
  const perDish = Math.max(1, people / dishes.length);
  const perPerson = Math.max(1, dishes.length / people);

  const deal = new Map<number, number[]>(dishes.map((dish) => [dish.portionIndex, []]));
  const dealt = new Map<number, number>(participantIds.map((id) => [id, 0]));
  const give = (dish: BillPosition, id: number) => {
    deal.get(dish.portionIndex)!.push(id);
    dealt.set(id, dealt.get(id)! + 1);
  };
  const hasRoom = (dish: BillPosition) => deal.get(dish.portionIndex)!.length < perDish;
  const wantsMore = (id: number) => dealt.get(id)! < perPerson;

  for (const dish of dishes) {
    for (const id of participantIds) {
      if (hasRoom(dish) && wantsMore(id) && dish.participantIds.includes(id)) give(dish, id);
    }
  }
  for (const dish of dishes) {
    for (const id of participantIds) {
      if (hasRoom(dish) && wantsMore(id) && !deal.get(dish.portionIndex)!.includes(id)) give(dish, id);
    }
  }
  return deal;
}

/** Dishes gathered back into their receipt line, keeping the given order: a line
 *  takes the place of its first dish, its dishes keep their relative order. */
export function groupPositions(positions: BillPosition[]): BillPositionGroup[] {
  const groups = new Map<number, BillPositionGroup>();
  for (const position of positions) {
    const group = groups.get(position.item.id);
    if (group) {
      group.positions.push(position);
      group.participantIds = [...new Set([...group.participantIds, ...position.participantIds])];
    } else {
      groups.set(position.item.id, {
        key: String(position.item.id),
        item: position.item,
        positions: [position],
        participantIds: position.participantIds,
      });
    }
  }
  return [...groups.values()];
}
