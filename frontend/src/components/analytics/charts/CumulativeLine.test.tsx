import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { TimelinePoint } from '@/types/analytics';
import CumulativeLine from './CumulativeLine';

const POINTS: TimelinePoint[] = [
  { key: '2026-09-01', amount: 100, bills: 1 },
  { key: '2026-09-02', amount: 0, bills: 0 },
  { key: '2026-09-03', amount: 50, bills: 1 },
];

const touchAt = (x: number, y: number) => ({ identifier: 1, clientX: x, clientY: y, target: document.body }) as unknown as Touch;

function chart() {
  render(<CumulativeLine points={POINTS} language="en" label="Running total" describe={(point, total) => `${point.key} · ${total}`} />);
  const plot = screen.getByRole('slider', { name: 'Running total' });
  vi.spyOn(plot, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 320, height: 150, right: 320, bottom: 150, x: 0, y: 0, toJSON: () => ({}) });
  return plot;
}

describe('CumulativeLine', () => {
  it('marks the last point to begin with', () => {
    expect(chart()).toHaveAttribute('aria-valuetext', '2026-09-03 · 150');
  });

  it('follows a finger drawn sideways and keeps the drag from the page', () => {
    const plot = chart();
    expect(plot).toHaveAttribute('data-no-swipe');

    fireEvent.touchStart(plot, { touches: [touchAt(30, 60)], changedTouches: [touchAt(30, 60)] });
    // Not yet: the finger may be about to scroll the page.
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-03 · 150');

    const move = touchAt(170, 64);
    const moved = fireEvent.touchMove(plot, { touches: [move], changedTouches: [move], cancelable: true });
    expect(moved).toBe(false);
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-02 · 100');
  });

  it('leaves a vertical drag to scroll the page', () => {
    const plot = chart();
    fireEvent.touchStart(plot, { touches: [touchAt(300, 20)], changedTouches: [touchAt(300, 20)] });

    const move = touchAt(304, 120);
    expect(fireEvent.touchMove(plot, { touches: [move], changedTouches: [move], cancelable: true })).toBe(true);
    fireEvent.touchStart(plot, { touches: [touchAt(30, 20)], changedTouches: [touchAt(30, 20)] });
    fireEvent.touchMove(plot, { touches: [touchAt(31, 120)], changedTouches: [touchAt(31, 120)] });
    fireEvent.touchEnd(plot, { touches: [], changedTouches: [touchAt(31, 120)] });
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-03 · 150');
  });

  it('steps with the arrow keys', async () => {
    const user = userEvent.setup();
    const plot = chart();
    plot.focus();

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-01 · 100');
    await user.keyboard('{End}');
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-03 · 150');
    await user.keyboard('{ArrowDown}');
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-02 · 100');
    await user.keyboard('{ArrowUp}');
    expect(plot).toHaveAttribute('aria-valuetext', '2026-09-03 · 150');
  });
});
