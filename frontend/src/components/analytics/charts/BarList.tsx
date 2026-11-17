'use client';

import type { ReactNode } from 'react';

export interface BarRow {
  key: string;
  label: ReactNode;
  value: number;
  /** What the row says on its right — the value, formatted. */
  shown: string;
  /** Tailwind classes for the bar's fill; the ink by default. */
  tone?: string;
}

/** Ranked rows, each with a bar for its share of the largest. */
export default function BarList({ rows, labelWidth = 'w-[124px]' }: { rows: BarRow[]; labelWidth?: string }) {
  const top = Math.max(...rows.map((row) => row.value), 1);

  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {rows.map((row) => (
        <li key={row.key} className="flex items-center gap-2.5">
          <span className={`${labelWidth} shrink-0 truncate text-[14px] text-foreground`}>{row.label}</span>
          <span className="h-2.5 min-w-0 flex-1" aria-hidden>
            <span
              className={`block h-2.5 rounded-r-[4px] ${row.tone ?? 'bg-foreground'}`}
              style={{ width: `${Math.max(3, Math.round((row.value / top) * 100))}%` }}
            />
          </span>
          <span className="w-16 shrink-0 text-right font-mono text-[13px] font-bold tabular-nums text-foreground">{row.shown}</span>
        </li>
      ))}
    </ul>
  );
}
