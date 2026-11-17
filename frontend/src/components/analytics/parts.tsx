'use client';

import type { ReactNode } from 'react';
import type { DishGroup } from '@/types/analytics';

/** The fill each kind of spending wears, in the fixed chart order. */
export const GROUP_TONES: Record<DishGroup, string> = {
  food: 'bg-chart-1',
  drink: 'bg-chart-2',
  dessert: 'bg-chart-3',
  alcohol: 'bg-chart-4',
  fee: 'bg-chart-5',
  other: 'bg-chart-other',
  discount: 'bg-chart-other',
};

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-lg border-[1.5px] border-outline bg-surface p-3.5 ${className}`}>{children}</section>;
}

export function CardTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h3 className="font-display text-[15px] font-bold text-foreground">{children}</h3>
      {aside && <span className="shrink-0 font-mono text-[11px] text-muted">{aside}</span>}
    </div>
  );
}

/** A number with what it counts above it and a word about it below. */
export function Stat({ label, value, hint, dark = false }: { label: string; value: string; hint?: string; dark?: boolean }) {
  return (
    <div className={`min-w-0 rounded-lg border-[1.5px] px-3 py-2.5 ${dark ? 'border-emphasis bg-emphasis text-emphasis-fg' : 'border-outline bg-surface text-foreground'}`}>
      <div className={`font-mono text-[10px] uppercase tracking-[0.04em] ${dark ? 'opacity-80' : 'text-muted'}`}>{label}</div>
      <div className="mt-1 break-words font-mono text-[17px] font-bold leading-tight tabular-nums">{value}</div>
      {hint && <div className={`mt-0.5 text-[11px] ${dark ? 'opacity-80' : 'text-muted'}`}>{hint}</div>}
    </div>
  );
}

export interface LedgerLine {
  key: string;
  label: string;
  hint?: string;
  value: string;
}

/** Amounts down a receipt: what each is on the left, the sum on the right, at any length. */
export function Ledger({ lines }: { lines: LedgerLine[] }) {
  return (
    <Card className="py-0.5">
      <dl className="m-0 divide-y-[1.5px] divide-dashed divide-border">
        {lines.map((line) => (
          <div key={line.key} className="flex items-center justify-between gap-3 py-2.5">
            <dt className="min-w-0">
              <div className="text-[14px] font-semibold text-foreground">{line.label}</div>
              {line.hint && <div className="text-[12px] text-muted">{line.hint}</div>}
            </dt>
            <dd className="m-0 shrink-0 text-right font-mono text-[15px] font-bold tabular-nums text-foreground">{line.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

/** A rubber stamp: a badge, a record, a verdict. */
export function Stamp({ children, tone = 'ink', tilt = -3 }: { children: ReactNode; tone?: 'ink' | 'accent' | 'success' | 'danger'; tilt?: number }) {
  const tones = {
    ink: 'border-outline text-foreground',
    accent: 'border-accent text-accent',
    success: 'border-success text-success',
    danger: 'border-danger text-danger',
  };
  return (
    <span
      className={`inline-flex items-center rounded-[5px] border-2 px-2 py-[3px] font-mono text-[11px] font-bold uppercase tracking-[0.08em] ${tones[tone]}`}
      style={{ transform: `rotate(${tilt}deg)` }}
    >
      {children}
    </span>
  );
}

export function Swatch({ tone }: { tone: string }) {
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-[2px] ${tone}`} aria-hidden />;
}

/** Nothing to show for the period, said plainly. */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-[10px] border-[1.5px] border-dashed border-outline bg-surface px-5 py-7 text-center">
      <p className="font-display text-[15px] font-bold text-foreground">{title}</p>
      {hint && <p className="mt-1.5 text-[13px] text-muted">{hint}</p>}
    </div>
  );
}
