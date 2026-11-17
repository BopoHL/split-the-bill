'use client';

import { Minus, Plus } from 'lucide-react';

interface CountStepperProps {
  /** Current value as a string (kept as string to mirror the inputs it replaces). */
  value: string;
  onChange: (next: string) => void;
  min?: number;
}

/**
 * Compact «− value +» stepper for small counts (item quantity). The buttons
 * nudge by one; the value itself is display-only (no keypad).
 */
export default function CountStepper({ value, onChange, min = 1 }: CountStepperProps) {
  const parsed = parseInt(value, 10);
  const current = isNaN(parsed) ? 0 : parsed;

  return (
    <div className="flex h-11 items-stretch overflow-hidden rounded-[7px] border-[1.5px] border-outline">
      <button
        type="button"
        aria-label="−"
        onClick={() => onChange(String(Math.max(min, current - 1)))}
        className="flex w-11 items-center justify-center border-r-[1.5px] border-outline bg-surface text-foreground transition-colors hover:bg-accent hover:text-accent-fg active:translate-y-px"
      >
        <Minus className="h-[18px] w-[18px]" />
      </button>
      <span className="flex w-11 items-center justify-center bg-background font-mono text-[16px] font-semibold text-foreground">
        {value || String(min)}
      </span>
      <button
        type="button"
        aria-label="+"
        onClick={() => onChange(String(Math.max(min, current + 1)))}
        className="flex w-11 items-center justify-center border-l-[1.5px] border-outline bg-surface text-foreground transition-colors hover:bg-accent hover:text-accent-fg active:translate-y-px"
      >
        <Plus className="h-[18px] w-[18px]" />
      </button>
    </div>
  );
}
