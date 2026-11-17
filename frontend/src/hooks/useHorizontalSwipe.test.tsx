import { fireEvent, render } from '@testing-library/react';
import { useLayoutEffect, useRef } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useHorizontalSwipe } from './useHorizontalSwipe';

function Page({ onSwipeEnd }: { onSwipeEnd: (dx: number) => void }) {
  const area = useRef<HTMLDivElement>(null);
  useHorizontalSwipe(area, { onSwipeStart: vi.fn(), onSwipeMove: vi.fn(), onSwipeEnd }, { reachesPageBottom: true });
  return (
    <div data-swipe-surface data-testid="page">
      <header data-testid="header">tabs</header>
      <div ref={area} data-testid="panels">short content</div>
      <div data-testid="background" />
    </div>
  );
}

const swipe = (target: Element, y: number) => {
  const at = (x: number) => ({ identifier: 1, clientX: x, clientY: y, target });
  fireEvent.touchStart(target, { touches: [at(300)], changedTouches: [at(300)] });
  fireEvent.touchMove(target, { touches: [at(200)], changedTouches: [at(200)] });
  fireEvent.touchEnd(target, { touches: [], changedTouches: [at(150)] });
};

describe('useHorizontalSwipe reaching the page bottom', () => {
  const layout = (panelsTop: number) =>
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return { top: this.dataset.testid === 'panels' ? panelsTop : 0 } as DOMRect;
    });

  it('takes a swipe that starts on the empty page below the panels', () => {
    const rect = layout(200);
    const onSwipeEnd = vi.fn();
    const view = render(<Page onSwipeEnd={onSwipeEnd} />);

    swipe(view.getByTestId('background'), 600);

    expect(onSwipeEnd).toHaveBeenCalledWith(-150, expect.any(Number));
    rect.mockRestore();
  });

  it('leaves a swipe above the panels alone', () => {
    const rect = layout(200);
    const onSwipeEnd = vi.fn();
    const view = render(<Page onSwipeEnd={onSwipeEnd} />);

    swipe(view.getByTestId('header'), 80);

    expect(onSwipeEnd).not.toHaveBeenCalled();
    rect.mockRestore();
  });
});

/** Swipes in the same commit that puts it on screen — before any passive
 *  effect has had a chance to run. */
function SwipedOnArrival({ onSwipeEnd }: { onSwipeEnd: (dx: number) => void }) {
  const area = useRef<HTMLDivElement>(null);
  useHorizontalSwipe(area, { onSwipeStart: vi.fn(), onSwipeMove: vi.fn(), onSwipeEnd });
  useLayoutEffect(() => {
    if (area.current) swipe(area.current, 80);
  }, []);
  return <div ref={area}>panels</div>;
}

describe('useHorizontalSwipe on arrival', () => {
  it('listens from the commit that puts the area on screen', () => {
    const onSwipeEnd = vi.fn();
    render(<SwipedOnArrival onSwipeEnd={onSwipeEnd} />);

    expect(onSwipeEnd).toHaveBeenCalledWith(-150, expect.any(Number));
  });
});
