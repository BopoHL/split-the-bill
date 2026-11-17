/** The app's settle curve: quick start, long soft landing. */
export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

/** A whole screen moving over: gathers pace, then settles long — the way a
 *  sheet slides on iOS. EASE_OUT's jump from rest is too abrupt at this size. */
export const EASE_SLIDE = [0.32, 0.72, 0, 1] as const;

const SETTLE_MIN_MS = 180;
const SETTLE_MAX_MS = 380;

/**
 * How something dragged travels the rest of the way once let go, in px and
 * px/ms. The curve starts at the finger's own pace — letting go continues the
 * drag instead of snapping away from it — and eases into place; from rest (a
 * tap, a slow release) it speeds up gently first. Longer distances take a
 * little longer.
 */
export function settleTiming(distance: number, speed: number): KeyframeAnimationOptions {
  const byDistance = 200 + distance * 0.6;
  const bySpeed = speed > 0 ? (2 * distance) / speed : Infinity;
  const duration = Math.min(SETTLE_MAX_MS, Math.max(SETTLE_MIN_MS, Math.min(byDistance, bySpeed)));
  const startSlope = distance > 0 ? (speed * duration) / distance : 0;
  const x1 = 0.3;
  const y1 = Math.min(1, startSlope * x1);
  return { duration, easing: `cubic-bezier(${x1}, ${y1.toFixed(3)}, 0.25, 1)`, fill: 'forwards' };
}
