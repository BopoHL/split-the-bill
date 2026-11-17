import { describe, expect, it, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useViewportRestore } from './useViewportRestore';

function setVisualViewport(props: Partial<VisualViewport>) {
  Object.defineProperty(window, 'visualViewport', {
    configurable: true,
    value: {
      scale: 1,
      offsetLeft: 0,
      pageLeft: 0,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      ...props,
    },
  });
}

function meta() {
  return document.querySelector('meta[name="viewport"]')!;
}

async function flushFrames() {
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}

describe('useViewportRestore', () => {
  beforeEach(() => {
    document.head.innerHTML =
      '<meta name="viewport" content="width=device-width, initial-scale=1">';
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  });

  it('leaves an undisturbed viewport alone', async () => {
    setVisualViewport({});
    renderHook(() => useViewportRestore());

    document.dispatchEvent(new Event('visibilitychange'));
    await flushFrames();

    expect(meta().getAttribute('content')).toBe(
      'width=device-width, initial-scale=1',
    );
  });

  it('resets a drifted viewport when the app comes back', async () => {
    setVisualViewport({ scale: 1.4, pageLeft: 60 });
    renderHook(() => useViewportRestore());

    document.dispatchEvent(new Event('visibilitychange'));
    await flushFrames();

    expect(meta().getAttribute('content')).toContain('maximum-scale=1,');
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
  });

  it('blurs the focused field before the app is backgrounded', () => {
    setVisualViewport({});
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    renderHook(() => useViewportRestore());
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));

    expect(document.activeElement).not.toBe(input);
  });
});
