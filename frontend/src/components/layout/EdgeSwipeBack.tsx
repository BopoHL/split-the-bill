'use client';

import { useRef } from 'react';
import { createPortal } from 'react-dom';
import { useReducedMotion } from 'framer-motion';
import { ArrowLeft } from 'lucide-react';
import { useEdgeSwipeBack, type BackSwipeLayer } from '@/hooks/useEdgeSwipeBack';

/** What shows behind a layer pulled aside: a plain backdrop behind a screen;
 *  the screen itself behind a sheet over it, the arrow just above it. */
const BEHIND: Record<BackSwipeLayer, string> = {
  page: 'z-0 bg-surface-2',
  paywall: 'z-[69]',
};

/**
 * The back swipe for a screen — or a sheet over one — that has somewhere to go
 * back to, and what shows behind it while it is pulled aside, with an arrow
 * that fills in once letting go would go back.
 */
export default function EdgeSwipeBack({ onBack, layer = 'page' }: { onBack: () => void; layer?: BackSwipeLayer }) {
  const hintRef = useRef<HTMLSpanElement>(null);
  useEdgeSwipeBack(onBack, hintRef, { reduceMotion: !!useReducedMotion(), layer });

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div aria-hidden="true" className={`pointer-events-none fixed inset-0 ${BEHIND[layer]}`}>
      <span
        ref={hintRef}
        data-armed="false"
        style={{ opacity: 0 }}
        className="absolute left-3 top-1/2 flex h-11 w-11 items-center justify-center rounded-full border-[1.5px] border-outline bg-surface text-foreground transition-colors duration-150 data-[armed=true]:bg-accent data-[armed=true]:text-accent-fg"
      >
        <ArrowLeft className="h-5 w-5" strokeWidth={2.25} />
      </span>
    </div>,
    document.body,
  );
}
