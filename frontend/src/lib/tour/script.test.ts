import { describe, expect, it } from 'vitest';
import { guestTour } from './script';

describe('guestTour', () => {
  it('walks a guest from their seat through picking dishes to paying', () => {
    expect(guestTour({ canPickItems: true }).steps.map((step) => step.id)).toEqual([
      'guestSeat', 'guestPick', 'guestDishes', 'guestShare', 'guestPaid',
    ]);
  });

  it('leaves picking out where dishes are not theirs to pick', () => {
    expect(guestTour({ canPickItems: false }).steps.map((step) => step.id)).toEqual([
      'guestSeat', 'guestShare', 'guestPaid',
    ]);
  });

  it('only points at paying, which shows once there is something to pay', () => {
    const paying = guestTour({ canPickItems: true }).steps.filter((step) => step.optional);

    expect(paying.map((step) => [step.id, step.kind])).toEqual([['guestShare', 'look'], ['guestPaid', 'look']]);
  });
});
