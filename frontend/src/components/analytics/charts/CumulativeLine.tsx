'use client';

import { useState, type KeyboardEvent } from 'react';
import type { TimelinePoint } from '@/types/analytics';
import { compactAmount, cumulative, timelineTick } from '@/lib/utils/analytics';
import ScrubArea from './ScrubArea';

const WIDTH = 320;
const HEIGHT = 150;
const LEFT = 30;
const RIGHT = 10;
const TOP = 18;
const BASE = 128;

/**
 * The money as it piled up over the period. A finger drawn along it — or a
 * tap, a hover, the arrow keys — marks a day or month with a vertical line and
 * says the total by then; the last one is marked to begin with.
 */
export default function CumulativeLine({ points, language, label, describe }: {
  points: TimelinePoint[];
  language: string;
  /** What the chart shows, for screen readers. */
  label: string;
  /** The words for a marked point: its date and the total by then. */
  describe: (point: TimelinePoint, total: number) => string;
}) {
  const totals = cumulative(points);
  const [selected, setSelected] = useState<number | null>(null);
  if (points.length === 0) return null;

  const last = points.length - 1;
  const step = points.length > 1 ? (WIDTH - LEFT - RIGHT) / last : 0;
  const nearest = (share: number) => (step ? Math.min(last, Math.max(0, Math.round((share * WIDTH - LEFT) / step))) : 0);

  const marked = Math.min(selected ?? last, last);
  const top = Math.max(...totals, 1);
  const keys: Record<string, number> = {
    ArrowLeft: marked - 1,
    ArrowDown: marked - 1,
    ArrowRight: marked + 1,
    ArrowUp: marked + 1,
    Home: 0,
    End: last,
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (!(event.key in keys)) return;
    event.preventDefault();
    setSelected(Math.min(last, Math.max(0, keys[event.key])));
  };
  const x = (index: number) => LEFT + index * step;
  const y = (value: number) => BASE - (value / top) * (BASE - TOP);
  const line = totals.map((total, index) => `${x(index)},${y(total)}`).join(' ');
  const ticks = tickIndexes(points.length);

  return (
    <figure className="m-0">
      <ScrubArea
        onScrub={(share) => setSelected(nearest(share))}
        role="slider"
        tabIndex={0}
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={last}
        aria-valuenow={marked}
        aria-valuetext={describe(points[marked], totals[marked])}
        onKeyDown={onKeyDown}
        className="cursor-crosshair rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="block h-auto w-full" aria-hidden="true">
          {[0.5, 1].map((share) => (
            <g key={share}>
              <line x1={LEFT} x2={WIDTH - RIGHT} y1={y(top * share)} y2={y(top * share)} className="stroke-border" strokeWidth={1} strokeDasharray="3 4" />
              <text x={0} y={y(top * share) + 3} className="fill-muted font-mono" fontSize={10}>
                {compactAmount(top * share, language)}
              </text>
            </g>
          ))}
          <line x1={LEFT} x2={WIDTH - RIGHT} y1={BASE} y2={BASE} className="stroke-outline" strokeWidth={1.5} />
          <polygon points={`${x(0)},${BASE} ${line} ${x(points.length - 1)},${BASE}`} className="fill-accent" fillOpacity={0.12} />
          <polyline points={line} fill="none" className="stroke-accent" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          <line x1={x(marked)} x2={x(marked)} y1={TOP - 6} y2={BASE} className="stroke-outline" strokeWidth={1.5} />
          <circle cx={x(marked)} cy={y(totals[marked])} r={5} className="fill-accent stroke-surface" strokeWidth={2} />
          {ticks.map((index) => (
            <text key={index} x={x(index)} y={HEIGHT - 4} textAnchor="middle" className="fill-muted font-mono" fontSize={10}>
              {timelineTick(points[index].key, language)}
            </text>
          ))}
        </svg>
      </ScrubArea>
      <figcaption className="mt-1 text-center font-mono text-[12px] text-foreground" aria-live="polite">
        {describe(points[marked], totals[marked])}
      </figcaption>
    </figure>
  );
}

/**
 * Up to seven evenly spread labels along the axis, the first and last among
 * them; one that would crowd the last is dropped.
 */
function tickIndexes(count: number): number[] {
  if (count <= 7) return Array.from({ length: count }, (_, index) => index);
  const every = Math.ceil((count - 1) / 6);
  const indexes = [];
  for (let index = 0; index < count - 1; index += every) indexes.push(index);
  if (count - 1 - indexes[indexes.length - 1] < every * 0.75) indexes.pop();
  return [...indexes, count - 1];
}
