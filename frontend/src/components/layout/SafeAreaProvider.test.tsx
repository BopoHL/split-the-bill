import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const telegram = vi.hoisted(() => ({
  safe: null as { top?: number; right?: number; bottom?: number; left?: number } | null,
  content: null as { top?: number; right?: number; bottom?: number; left?: number } | null,
  fullscreen: false,
  viewportCallback: null as (() => void) | null,
  unsubscribe: vi.fn(),
}));

vi.mock('@/lib/telegram/init', () => ({
  getSafeAreaInsets: () => telegram.safe,
  getContentSafeAreaInsets: () => telegram.content,
  isFullscreen: () => telegram.fullscreen,
  onViewportChanged: (callback: () => void) => {
    telegram.viewportCallback = callback;
    return telegram.unsubscribe;
  },
}));

import SafeAreaProvider from './SafeAreaProvider';

const root = document.documentElement;
const variable = (name: string) => root.style.getPropertyValue(name);

describe('SafeAreaProvider', () => {
  beforeEach(() => {
    telegram.safe = null;
    telegram.content = null;
    telegram.fullscreen = false;
    telegram.viewportCallback = null;
    telegram.unsubscribe.mockReset();
    root.classList.remove('tg-fullscreen');
    ['top', 'right', 'bottom', 'left'].forEach((edge) => {
      root.style.removeProperty(`--safe-${edge}`);
      root.style.removeProperty(`--content-safe-${edge}`);
    });
  });

  it('publishes raw and combined Telegram insets on all four edges', () => {
    telegram.safe = { top: 11, right: 12, bottom: 13, left: 14 };
    telegram.content = { top: 21, right: 22, bottom: 23, left: 24 };
    telegram.fullscreen = true;

    render(<SafeAreaProvider>content</SafeAreaProvider>);

    expect(variable('--safe-top')).toBe('11px');
    expect(variable('--safe-right')).toBe('12px');
    expect(variable('--safe-bottom')).toBe('13px');
    expect(variable('--safe-left')).toBe('14px');
    expect(variable('--content-safe-top')).toBe('32px');
    expect(variable('--content-safe-right')).toBe('34px');
    expect(variable('--content-safe-bottom')).toBe('36px');
    expect(variable('--content-safe-left')).toBe('38px');
    expect(root).toHaveClass('tg-fullscreen');
  });

  it('keeps browser fallbacks for missing and partially reported edges', () => {
    telegram.safe = { top: 7 };
    telegram.content = { right: 9 };

    render(<SafeAreaProvider>content</SafeAreaProvider>);

    expect(variable('--safe-top')).toBe('7px');
    expect(variable('--content-safe-top')).toBe('7px');
    expect(variable('--safe-right')).toBe('');
    expect(variable('--content-safe-right')).toBe('calc(var(--safe-right) + 9px)');
    expect(variable('--safe-bottom')).toBe('');
    expect(variable('--content-safe-bottom')).toBe('');
    expect(variable('--safe-left')).toBe('');
    expect(variable('--content-safe-left')).toBe('');
  });

  it('reacts to viewport and browser changes, then resets its DOM state on cleanup', () => {
    telegram.safe = { top: 1, right: 2, bottom: 3, left: 4 };
    telegram.content = { top: 5, right: 6, bottom: 7, left: 8 };
    const view = render(<SafeAreaProvider>content</SafeAreaProvider>);

    telegram.safe = null;
    telegram.content = null;
    telegram.fullscreen = true;
    act(() => telegram.viewportCallback?.());

    expect(variable('--safe-top')).toBe('');
    expect(variable('--content-safe-left')).toBe('');
    expect(root).toHaveClass('tg-fullscreen');

    telegram.safe = { top: 10 };
    act(() => window.dispatchEvent(new Event('orientationchange')));
    expect(variable('--safe-top')).toBe('10px');
    expect(variable('--content-safe-top')).toBe('10px');

    view.unmount();
    expect(telegram.unsubscribe).toHaveBeenCalledOnce();
    expect(root).not.toHaveClass('tg-fullscreen');
    expect(variable('--safe-top')).toBe('');
    expect(variable('--content-safe-top')).toBe('');

    telegram.safe = { top: 99 };
    act(() => window.dispatchEvent(new Event('resize')));
    expect(variable('--safe-top')).toBe('');
  });
});
