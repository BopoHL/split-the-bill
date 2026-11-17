import { useEffectEvent, useLayoutEffect, type RefObject } from 'react';

const INTENT_SLOP_PX = 6;
const HORIZONTAL_BIAS = 1.2;

interface Gesture {
  touchId: number;
  startX: number;
  startY: number;
  locked: boolean;
}

const findTouch = (touches: TouchList, id: number) =>
  Array.from(touches).find((touch) => touch.identifier === id);

/**
 * Following a finger along a chart. Once a touch moves more sideways than up
 * or down it belongs to the chart — the page neither scrolls nor pages under
 * it — and every move reports where along the chart the finger is, from 0 at
 * its left edge to 1 at its right; a tap reports where it landed. A mostly
 * vertical drag is left to scroll the page, and moves nothing on the chart.
 * A mouse follows by hovering.
 *
 * Touch events rather than pointer events, as with the pagers' swipe: WebKit
 * cancels a pointer as soon as a sideways drag is not perfectly level. The
 * element should carry `data-no-swipe` so no pager takes the drag first.
 */
export function useScrub(ref: RefObject<HTMLElement | null>, onScrub: (share: number) => void) {
  const scrub = useEffectEvent(onScrub);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    let gesture: Gesture | null = null;

    const at = (clientX: number) => {
      const box = element.getBoundingClientRect();
      return box.width > 0 ? Math.min(1, Math.max(0, (clientX - box.left) / box.width)) : 0;
    };

    const handleStart = (event: TouchEvent) => {
      const touch = event.changedTouches[0];
      if (event.touches.length > 1 || !touch) {
        gesture = null;
        return;
      }
      gesture = { touchId: touch.identifier, startX: touch.clientX, startY: touch.clientY, locked: false };
    };

    const handleMove = (event: TouchEvent) => {
      const current = gesture;
      const touch = current && findTouch(event.changedTouches, current.touchId);
      if (!current || !touch) return;
      if (!current.locked) {
        const dx = touch.clientX - current.startX;
        const dy = touch.clientY - current.startY;
        if (Math.hypot(dx, dy) < INTENT_SLOP_PX) return;
        if (Math.abs(dx) < Math.abs(dy) * HORIZONTAL_BIAS) {
          gesture = null;
          return;
        }
        current.locked = true;
      }
      if (event.cancelable) event.preventDefault();
      scrub(at(touch.clientX));
    };

    const handleEnd = (event: TouchEvent) => {
      const touch = gesture && findTouch(event.changedTouches, gesture.touchId);
      if (!gesture || !touch) return;
      const tapped = event.type === 'touchend' && !gesture.locked;
      gesture = null;
      if (tapped) scrub(at(touch.clientX));
    };

    const handleHover = (event: PointerEvent) => {
      if (event.pointerType === 'mouse') scrub(at(event.clientX));
    };

    element.addEventListener('touchstart', handleStart, { passive: true });
    element.addEventListener('touchmove', handleMove, { passive: false });
    element.addEventListener('touchend', handleEnd);
    element.addEventListener('touchcancel', handleEnd);
    element.addEventListener('pointermove', handleHover);
    return () => {
      element.removeEventListener('touchstart', handleStart);
      element.removeEventListener('touchmove', handleMove);
      element.removeEventListener('touchend', handleEnd);
      element.removeEventListener('touchcancel', handleEnd);
      element.removeEventListener('pointermove', handleHover);
    };
  }, [ref]);
}
