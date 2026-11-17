'use client';

import { useLayoutEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import Button from '@/components/ui/Button';
import { EASE_OUT } from '@/lib/motion';
import type { Box } from '@/lib/tour/visibility';

const GAP = 14;
const EDGE = 16;
const MAX_WIDTH = 336;
/** Room kept clear of the header and the home indicator when choosing a side. */
const CHROME = 56;

interface TourBubbleProps {
  hole: Box;
  title: string;
  text: string;
  progress: string;
  action?: { label: string; onClick: () => void };
}

/** What a step says, next to what it lights: under it when there is room,
 *  over it otherwise, with a caret pointing at it. */
export default function TourBubble({ hole, title, text, progress, action }: TourBubbleProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(160);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const width = Math.min(MAX_WIDTH, viewportWidth - EDGE * 2);
  const centerX = hole.left + hole.width / 2;
  const left = Math.min(Math.max(EDGE, centerX - width / 2), viewportWidth - EDGE - width);
  const caretX = Math.min(Math.max(18, centerX - left), width - 18);

  const holeBottom = hole.top + hole.height;
  const below = viewportHeight - holeBottom - CHROME >= height + GAP
    || viewportHeight - holeBottom >= hole.top;
  const top = below
    ? `min(${holeBottom + GAP}px, calc(100dvh - var(--content-safe-bottom) - ${height + 12}px))`
    // Clear of the tour's own Skip up in the corner.
    : `max(calc(var(--content-safe-top) + ${CHROME}px), ${hole.top - GAP - height}px)`;

  return (
    <motion.div
      ref={ref}
      role="dialog"
      aria-live="polite"
      aria-label={title}
      initial={{ opacity: 0, y: below ? 8 : -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: EASE_OUT }}
      style={{ top, left, width }}
      // Only a bubble with a button of its own takes presses; any other lets
      // them through, in case it has to sit over what it points at.
      className={`${action ? 'pointer-events-auto' : 'pointer-events-none'} fixed rounded-[10px] border-[1.5px] border-outline bg-surface p-4 text-foreground shadow-[var(--shadow-hard)]`}
    >
      <span
        aria-hidden="true"
        style={{ left: caretX - 6 }}
        className={`absolute h-3 w-3 rotate-45 border-outline bg-surface ${
          below ? '-top-[7px] border-l-[1.5px] border-t-[1.5px]' : '-bottom-[7px] border-b-[1.5px] border-r-[1.5px]'
        }`}
      />
      <p className="font-mono text-[10px] font-bold tracking-[0.12em] text-muted-2">{progress}</p>
      <h2 className="mt-1 text-balance font-display text-[16px] font-bold leading-snug">{title}</h2>
      <p className="mt-1.5 text-pretty text-[13px] font-medium leading-relaxed text-muted">{text}</p>
      {action && (
        <Button type="button" size="sm" onClick={action.onClick} className="mt-3.5 w-full">
          {action.label}
        </Button>
      )}
    </motion.div>
  );
}
