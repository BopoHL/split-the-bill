import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import EdgeSwipeBack from './EdgeSwipeBack';

type Point = { x: number; y: number };

const touchAt = ({ x, y }: Point) => ({ identifier: 1, clientX: x, clientY: y });

function drag(target: Element, points: Point[], { lift = true } = {}) {
  const [first, ...rest] = points.map(touchAt);
  fireEvent.touchStart(target, { touches: [first], changedTouches: [first] });
  for (const touch of rest) fireEvent.touchMove(target, { touches: [touch], changedTouches: [touch] });
  if (lift) fireEvent.touchEnd(target, { touches: [], changedTouches: [rest.at(-1) ?? first] });
}

function renderPage(onBack = vi.fn()) {
  render(
    <>
      <div data-back-swipe-layer="page" data-testid="page">
        <button type="button">Row</button>
      </div>
      <div data-testid="overlay">Keypad</div>
      <EdgeSwipeBack onBack={onBack} />
    </>,
  );
  return onBack;
}

describe('EdgeSwipeBack', () => {
  it('goes back when the page is pulled far enough from the left edge', () => {
    const onBack = renderPage();

    drag(screen.getByRole('button', { name: 'Row' }), [{ x: 8, y: 300 }, { x: 30, y: 302 }, { x: 600, y: 310 }]);

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('carries the page with the finger and puts it back when let go early', () => {
    const onBack = renderPage();
    const page = screen.getByTestId('page');

    drag(page, [{ x: 8, y: 300 }, { x: 30, y: 300 }, { x: 60, y: 300 }], { lift: false });
    expect(page.style.translate).toBe('52px 0');

    const last = touchAt({ x: 60, y: 300 });
    fireEvent.touchCancel(page, { touches: [], changedTouches: [last] });
    expect(page.style.translate).toBe('');
    expect(onBack).not.toHaveBeenCalled();
  });

  it('leaves touches away from the edge, upward drags and overlays alone', () => {
    const onBack = renderPage();
    const page = screen.getByTestId('page');

    drag(page, [{ x: 120, y: 300 }, { x: 150, y: 300 }, { x: 700, y: 300 }]);
    drag(page, [{ x: 8, y: 300 }, { x: 12, y: 360 }, { x: 600, y: 420 }]);
    drag(screen.getByTestId('overlay'), [{ x: 8, y: 300 }, { x: 30, y: 300 }, { x: 600, y: 300 }]);

    expect(onBack).not.toHaveBeenCalled();
    expect(page.style.translate).toBe('');
  });

  it('keeps the page from scrolling once the swipe is recognised', () => {
    renderPage();
    const page = screen.getByTestId('page');
    const start = touchAt({ x: 8, y: 300 });
    fireEvent.touchStart(page, { touches: [start], changedTouches: [start] });

    const aside = touchAt({ x: 40, y: 304 });
    expect(fireEvent.touchMove(page, { touches: [aside], changedTouches: [aside] })).toBe(false);
  });
});

describe('EdgeSwipeBack over another one', () => {
  function renderSheetOverPage() {
    const leavePage = vi.fn();
    const closeSheet = vi.fn();
    const view = render(
      <>
        <div data-back-swipe-layer="page" data-testid="page">Page</div>
        <EdgeSwipeBack onBack={leavePage} />
        <div data-back-swipe-layer="paywall" data-testid="sheet">Sheet</div>
        <EdgeSwipeBack onBack={closeSheet} layer="paywall" />
      </>,
    );
    return { leavePage, closeSheet, view };
  }

  it('closes the sheet and carries only the sheet, leaving the page where it is', () => {
    const { leavePage, closeSheet } = renderSheetOverPage();

    drag(screen.getByTestId('sheet'), [{ x: 8, y: 300 }, { x: 30, y: 300 }, { x: 60, y: 300 }], { lift: false });
    expect(screen.getByTestId('sheet').style.translate).toBe('52px 0');
    expect(screen.getByTestId('page').style.translate).toBe('');

    const far = touchAt({ x: 600, y: 300 });
    fireEvent.touchMove(screen.getByTestId('sheet'), { touches: [far], changedTouches: [far] });
    fireEvent.touchEnd(screen.getByTestId('sheet'), { touches: [], changedTouches: [far] });

    expect(closeSheet).toHaveBeenCalledTimes(1);
    expect(leavePage).not.toHaveBeenCalled();
  });

  it('gives the swipe back to the page once the sheet is gone', () => {
    const leavePage = vi.fn();
    const { rerender } = render(
      <>
        <div data-back-swipe-layer="page" data-testid="page">Page</div>
        <EdgeSwipeBack onBack={leavePage} />
        <EdgeSwipeBack onBack={vi.fn()} layer="paywall" />
      </>,
    );
    drag(screen.getByTestId('page'), [{ x: 8, y: 300 }, { x: 30, y: 300 }, { x: 600, y: 300 }]);
    expect(leavePage).not.toHaveBeenCalled();

    rerender(
      <>
        <div data-back-swipe-layer="page" data-testid="page">Page</div>
        <EdgeSwipeBack onBack={leavePage} />
      </>,
    );
    drag(screen.getByTestId('page'), [{ x: 8, y: 300 }, { x: 30, y: 300 }, { x: 600, y: 300 }]);

    expect(leavePage).toHaveBeenCalledTimes(1);
  });
});
