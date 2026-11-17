'use client';

import { useEffect, useState, type RefObject } from 'react';
import { findTarget, type TourTarget } from '@/lib/tour/anchors';
import { inspectTarget, sameBox, type Box } from '@/lib/tour/visibility';

/** Wait this long before nudging a scrolled-away target into view again. */
const SCROLL_RETRY_MS = 800;
/** Something passing over the element — a sheet on its way out — is waited
 *  out; something that stays, like a docked bar, is scrolled away from. */
const COVERED_SCROLL_MS = 600;

/**
 * Where the lit element is right now, or null until it can be lit.
 *
 * Followed every frame for as long as the step lasts: the element slides with
 * a sheet, jumps when a list refreshes, scrolls with the page. One scrolled out
 * of view, or lying under a bar that stays put, is brought to the middle of the
 * screen.
 */
export function useTourTarget(
  stepId: string,
  target: TourTarget | undefined,
  ignore: RefObject<Element | null>,
): Box | null {
  const [seen, setSeen] = useState<{ stepId: string; box: Box | null }>({ stepId, box: null });

  useEffect(() => {
    if (!target) return;
    let frame = 0;
    let scrolledAt = -Infinity;
    let coveredSince: number | null = null;

    const follow = (now: number) => {
      const element = findTarget(target);
      const view = element ? inspectTarget(element, ignore.current) : null;
      coveredSince = view?.kind === 'covered' ? (coveredSince ?? now) : null;
      const outOfSight = view?.kind === 'below-fold'
        || (coveredSince != null && now - coveredSince > COVERED_SCROLL_MS);
      if (element && outOfSight && now - scrolledAt > SCROLL_RETRY_MS) {
        scrolledAt = now;
        element.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
      const box = view?.kind === 'ready' ? view.box : null;
      setSeen((previous) =>
        previous.stepId === stepId && sameBox(previous.box, box) ? previous : { stepId, box },
      );
      frame = requestAnimationFrame(follow);
    };

    frame = requestAnimationFrame(follow);
    return () => cancelAnimationFrame(frame);
  }, [stepId, target, ignore]);

  return seen.stepId === stepId ? seen.box : null;
}
