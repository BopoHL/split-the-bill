import { describe, expect, it, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useScrollLock } from './useScrollLock';

describe('useScrollLock', () => {
  beforeEach(() => {
    document.body.setAttribute('style', '');
    window.scrollTo(0, 0);
  });

  it('does nothing while inactive', () => {
    renderHook(() => useScrollLock(false));
    expect(document.body.style.position).toBe('');
  });

  it('pins the body and restores the scroll offset', () => {
    window.scrollY = 240;
    const { unmount } = renderHook(() => useScrollLock(true));

    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-240px');

    unmount();
    expect(document.body.style.position).toBe('');
    expect(document.body.style.top).toBe('');
  });

  it('stays locked until the outermost overlay closes', () => {
    const outer = renderHook(() => useScrollLock(true));
    const inner = renderHook(() => useScrollLock(true));

    inner.unmount();
    expect(document.body.style.position).toBe('fixed');

    outer.unmount();
    expect(document.body.style.position).toBe('');
  });
});
