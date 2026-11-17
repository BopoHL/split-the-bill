import { describe, expect, it, vi } from 'vitest';
import { useRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { useScrub } from './useScrub';

function Chart({ onScrub }: { onScrub: (share: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useScrub(ref, onScrub);
  return <div ref={ref} data-testid="chart" />;
}

const finger = (x: number, y: number) => ({ identifier: 1, clientX: x, clientY: y });

function setup() {
  const onScrub = vi.fn();
  render(<Chart onScrub={onScrub} />);
  const chart = screen.getByTestId('chart');
  chart.getBoundingClientRect = () => ({ left: 0, width: 200, top: 0, height: 100 }) as DOMRect;
  return { chart, onScrub };
}

describe('useScrub', () => {
  it('leaves the chart alone while the page is scrolled over it', () => {
    const { chart, onScrub } = setup();

    fireEvent.touchStart(chart, { touches: [finger(50, 10)], changedTouches: [finger(50, 10)] });
    fireEvent.touchMove(chart, { touches: [finger(52, 60)], changedTouches: [finger(52, 60)] });
    fireEvent.touchEnd(chart, { touches: [], changedTouches: [finger(52, 60)] });

    expect(onScrub).not.toHaveBeenCalled();
  });

  it('follows a sideways drag, and a tap picks where it lands', () => {
    const { chart, onScrub } = setup();

    fireEvent.touchStart(chart, { touches: [finger(50, 10)], changedTouches: [finger(50, 10)] });
    fireEvent.touchMove(chart, { touches: [finger(100, 12)], changedTouches: [finger(100, 12)] });
    fireEvent.touchEnd(chart, { touches: [], changedTouches: [finger(100, 12)] });
    expect(onScrub.mock.calls).toEqual([[0.5]]);

    fireEvent.touchStart(chart, { touches: [finger(150, 10)], changedTouches: [finger(150, 10)] });
    fireEvent.touchEnd(chart, { touches: [], changedTouches: [finger(150, 10)] });
    expect(onScrub).toHaveBeenLastCalledWith(0.75);
  });
});
