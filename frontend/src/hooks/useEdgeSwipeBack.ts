import { useEffect, useEffectEvent, type RefObject } from 'react';
import { settleTiming } from '@/lib/motion';

/** How close to the left edge a finger has to land to start going back — the
 *  strip other sideways swipes on the same screen leave to it. */
export const BACK_SWIPE_EDGE_PX = 24;
/** What a swipe carries aside: a screen with the chrome fixed over it, or a
 *  sheet laid over a screen. Each element that moves is marked
 *  `data-back-swipe-layer` with the name of what it belongs to. */
export type BackSwipeLayer = 'page' | 'paywall';
const TEXT_ENTRY = 'input,textarea,select,[contenteditable="true"]';
const INTENT_SLOP_PX = 8;
const HORIZONTAL_BIAS = 1.2;
const VELOCITY_WINDOW_MS = 100;
const COMMIT_SHARE = 0.35;
const COMMIT_VELOCITY = 0.35;

interface Gesture {
  touchId: number;
  startX: number;
  startY: number;
  locked: boolean;
  samples: { x: number; t: number }[];
  layers: HTMLElement[];
  width: number;
}

const findTouch = (touches: TouchList, id: number) =>
  Array.from(touches).find((touch) => touch.identifier === id);

// Only the swipe mounted last goes back: a sheet over a screen is closed
// before the screen underneath is left.
const owners: symbol[] = [];

/**
 * Going back by swiping in from the left edge, the way iOS pages do.
 *
 * A touch that lands within {@link BACK_SWIPE_EDGE_PX} of the edge, on the
 * `layer` rather than on something laid over it, and then moves mostly to the
 * right carries every element of that layer along. Let
 * go far or fast enough and they slide the rest of the way out before
 * `onBack` runs; otherwise they slide back. `hintRef` is drawn behind them:
 * it fades in as the page moves and is marked `data-armed` once letting go
 * would go back.
 *
 * The layers move with the `translate` property, which leaves their own
 * transforms alone and is cleared at rest, so nothing fixed inside a layer is
 * positioned against it except mid-gesture.
 */
export function useEdgeSwipeBack(
  onBack: () => void,
  hintRef: RefObject<HTMLElement | null>,
  { reduceMotion = false, layer = 'page' }: { reduceMotion?: boolean; layer?: BackSwipeLayer } = {},
) {
  const back = useEffectEvent(onBack);

  useEffect(() => {
    const me = Symbol(layer);
    owners.push(me);
    const layers = `[data-back-swipe-layer="${layer}"]`;
    let gesture: Gesture | null = null;
    let animations: Animation[] = [];

    const paint = (layers: HTMLElement[], x: number, width: number) => {
      for (const layer of layers) layer.style.translate = x > 0 ? `${x}px 0` : '';
      const hint = hintRef.current;
      if (!hint) return;
      const progress = Math.min(1, x / (width * COMMIT_SHARE));
      hint.style.opacity = String(progress);
      hint.style.transform = `translate3d(${Math.min(x / 3, 24)}px, -50%, 0) scale(${0.7 + 0.3 * progress})`;
      hint.dataset.armed = String(progress >= 1);
    };

    const stopAnimations = () => {
      for (const animation of animations) animation.cancel();
      animations = [];
    };

    const rest = (layers: HTMLElement[]) => {
      stopAnimations();
      paint(layers, 0, 1);
    };

    const settle = (layers: HTMLElement[], from: number, to: number, velocity: number, done: () => void) => {
      if (reduceMotion || layers.some((layer) => typeof layer.animate !== 'function')) {
        done();
        return;
      }
      const timing = settleTiming(Math.abs(to - from), Math.max(0, Math.sign(to - from) * velocity));
      animations = layers.map((layer) =>
        layer.animate([{ translate: `${from}px 0` }, { translate: `${to}px 0` }], timing),
      );
      const hint = hintRef.current;
      if (hint?.animate) {
        animations.push(hint.animate([{ opacity: hint.style.opacity }, { opacity: 0 }], timing));
      }
      animations[0].onfinish = done;
    };

    const handleStart = (event: TouchEvent) => {
      if (gesture?.locked || event.touches.length > 1) {
        gesture = null;
        return;
      }
      const touch = event.changedTouches[0];
      const target = event.target as Element | null;
      if (
        !touch
        || owners.at(-1) !== me
        || touch.clientX > BACK_SWIPE_EDGE_PX
        || !target?.closest(layers)
        || target.closest(TEXT_ENTRY)
        || animations.length > 0
      ) {
        return;
      }
      stopAnimations();
      gesture = {
        touchId: touch.identifier,
        startX: touch.clientX,
        startY: touch.clientY,
        locked: false,
        samples: [{ x: touch.clientX, t: event.timeStamp }],
        layers: Array.from(document.querySelectorAll<HTMLElement>(layers)),
        width: window.innerWidth,
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
        if (dx <= 0 || dx < Math.abs(dy) * HORIZONTAL_BIAS) {
          gesture = null;
          return;
        }
        current.locked = true;
      }

      if (event.cancelable) event.preventDefault();
      current.samples = [
        ...current.samples.filter((sample) => event.timeStamp - sample.t < VELOCITY_WINDOW_MS),
        { x: touch.clientX, t: event.timeStamp },
      ];
      paint(current.layers, Math.max(0, dx), current.width);
    };

    const handleEnd = (event: TouchEvent) => {
      const current = gesture;
      const touch = current && findTouch(event.changedTouches, current.touchId);
      if (!current || !touch) return;
      gesture = null;
      if (!current.locked) return;

      const x = Math.max(0, touch.clientX - current.startX);
      const [oldest] = current.samples;
      const elapsed = event.timeStamp - oldest.t;
      const velocity = elapsed > 0 ? (touch.clientX - oldest.x) / elapsed : 0;
      const goesBack = x > current.width * COMMIT_SHARE || (velocity > COMMIT_VELOCITY && x > INTENT_SLOP_PX);
      if (goesBack) {
        settle(current.layers, x, current.width, velocity, back);
      } else {
        settle(current.layers, x, 0, velocity, () => rest(current.layers));
      }
    };

    const handleCancel = (event: TouchEvent) => {
      const current = gesture;
      if (!current || !findTouch(event.changedTouches, current.touchId)) return;
      gesture = null;
      if (current.locked) rest(current.layers);
    };

    // Captured on the document, so the gesture is decided before anything on
    // the page sees the touch.
    const options = { capture: true } as const;
    document.addEventListener('touchstart', handleStart, { ...options, passive: true });
    document.addEventListener('touchmove', handleMove, { ...options, passive: false });
    document.addEventListener('touchend', handleEnd, options);
    document.addEventListener('touchcancel', handleCancel, options);
    return () => {
      owners.splice(owners.indexOf(me), 1);
      document.removeEventListener('touchstart', handleStart, options);
      document.removeEventListener('touchmove', handleMove, options);
      document.removeEventListener('touchend', handleEnd, options);
      document.removeEventListener('touchcancel', handleCancel, options);
      stopAnimations();
    };
  }, [hintRef, reduceMotion, layer]);
}
