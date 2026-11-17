import { describe, it, expect } from 'vitest';

import { placeList } from './StepPeople';

const rect = (top: number, height = 48): DOMRect =>
  ({ top, bottom: top + height, left: 20, width: 300, height } as DOMRect);

describe('placeList — where the currency list opens', () => {
  it('drops under the picker when there is room, bounded to its own height', () => {
    const placed = placeList(rect(100), 800);

    expect(placed.up).toBe(false);
    expect(placed.maxHeight).toBe(224);
    expect(placed.edge).toBe(154);
    expect(placed).toMatchObject({ left: 20, width: 300 });
  });

  it('opens upward on a short screen where the room is over the picker', () => {
    const placed = placeList(rect(600), 700);

    expect(placed.up).toBe(true);
    // Grows away from the bottom edge, starting just above the trigger.
    expect(placed.edge).toBe(106);
    expect(placed.maxHeight).toBe(224);
  });

  it('shrinks to the room that is there rather than running off the screen', () => {
    const placed = placeList(rect(500), 700);

    expect(placed.up).toBe(false);
    expect(placed.maxHeight).toBe(140);
  });
});
