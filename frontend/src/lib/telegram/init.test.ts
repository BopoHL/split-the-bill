import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from '@/types/telegram';
import { requestFullscreen, waitForTelegramWebApp } from './init';

const webApp = (): TelegramWebApp =>
  ({ initData: 'user=test' }) as TelegramWebApp;

afterEach(() => {
  vi.useRealTimers();
  delete window.Telegram;
});

describe('waitForTelegramWebApp', () => {
  it('waits for Telegram SDK after an iOS WebView resume', async () => {
    vi.useFakeTimers();
    const ready = waitForTelegramWebApp(100, 10);

    await vi.advanceTimersByTimeAsync(10);
    window.Telegram = { WebApp: webApp() };
    await vi.advanceTimersByTimeAsync(10);

    await expect(ready).resolves.toBe(true);
  });

  it('falls back after the bounded wait in a normal browser', async () => {
    vi.useFakeTimers();
    const ready = waitForTelegramWebApp(30, 10);

    await vi.advanceTimersByTimeAsync(30);

    await expect(ready).resolves.toBe(false);
  });
});

describe('requestFullscreen', () => {
  const client = (platform: string) => {
    const wa = {
      platform,
      isFullscreen: false,
      isVersionAtLeast: () => true,
      requestFullscreen: vi.fn(),
      ready: vi.fn(),
      expand: vi.fn(),
      themeParams: {},
    };
    window.Telegram = { WebApp: wa as unknown as TelegramWebApp };
    return wa;
  };

  it('reclaims the chrome strip on a phone', () => {
    const wa = client('ios');
    requestFullscreen();
    expect(wa.requestFullscreen).toHaveBeenCalled();
  });

  it('leaves desktop alone — there it would swallow the whole monitor', () => {
    for (const platform of ['tdesktop', 'macos', 'weba']) {
      const wa = client(platform);
      requestFullscreen();
      expect(wa.requestFullscreen).not.toHaveBeenCalled();
    }
  });
});

describe('initTelegramSDK', () => {
  const client = (platform: string) => {
    const wa = {
      platform,
      isFullscreen: false,
      isVersionAtLeast: () => true,
      requestFullscreen: vi.fn(),
      disableVerticalSwipes: vi.fn(),
      ready: vi.fn(),
      expand: vi.fn(),
      themeParams: {},
    };
    window.Telegram = { WebApp: wa as unknown as TelegramWebApp };
    return wa;
  };

  it('expands the viewport on a phone', async () => {
    vi.resetModules();
    const wa = client('ios');

    const { initTelegramSDK } = await import('./init');
    initTelegramSDK();

    expect(wa.expand).toHaveBeenCalled();
  });

  it('leaves the window as the client sized it on desktop and web', async () => {
    for (const platform of ['tdesktop', 'macos', 'web', 'weba']) {
      vi.resetModules();
      const wa = client(platform);

      const { initTelegramSDK } = await import('./init');
      initTelegramSDK();

      expect(wa.expand).not.toHaveBeenCalled();
    }
  });
});

describe('home screen shortcut wrappers', () => {
  const setup = async (options: {
    supported?: boolean;
    add?: () => void;
    check?: (callback: (status: 'added') => void) => void;
  } = {}) => {
    const wa = {
      platform: 'android',
      initData: 'user=test',
      isVersionAtLeast: vi.fn(() => options.supported ?? true),
      addToHomeScreen: options.add ?? vi.fn(),
      checkHomeScreenStatus: options.check ?? vi.fn(),
      onEvent: vi.fn(),
      offEvent: vi.fn(),
      ready: vi.fn(),
      expand: vi.fn(),
      themeParams: {},
    };
    window.Telegram = { WebApp: wa as unknown as TelegramWebApp };
    vi.resetModules();
    const api = await import('./init');
    return { api, wa };
  };

  it('invokes both APIs on a Bot API 8.0 client', async () => {
    const { api, wa } = await setup();
    const onStatus = vi.fn();

    expect(api.canAddToHomeScreen()).toBe(true);
    expect(api.addToHomeScreen()).toBe(true);
    expect(api.checkHomeScreenStatus(onStatus)).toBe(true);

    expect(wa.addToHomeScreen).toHaveBeenCalledTimes(1);
    expect(wa.checkHomeScreenStatus).toHaveBeenCalledWith(onStatus);
  });

  it('does not invoke shortcut APIs when the client fails the version gate', async () => {
    const { api, wa } = await setup({ supported: false });

    expect(api.canAddToHomeScreen()).toBe(false);
    expect(api.addToHomeScreen()).toBe(false);
    expect(api.checkHomeScreenStatus(vi.fn())).toBe(false);

    expect(wa.addToHomeScreen).not.toHaveBeenCalled();
    expect(wa.checkHomeScreenStatus).not.toHaveBeenCalled();
  });

  it('reports a synchronous native failure instead of claiming invocation', async () => {
    const { api } = await setup({
      add: () => {
        throw new Error('native request rejected');
      },
      check: () => {
        throw new Error('status unavailable');
      },
    });

    expect(api.addToHomeScreen()).toBe(false);
    expect(api.checkHomeScreenStatus(vi.fn())).toBe(false);
  });
});

describe('holdBackButton', () => {
  /** A fresh module per case: it caches the WebApp it saw first. */
  const setup = async () => {
    const handlers = new Set<() => void>();
    const button = {
      visible: false,
      onClick: vi.fn((handler: () => void) => handlers.add(handler)),
      offClick: vi.fn((handler: () => void) => handlers.delete(handler)),
      show: vi.fn(() => { button.visible = true; }),
      hide: vi.fn(() => { button.visible = false; }),
    };
    window.Telegram = {
      WebApp: { BackButton: button, ready: vi.fn(), expand: vi.fn(), themeParams: {} } as unknown as TelegramWebApp,
    };
    vi.resetModules();
    const api = await import('./init');
    return { api, button, press: () => handlers.forEach((handler) => handler()) };
  };

  it('keeps every screen from going back until released', async () => {
    const { api, button, press } = await setup();
    const goHome = vi.fn();
    const releaseScreen = api.showBackButton(goHome);

    const release = api.holdBackButton();
    const closeSheet = vi.fn();
    const releaseSheet = api.showBackButton(closeSheet);
    press();

    expect(button.visible).toBe(false);
    expect(goHome).not.toHaveBeenCalled();
    expect(closeSheet).not.toHaveBeenCalled();

    releaseSheet();
    release();
    press();

    expect(button.visible).toBe(true);
    expect(goHome).toHaveBeenCalledTimes(1);
    releaseScreen();
  });

  it('is released once however often the release runs', async () => {
    const { api, button } = await setup();
    const releaseScreen = api.showBackButton(vi.fn());
    const first = api.holdBackButton();
    const second = api.holdBackButton();

    first();
    first();
    expect(button.visible).toBe(false);

    second();
    expect(button.visible).toBe(true);
    releaseScreen();
  });
});
