'use client';

import { useRef, type HTMLAttributes, type ReactNode } from 'react';
import { useScrub } from '@/hooks/useScrub';

/**
 * A chart's plot that follows the finger (see useScrub): no pager takes a
 * sideways drag that starts on it, and the page still scrolls under a
 * vertical one.
 */
export default function ScrubArea({ onScrub, children, className = '', ...rest }: HTMLAttributes<HTMLDivElement> & {
  /** Where along the plot the finger or the mouse is, from 0 to 1. */
  onScrub: (share: number) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useScrub(ref, onScrub);
  return (
    <div ref={ref} data-no-swipe className={`touch-pan-y select-none ${className}`} {...rest}>
      {children}
    </div>
  );
}
