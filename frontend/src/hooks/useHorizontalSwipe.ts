import { useEffectEvent, useLayoutEffect, type RefObject } from 'react';

/** Where a swipe must not start: text entry, forms, anything rendered on top
 *  of the page, and whatever takes a sideways drag for itself (`data-no-swipe`),
 *  such as a chart followed with the finger. */
const IGNORED_TARGETS =
  'input,textarea,select,[contenteditable="true"],[data-no-swipe],[role="dialog"]';
/** Something that scrolls sideways by itself, such as a strip of receipts. */
const SIDEWAYS_SCROLLER = '[data-sideways-scroller]';
const INTENT_SLOP_PX = 8;
const HORIZONTAL_BIAS = 1.2;
const VELOCITY_WINDOW_MS = 100;
// The click a released drag produces arrives right after the touchend;
// anything later is a deliberate press.
const SWALLOW_CLICK_MS = 400;

export interface HorizontalSwipeCallbacks {
  /** The gesture has been recognised as horizontal and now belongs to the caller. */
  onSwipeStart: () => void;
  onSwipeMove: (dx: number) => void;
  /** `velocity` is in px/ms, negative towards the left. An interrupted gesture ends at 0/0. */
  onSwipeEnd: (dx: number, velocity: number) => void;
}

export interface HorizontalSwipeOptions {
  /** A strip at the left edge, in px, whose touches belong to another gesture. */
  leftEdgeReserved?: number;
  /** Also take swipes that start on the page below the element — the empty
   *  background under short content — as far as the enclosing
   *  `[data-swipe-surface]` reaches. */
  reachesPageBottom?: boolean;
}

/** The page a swipe area may reach down into. */
const SWIPE_SURFACE = '[data-swipe-surface]';

interface Gesture {
  touchId: number;
  startX: number;
  startY: number;
  locked: boolean;
  samples: { x: number; t: number }[];
  scroller: HTMLElement | null;
}

const findTouch = (touches: TouchList, id: number) =>
  Array.from(touches).find((touch) => touch.identifier === id);

/** Whether a scroller can still move the way the finger goes: a finger going
 *  left scrolls it towards its end. */
const hasRoom = (scroller: HTMLElement, dx: number) =>
  dx < 0
    ? scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 1
    : scroller.scrollLeft > 0;

/**
 * Horizontal swipe on an element, from touch events.
 *
 * Pointer events with `touch-action: pan-y` are not enough on iOS: WebKit
 * starts its own vertical pan — and cancels the pointer — as soon as a
 * sideways drag is not perfectly level. Touch events let the gesture be
 * decided here instead: once the first movement is mostly horizontal, every
 * further touchmove is cancelled so neither the page nor the Telegram viewport
 * moves; a mostly vertical one is left alone and scrolls as usual. A sideways
 * scroller under the finger keeps a horizontal drag while it has room to
 * scroll that way; one that fits, or has reached its edge, lets it through.
 *
 * One finger at a time. Touch and stylus only — a mouse drag selects text.
 */
export function useHorizontalSwipe(
  ref: RefObject<HTMLElement | null>,
  { onSwipeStart, onSwipeMove, onSwipeEnd }: HorizontalSwipeCallbacks,
  { leftEdgeReserved = 0, reachesPageBottom = false }: HorizontalSwipeOptions = {},
) {
  const start = useEffectEvent(onSwipeStart);
  const move = useEffectEvent(onSwipeMove);
  const end = useEffectEvent(onSwipeEnd);

  // Listening from the commit that puts the area on screen: a passive effect
  // runs after paint, and a touch landing in between would be lost.
  useLayoutEffect(() => {
    const area = ref.current;
    if (!area) return;
    const element = (reachesPageBottom && area.closest<HTMLElement>(SWIPE_SURFACE)) || area;
    let gesture: Gesture | null = null;
    let swipeEndedAt: number | null = null;

    const interrupt = () => {
      const current = gesture;
      gesture = null;
      if (current?.locked) end(0, 0);
    };

    const handleStart = (event: TouchEvent) => {
      interrupt();
      swipeEndedAt = null;
      // A second finger ends the swipe instead of joining it.
      if (event.touches.length > 1) return;
      const touch = event.changedTouches[0];
      if (!touch || touch.clientX <= leftEdgeReserved || (event.target as Element).closest(IGNORED_TARGETS)) return;
      // On the page around the area, only below where it starts: what is above
      // it — a header, the tabs — is not something to swipe.
      if (element !== area && !area.contains(event.target as Node) && touch.clientY < area.getBoundingClientRect().top) return;
      gesture = {
        touchId: touch.identifier,
        startX: touch.clientX,
        startY: touch.clientY,
        locked: false,
        samples: [{ x: touch.clientX, t: event.timeStamp }],
        scroller: (event.target as Element).closest<HTMLElement>(SIDEWAYS_SCROLLER),
      };
    };

    const handleMove = (event: TouchEvent) => {
      const current = gesture;
      const touch = current && findTouch(event.changedTouches, current.touchId);
      if (!current || !touch) return;
      const dx = touch.clientX - current.startX;
      const dy = touch.clientY - current.startY;

      if (!current.locked) {
        if (Math.hypot(dx, dy) < INTENT_SLOP_PX) return;
        if (Math.abs(dx) < Math.abs(dy) * HORIZONTAL_BIAS || (current.scroller && hasRoom(current.scroller, dx))) {
          gesture = null;
          return;
        }
        current.locked = true;
        start();
      }

      if (event.cancelable) event.preventDefault();
      current.samples = [
        ...current.samples.filter((sample) => event.timeStamp - sample.t < VELOCITY_WINDOW_MS),
        { x: touch.clientX, t: event.timeStamp },
      ];
      move(dx);
    };

    const handleEnd = (event: TouchEvent) => {
      const current = gesture;
      const touch = current && findTouch(event.changedTouches, current.touchId);
      if (!current || !touch) return;
      gesture = null;
      if (!current.locked) return;
      swipeEndedAt = performance.now();
      const [oldest] = current.samples;
      const elapsed = event.timeStamp - oldest.t;
      end(touch.clientX - current.startX, elapsed > 0 ? (touch.clientX - oldest.x) / elapsed : 0);
    };

    const handleCancel = (event: TouchEvent) => {
      if (gesture && findTouch(event.changedTouches, gesture.touchId)) interrupt();
    };

    // The finger lifted over whatever it started on; that is not a tap on it.
    const handleClick = (event: MouseEvent) => {
      const endedAt = swipeEndedAt;
      swipeEndedAt = null;
      if (endedAt == null || performance.now() - endedAt > SWALLOW_CLICK_MS) return;
      event.preventDefault();
      event.stopPropagation();
    };

    element.addEventListener('touchstart', handleStart, { passive: true });
    element.addEventListener('touchmove', handleMove, { passive: false });
    element.addEventListener('touchend', handleEnd);
    element.addEventListener('touchcancel', handleCancel);
    element.addEventListener('click', handleClick, true);
    return () => {
      element.removeEventListener('touchstart', handleStart);
      element.removeEventListener('touchmove', handleMove);
      element.removeEventListener('touchend', handleEnd);
      element.removeEventListener('touchcancel', handleCancel);
      element.removeEventListener('click', handleClick, true);
    };
  }, [ref, leftEdgeReserved, reachesPageBottom]);
}
