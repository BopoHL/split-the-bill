import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useZoomLock } from './useZoomLock';

function touchEvent(count: number) {
  const event = new Event('touchmove', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'touches', { value: new Array(count).fill({}) });
  return event;
}

describe('useZoomLock', () => {
  it('cancels multi-touch moves but leaves single-finger panning alone', () => {
    renderHook(() => useZoomLock());

    const pinch = touchEvent(2);
    document.dispatchEvent(pinch);
    expect(pinch.defaultPrevented).toBe(true);

    const pan = touchEvent(1);
    document.dispatchEvent(pan);
    expect(pan.defaultPrevented).toBe(false);
  });

  it('cancels the iOS gesture stream', () => {
    renderHook(() => useZoomLock());

    const gesture = new Event('gesturestart', { bubbles: true, cancelable: true });
    document.dispatchEvent(gesture);
    expect(gesture.defaultPrevented).toBe(true);
  });

  it('detaches its listeners on unmount', () => {
    const { unmount } = renderHook(() => useZoomLock());
    unmount();

    const pinch = touchEvent(2);
    document.dispatchEvent(pinch);
    expect(pinch.defaultPrevented).toBe(false);
  });
});
