'use client';

import { useEffect } from 'react';

const BASE_VIEWPORT =
  'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover';
const NUDGE_VIEWPORT =
  'width=device-width, initial-scale=1, maximum-scale=0.99, user-scalable=no, viewport-fit=cover';

function hasDrifted(vv: VisualViewport) {
  return vv.scale > 1.01 || vv.offsetLeft > 0 || vv.pageLeft > 0;
}

/**
 * Restores the viewport after the webview comes back from the background.
 *
 * Backgrounding the mini app — minimising Telegram, or opening and closing a
 * photo — makes iOS snapshot the visual viewport and restore it verbatim. If the
 * user was mid-gesture or an input was focused, that snapshot can carry a scale
 * above 1 and a horizontal offset, which is what surfaces as "the app is zoomed
 * and scrolls sideways". `user-scalable=no` doesn't help: nothing is zooming,
 * the state is being replayed.
 *
 * iOS only re-applies `maximum-scale` when the meta tag actually changes, so we
 * nudge it to a different value for one frame and put it back.
 */
export function useViewportRestore() {
  useEffect(() => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');

    const reset = () => {
      const vv = window.visualViewport;
      if (!vv || !hasDrifted(vv)) return;

      if (meta) {
        meta.setAttribute('content', NUDGE_VIEWPORT);
        requestAnimationFrame(() => meta.setAttribute('content', BASE_VIEWPORT));
      }
      window.scrollTo(0, 0);
    };

    let frame = 0;
    const scheduleReset = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(reset);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        // Leaving with a focused input is what produces a zoomed snapshot.
        (document.activeElement as HTMLElement | null)?.blur();
        return;
      }
      scheduleReset();
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pageshow', scheduleReset);
    window.addEventListener('focus', scheduleReset);
    window.visualViewport?.addEventListener('resize', scheduleReset);
    window.visualViewport?.addEventListener('scroll', scheduleReset);

    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pageshow', scheduleReset);
      window.removeEventListener('focus', scheduleReset);
      window.visualViewport?.removeEventListener('resize', scheduleReset);
      window.visualViewport?.removeEventListener('scroll', scheduleReset);
    };
  }, []);
}

/**
 * Imperative escape hatch for flows that hand the screen to a native surface —
 * the Telegram photo viewer, the camera, the file picker. Blur first so the
 * webview is snapshotted without a focused input.
 */
export function blurBeforeNativeSurface() {
  (document.activeElement as HTMLElement | null)?.blur();
}
