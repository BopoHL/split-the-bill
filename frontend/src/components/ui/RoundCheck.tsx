import { Check, Minus } from 'lucide-react';

/** Whether something is ticked for all it covers, part of it, or none. */
export type CheckState = 'all' | 'some' | 'none';

const SIZES = {
  sm: { box: 'h-5 w-5', icon: 'h-3 w-3' },
  md: { box: 'h-[22px] w-[22px]', icon: 'h-3.5 w-3.5' },
} as const;

/** The round tick of a pick list. Drawn only: the control it marks carries the state. */
export default function RoundCheck({ state, size = 'md' }: { state: CheckState; size?: keyof typeof SIZES }) {
  const Icon = state === 'all' ? Check : state === 'some' ? Minus : null;
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full border-[1.5px] border-outline ${SIZES[size].box} ${
        state === 'none' ? 'bg-surface' : 'bg-accent text-accent-fg'
      }`}
    >
      {Icon && <Icon className={SIZES[size].icon} strokeWidth={3.25} />}
    </span>
  );
}
