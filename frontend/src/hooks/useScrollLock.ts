'use client';

import { useEffect } from 'react';

// Nested overlays (a confirm dialog opened from a sheet) must not unlock the
// page when only the innermost one closes, so locks are counted, not toggled.
let lockCount = 0;
let savedScrollY = 0;

function lock() {
  if (lockCount++ > 0) return;

  savedScrollY = window.scrollY;
  const { style } = document.body;
  style.position = 'fixed';
  style.top = `-${savedScrollY}px`;
  style.left = '0';
  style.right = '0';
  style.width = '100%';
}

function unlock() {
  if (lockCount === 0 || --lockCount > 0) return;

  const { style } = document.body;
  style.position = '';
  style.top = '';
  style.left = '';
  style.right = '';
  style.width = '';
  window.scrollTo(0, savedScrollY);
}

/**
 * Freezes the page behind an overlay.
 *
 * `overflow: hidden` on body is ignored by iOS Safari — the page keeps scrolling
 * under the overlay and jumps to the top once it closes. Pinning the body with
 * `position: fixed` and restoring the offset afterwards is the only approach
 * that holds on iOS.
 */
export function useScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return;
    lock();
    return unlock;
  }, [active]);
}
