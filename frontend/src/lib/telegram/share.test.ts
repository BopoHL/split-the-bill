import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp, TelegramWebView } from '@/types/telegram';

type Listener = () => void;
type Listeners = Record<string, Listener[]>;

const OPEN_SHEET = 'web_app_send_prepared_message';

function eventHub() {
  const listeners: Listeners = {};
  return {
    on: (name: string, cb: Listener) => {
      (listeners[name] ??= []).push(cb);
    },
    off: (name: string, cb: Listener) => {
      listeners[name] = (listeners[name] ?? []).filter((item) => item !== cb);
    },
    emit: (name: string) => [...(listeners[name] ?? [])].forEach((cb) => cb()),
    count: (name: string) => (listeners[name] ?? []).length,
  };
}

/**
 * A client the way telegram-web-app.js exposes it: `WebApp` for the version and
 * fullscreen, `WebView` for the sheet itself.
 *
 * Both modules keep state — the cached WebApp, the sheet still open — so each
 * case imports them fresh.
 */
async function setup({ fullscreen = false, platform = 'tdesktop', bot80 = true, bridge = true } = {}) {
  const app = eventHub();
  const client = eventHub();
  const wa = {
    platform,
    isFullscreen: fullscreen,
    isVersionAtLeast: () => bot80,
    ready: vi.fn(),
    expand: vi.fn(),
    requestFullscreen: vi.fn(function (this: { isFullscreen: boolean }) {
      this.isFullscreen = true;
    }),
    exitFullscreen: vi.fn(function (this: { isFullscreen: boolean }) {
      this.isFullscreen = false;
    }),
    onEvent: app.on,
    offEvent: app.off,
    themeParams: {},
  };
  const webView = {
    postEvent: vi.fn((_type: string, callback?: (error?: unknown) => void) => callback?.()),
    onEvent: client.on,
    offEvent: client.off,
  };
  window.Telegram = bridge
    ? { WebApp: wa as unknown as TelegramWebApp, WebView: webView as unknown as TelegramWebView }
    : { WebApp: wa as unknown as TelegramWebApp };
  vi.resetModules();
  const { canShareMessage, shareMessage } = await import('./share');
  return { wa, webView, app, client, canShareMessage, shareMessage };
}

afterEach(() => {
  vi.useRealTimers();
  delete window.Telegram;
});

describe('shareMessage', () => {
  it('opens the sheet through the client bridge', async () => {
    const { webView, shareMessage } = await setup();

    expect(shareMessage('prepared-1')).toBe(true);
    expect(webView.postEvent).toHaveBeenCalledWith(OPEN_SHEET, expect.any(Function), { id: 'prepared-1' });
  });

  it('opens the next sheet even when the client never reported on the last one', async () => {
    const { webView, client, shareMessage } = await setup();

    expect(shareMessage('prepared-1')).toBe(true);
    expect(shareMessage('prepared-2')).toBe(true);

    expect(webView.postEvent).toHaveBeenLastCalledWith(OPEN_SHEET, expect.any(Function), { id: 'prepared-2' });
    expect(client.count('prepared_message_sent')).toBe(1);
    expect(client.count('prepared_message_failed')).toBe(1);
  });

  it('stops listening once the client reports how the sheet ended', async () => {
    const { client, shareMessage } = await setup();

    shareMessage('prepared-1');
    client.emit('prepared_message_failed');

    expect(client.count('prepared_message_sent')).toBe(0);
    expect(client.count('prepared_message_failed')).toBe(0);
  });

  it('is unavailable below Bot API 8.0', async () => {
    const { webView, canShareMessage, shareMessage } = await setup({ bot80: false });

    expect(canShareMessage()).toBe(false);
    expect(shareMessage('prepared-1')).toBe(false);
    expect(webView.postEvent).not.toHaveBeenCalled();
  });

  it('is unavailable without the client bridge', async () => {
    const { canShareMessage, shareMessage } = await setup({ bridge: false });

    expect(canShareMessage()).toBe(false);
    expect(shareMessage('prepared-1')).toBe(false);
  });
});

describe('shareMessage in fullscreen', () => {
  it('waits for the client to leave fullscreen before opening the sheet', async () => {
    const { wa, webView, app, shareMessage } = await setup({ fullscreen: true, platform: 'ios' });

    expect(shareMessage('prepared-1')).toBe(true);
    expect(wa.exitFullscreen).toHaveBeenCalled();
    // Opening it in the same tick is what laid the sheet out against the
    // viewport we were still leaving.
    expect(webView.postEvent).not.toHaveBeenCalled();

    app.emit('fullscreenChanged');
    expect(webView.postEvent).toHaveBeenCalledWith(OPEN_SHEET, expect.any(Function), { id: 'prepared-1' });
  });

  it('opens the sheet anyway when the client never reports the viewport', async () => {
    const { webView, shareMessage } = await setup({ fullscreen: true, platform: 'ios' });
    vi.useFakeTimers();

    shareMessage('prepared-1');
    await vi.advanceTimersByTimeAsync(400);

    expect(webView.postEvent).toHaveBeenCalled();
  });

  it('puts fullscreen back once the sheet closes', async () => {
    const { wa, app, client, shareMessage } = await setup({ fullscreen: true, platform: 'ios' });

    shareMessage('prepared-1');
    app.emit('fullscreenChanged');
    expect(wa.requestFullscreen).not.toHaveBeenCalled();

    client.emit('prepared_message_sent');
    expect(wa.requestFullscreen).toHaveBeenCalledOnce();
  });

  it('still owes fullscreen after a sheet the client never reported on', async () => {
    const { wa, webView, app, client, shareMessage } = await setup({ fullscreen: true, platform: 'ios' });

    shareMessage('prepared-1');
    app.emit('fullscreenChanged');
    shareMessage('prepared-2');

    expect(webView.postEvent).toHaveBeenCalledTimes(2);
    expect(wa.requestFullscreen).not.toHaveBeenCalled();

    client.emit('prepared_message_sent');
    expect(wa.requestFullscreen).toHaveBeenCalledOnce();
  });

  it('puts fullscreen back when the bridge cannot deliver the request', async () => {
    const { wa, webView, app, shareMessage } = await setup({ fullscreen: true, platform: 'ios' });
    webView.postEvent.mockImplementation((_type, callback) => callback?.({ notAvailable: true }));

    shareMessage('prepared-1');
    app.emit('fullscreenChanged');

    expect(wa.requestFullscreen).toHaveBeenCalledOnce();
  });

  it('leaves a windowed app alone', async () => {
    // Desktop, where the app never goes fullscreen in the first place.
    const { wa, webView, shareMessage } = await setup();

    shareMessage('prepared-1');

    expect(wa.exitFullscreen).not.toHaveBeenCalled();
    expect(webView.postEvent).toHaveBeenCalled();
  });
});
