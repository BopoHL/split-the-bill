'use client';

import { useEffect } from 'react';

const GESTURE_EVENTS = ['gesturestart', 'gesturechange', 'gestureend'];

/**
 * Blocks pinch-to-zoom on every platform.
 *
 * `user-scalable=no` is honoured by Android but ignored by iOS Safari, and the
 * `gesture*` events that iOS does expose don't exist in Chrome. Neither branch
 * alone is enough, so we cancel both: the Safari gesture stream and any
 * multi-touch move. Double-tap zoom is handled by `touch-action: manipulation`
 * in globals.css, and the 16px input rule there stops the focus auto-zoom.
 */
export function useZoomLock() {
  useEffect(() => {
    const prevent = (e: Event) => e.preventDefault();
    const preventMultiTouch = (e: TouchEvent) => {
      if (e.touches.length > 1) e.preventDefault();
    };

    GESTURE_EVENTS.forEach((evt) =>
      document.addEventListener(evt, prevent, { passive: false }),
    );
    document.addEventListener('touchmove', preventMultiTouch, { passive: false });

    return () => {
      GESTURE_EVENTS.forEach((evt) => document.removeEventListener(evt, prevent));
      document.removeEventListener('touchmove', preventMultiTouch);
    };
  }, []);
}
