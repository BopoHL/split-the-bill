import { afterEach, describe, expect, it } from 'vitest';
import { findTarget, TourAnchor } from './anchors';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('findTarget', () => {
  it('tells repeated anchors apart by key or by order', () => {
    document.body.innerHTML = `
      <button data-tour="assign-items" data-tour-key="0">me</button>
      <button data-tour="assign-items" data-tour-key="1">friend</button>
      <label data-tour="assign-dish">plov</label>
      <label data-tour="assign-dish">kebab</label>
    `;

    expect(findTarget({ anchor: TourAnchor.AssignItems, key: 1 })?.textContent).toBe('friend');
    expect(findTarget({ anchor: TourAnchor.AssignDish, index: 1 })?.textContent).toBe('kebab');
    expect(findTarget({ anchor: TourAnchor.AssignDish })?.textContent).toBe('plov');
    expect(findTarget({ anchor: TourAnchor.CloseBill })).toBeNull();
  });
});
