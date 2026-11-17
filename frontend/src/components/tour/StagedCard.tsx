'use client';

import { useEffect, useState, type RefObject } from 'react';
import { Check } from 'lucide-react';
import { TourAnchor } from '@/lib/tour/anchors';
import { DEMO_CARD } from '@/lib/tour/script';
import { useTourTarget } from './useTourTarget';

const CARD_FIELD = { anchor: TourAnchor.CardField };
const TYPE_EVERY_MS = 45;

/** The card the tour types into the new bill's field — drawn over the real
 *  one, which stays empty: nothing of it is saved. */
export default function StagedCard({ ignore }: { ignore: RefObject<Element | null> }) {
  const box = useTourTarget('staged-card', CARD_FIELD, ignore);
  const [typed, setTyped] = useState(0);

  useEffect(() => {
    if (typed >= DEMO_CARD.length) return;
    const timer = setTimeout(() => setTyped((count) => count + 1), TYPE_EVERY_MS);
    return () => clearTimeout(timer);
  }, [typed]);

  if (!box) return null;
  const done = typed >= DEMO_CARD.length;

  return (
    <div
      aria-hidden="true"
      style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
      className="pointer-events-none fixed flex items-center gap-2 rounded-[9px] border-[1.5px] border-accent bg-background px-3.5"
    >
      <span className="min-w-0 flex-1 font-mono text-[16px] font-bold tracking-[0.02em] text-foreground">
        {DEMO_CARD.slice(0, typed)}
        {!done && <span className="ml-px inline-block h-[1.1em] w-[2px] translate-y-[3px] animate-pulse bg-accent" />}
      </span>
      {done && (
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-success text-success-fg">
          <Check className="h-4 w-4" strokeWidth={2.5} />
        </span>
      )}
    </div>
  );
}
