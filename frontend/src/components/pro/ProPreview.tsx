'use client';

import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { BellRing, Check, Infinity as Unlimited, Mic, ReceiptText } from 'lucide-react';
import ThemeDot from '@/components/ui/ThemeDot';
import { THEMES } from '@/lib/utils/themes';
import type { PaywallReason } from '@/types/pro';

/** Lines on a receipt, drawn as bars: no words, the shape says it. */
const Bar = ({ className }: { className: string }) => <span className={`block h-2 rounded-full bg-border ${className}`} />;
/** Someone at the table, as the avatars on the receipt show them. */
const Face = ({ className }: { className: string }) => (
  <span className={`block h-4 w-4 rounded-full border-[1.5px] border-outline ${className}`} />
);

/** The tile a preview sits on: the paywall's first thing, above the headline. */
function Tile({ children }: { children: ReactNode }) {
  return (
    <div
      aria-hidden="true"
      className="mb-4 flex h-[112px] items-center justify-center gap-4 overflow-hidden rounded-xl border-[1.5px] border-outline bg-surface px-4 shadow-[var(--shadow-hard-sm)]"
    >
      {children}
    </div>
  );
}

/**
 * What Pro does for the thing that opened the paywall, shown rather than told:
 * the feature at work in a few strokes and no words, for people who read none.
 * «general» has nothing in particular to show and keeps the medal.
 */
export default function ProPreview({ reason }: { reason: PaywallReason }) {
  const calm = !!useReducedMotion();
  // Comes in a beat after the one before it; still where motion is unwelcome.
  const rise = (order: number) => (calm ? {} : {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { type: 'spring' as const, duration: 0.5, bounce: 0.2, delay: 0.15 + order * 0.12 },
  });

  if (reason === 'voice') {
    return (
      <Tile>
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-[1.5px] border-outline bg-accent text-accent-fg shadow-[var(--shadow-hard-sm)]">
          <Mic className="h-6 w-6" strokeWidth={2.25} />
        </span>
        <span className="flex h-10 items-center gap-1">
          {[10, 22, 32, 18, 28, 12].map((height, i) => (
            <motion.span
              key={i}
              className="block w-1.5 rounded-full bg-accent"
              style={{ height }}
              animate={calm ? undefined : { scaleY: [1, 0.45, 1] }}
              transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.12, ease: 'easeInOut' }}
            />
          ))}
        </span>
        <span className="flex w-28 flex-col gap-2.5 rounded-lg border-[1.5px] border-outline bg-background p-2.5">
          {[['w-12', 'bg-accent', 'bg-success'], ['w-9', 'bg-star']].map(([width, ...faces], i) => (
            <motion.span key={i} className="flex items-center gap-1.5" {...rise(i)}>
              <Bar className={width} />
              <span className="ml-auto flex -space-x-1.5">
                {faces.map((face) => <Face key={face} className={face} />)}
              </span>
            </motion.span>
          ))}
        </span>
      </Tile>
    );
  }

  if (reason === 'reminders') {
    return (
      <Tile>
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-[1.5px] border-outline bg-accent text-accent-fg">
          <BellRing className="h-5 w-5" strokeWidth={2.25} />
        </span>
        <motion.span
          className="flex w-36 flex-col gap-2 rounded-2xl rounded-bl-sm border-[1.5px] border-outline bg-background p-3"
          {...rise(0)}
        >
          <Bar className="w-24" />
          <Bar className="w-16" />
        </motion.span>
        <motion.span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-[1.5px] border-outline bg-success text-success-fg"
          {...rise(2)}
        >
          <Check className="h-4 w-4" strokeWidth={3} />
        </motion.span>
      </Tile>
    );
  }

  if (reason === 'themes') {
    return (
      <Tile>
        {THEMES.filter((theme) => theme.pro).map((theme, i) => (
          <motion.span key={theme.id} {...rise(i)}>
            <ThemeDot theme={theme.id} className="h-10 w-10 border-outline shadow-[var(--shadow-hard-sm)]" />
          </motion.span>
        ))}
      </Tile>
    );
  }

  if (reason === 'analytics') {
    return (
      <Tile>
        <span className="flex h-16 items-end gap-2">
          {[28, 44, 34, 60, 40, 52].map((height, i) => (
            <motion.span
              key={i}
              className={`block w-5 origin-bottom rounded-t-md border-[1.5px] border-outline ${i === 3 ? 'bg-accent' : 'bg-accent-weak'}`}
              style={{ height }}
              initial={calm ? false : { scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ type: 'spring', duration: 0.6, bounce: 0.25, delay: 0.15 + i * 0.07 }}
            />
          ))}
        </span>
      </Tile>
    );
  }

  if (reason === 'scans') {
    return (
      <Tile>
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="relative text-muted" {...rise(i)}>
            <ReceiptText className="h-10 w-10" strokeWidth={1.75} />
            <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-success text-success-fg">
              <Check className="h-2.5 w-2.5" strokeWidth={3.5} />
            </span>
          </motion.span>
        ))}
        <motion.span
          className="flex h-12 w-12 items-center justify-center rounded-full border-[1.5px] border-outline bg-accent text-accent-fg shadow-[var(--shadow-hard-sm)]"
          {...rise(3)}
        >
          <Unlimited className="h-6 w-6" strokeWidth={2.5} />
        </motion.span>
      </Tile>
    );
  }

  return null;
}
