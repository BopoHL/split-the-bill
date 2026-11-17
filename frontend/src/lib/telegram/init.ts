import type { HomeScreenStatus, TelegramInsets, TelegramWebApp } from '@/types/telegram';
import { track, AnalyticsEvent } from '@/lib/analytics';

let webApp: TelegramWebApp | null = null;
const TELEGRAM_SDK_WAIT_MS = 1500;
const TELEGRAM_SDK_POLL_MS = 50;

/**
 * Whether the dev mock is allowed to run in the current build.
 *
 * The mock module is loaded out-of-band from AppShell.tsx via
 * `await import('@/lib/telegram/devMock')` behind this same guard, so
 * the chunk only enters non-production bundles. Inside this function
 * we just refuse to look at the mock module at all in prod.
 *
 * In a non-prod build it can additionally be turned off by setting
 * NEXT_PUBLIC_ENABLE_TG_MOCK=0 — useful if you want to test against a
 * real Telegram client over a tunnel without disabling the dev server.
 */
export function isDevMockEnabled(): boolean {
  if (process.env.NODE_ENV === 'production') return false;
  return process.env.NEXT_PUBLIC_ENABLE_TG_MOCK !== '0';
}

/**
 * Phone clients. Expanding the viewport and going fullscreen both exist to
 * reclaim the strip Telegram's own chrome takes on a small screen, and the
 * safe-area handling around them is written for a notch. Desktop and web
 * clients already render the mini app in a right-sized window — there the same
 * calls only blow it up to fill everything.
 */
const PHONE_PLATFORMS = ['android', 'ios'];

function isPhoneClient(wa: TelegramWebApp): boolean {
  return PHONE_PLATFORMS.includes(wa.platform);
}

/**
 * Initialize Telegram WebApp SDK.
 *
 * Pure consumer of `window.Telegram.WebApp` — does NOT install the dev
 * mock itself. The mock, when active, is installed by layout.tsx via a
 * dynamic import BEFORE this function is called. Keeping init.ts free
 * of any reference to the mock module is what lets Turbopack tree-shake
 * it out of the production bundle.
 */
export function initTelegramSDK(): TelegramWebApp | null {
  if (typeof window === 'undefined') {
    return null;
  }

  if (!window.Telegram?.WebApp) {
    console.warn('Telegram WebApp SDK not found');
    return null;
  }

  webApp = window.Telegram.WebApp;

  webApp.ready();
  if (isPhoneClient(webApp)) webApp.expand();

  // Vertical swipes otherwise collapse the mini app when the user drags the
  // content, which reads as "the page won't scroll".
  webApp.disableVerticalSwipes?.();
  requestFullscreen();

  if ((webApp as unknown as { setHeaderColor?: unknown }).setHeaderColor) {
    webApp.headerColor = webApp.themeParams.bg_color || '#fff9db';
  }

  return webApp;
}

/**
 * Whether the host client implements a given Bot API version. Clients that
 * predate the version gate don't expose `isVersionAtLeast` at all — there we
 * fall back to feature detection at the call site.
 */
export function supportsApi(version: string): boolean {
  const wa = getTelegramWebApp();
  if (!wa) return false;
  return typeof wa.isVersionAtLeast !== 'function' || wa.isVersionAtLeast(version);
}

/**
 * Go fullscreen (Bot API 8.0). Silently ignored where it doesn't belong.
 */
export function requestFullscreen(): void {
  const wa = getTelegramWebApp();
  if (!wa || typeof wa.requestFullscreen !== 'function' || !supportsApi('8.0')) return;
  if (!isPhoneClient(wa)) return;
  if (wa.isFullscreen) return;
  try {
    wa.requestFullscreen();
  } catch (err) {
    console.warn('requestFullscreen failed', err);
  }
}

export function exitFullscreen(): void {
  const wa = getTelegramWebApp();
  if (!wa || typeof wa.exitFullscreen !== 'function') return;
  wa.exitFullscreen();
}

export function isFullscreen(): boolean {
  return getTelegramWebApp()?.isFullscreen === true;
}

/**
 * Insets reported by the client. `safeArea` is the device cutout, `contentSafeArea`
 * is what Telegram's own chrome (the close/menu buttons in fullscreen) covers on
 * top of it. Absent on clients older than Bot API 8.0 — callers fall back to the
 * CSS `env(safe-area-inset-*)` values.
 */
export function getSafeAreaInsets(): TelegramInsets | null {
  return getTelegramWebApp()?.safeAreaInset ?? null;
}

export function getContentSafeAreaInsets(): TelegramInsets | null {
  return getTelegramWebApp()?.contentSafeAreaInset ?? null;
}

const VIEWPORT_EVENTS = [
  'safeAreaChanged',
  'contentSafeAreaChanged',
  'fullscreenChanged',
  'fullscreenFailed',
  'viewportChanged',
];

/**
 * Subscribe to every event that can change the usable area. Returns an
 * unsubscribe function.
 */
export function onViewportChanged(callback: () => void): () => void {
  const wa = getTelegramWebApp();
  if (!wa) return () => {};
  VIEWPORT_EVENTS.forEach((evt) => wa.onEvent(evt, callback));
  return () => VIEWPORT_EVENTS.forEach((evt) => wa.offEvent(evt, callback));
}

/**
 * Get Telegram WebApp instance.
 */
export function getTelegramWebApp(): TelegramWebApp | null {
  if (!webApp && typeof window !== 'undefined') {
    webApp = initTelegramSDK();
  }
  return webApp;
}

/**
 * Check if app is running inside Telegram (or the dev mock).
 *
 * Unlike the previous implementation this no longer trusts
 * `window.location.hostname === 'localhost'` — that branch would also
 * fire on prod when the server is hit locally, which is dangerous.
 * The dev mock now installs a real `window.Telegram.WebApp` shim, so a
 * single uniform check works for both real and mocked cases.
 */
export function isTelegramWebApp(): boolean {
  if (typeof window === 'undefined') return false;
  return !!(window.Telegram?.WebApp && window.Telegram.WebApp.initData);
}

/**
 * Telegram can restore an iOS WebView before its injected SDK is available.
 * Wait briefly before treating that resumed Mini App as an external browser.
 */
export function waitForTelegramWebApp(
  timeoutMs = TELEGRAM_SDK_WAIT_MS,
  pollMs = TELEGRAM_SDK_POLL_MS,
): Promise<boolean> {
  if (typeof window === 'undefined' || isTelegramWebApp()) {
    return Promise.resolve(isTelegramWebApp());
  }

  return new Promise((resolve) => {
    const startedAt = Date.now();
    const check = () => {
      if (isTelegramWebApp()) {
        resolve(true);
      } else if (Date.now() - startedAt >= timeoutMs) {
        resolve(false);
      } else {
        window.setTimeout(check, pollMs);
      }
    };

    window.setTimeout(check, pollMs);
  });
}

/**
 * Get current user from Telegram.
 */
export function getTelegramUser() {
  const webApp = getTelegramWebApp();
  return webApp?.initDataUnsafe?.user || null;
}

/**
 * Get start parameter from Telegram (e.g., invite code).
 */
export function getStartParam(): string | null {
  const webApp = getTelegramWebApp();
  return webApp?.initDataUnsafe?.start_param || null;
}

// Telegram's `onClick` appends handlers rather than replacing them, so a screen
// that layers over another (the photo viewer over a bill) would fire both. We
// keep a stack: the top entry owns the button, and popping restores the one
// underneath instead of hiding a button the screen below still needs.
const backHandlers: Array<() => void> = [];
// While anything holds the button, no screen may go back — it stays hidden
// and the stack underneath waits to be handed back.
let backHolds = 0;

function applyTopBackHandler() {
  const webApp = getTelegramWebApp();
  if (!webApp) return;

  const top = backHandlers[backHandlers.length - 1];
  if (top && backHolds === 0) {
    webApp.BackButton.onClick(top);
    webApp.BackButton.show();
  } else {
    webApp.BackButton.hide();
  }
}

/**
 * Take over Telegram's back button. Returns a release function.
 *
 * Releasing removes THIS handler wherever it sits in the stack rather than
 * popping the top one: a screen re-running its effect while an overlay is open
 * would otherwise drop the overlay's handler and leave the button dead.
 */
export function showBackButton(onClick: () => void): () => void {
  const webApp = getTelegramWebApp();
  if (!webApp) return () => {};

  const previous = backHandlers[backHandlers.length - 1];
  if (previous) webApp.BackButton.offClick(previous);

  backHandlers.push(onClick);
  applyTopBackHandler();

  return () => {
    const at = backHandlers.lastIndexOf(onClick);
    if (at === -1) return;

    const wasOnTop = at === backHandlers.length - 1;
    if (wasOnTop) webApp.BackButton.offClick(onClick);
    backHandlers.splice(at, 1);
    if (wasOnTop) applyTopBackHandler();
  };
}

/**
 * Keep Telegram's back button out of reach until released — for a guided walk
 * through several screens that going back mid-way would derail.
 */
export function holdBackButton(): () => void {
  const webApp = getTelegramWebApp();
  if (!webApp) return () => {};

  const top = backHandlers[backHandlers.length - 1];
  if (top && backHolds === 0) webApp.BackButton.offClick(top);
  backHolds += 1;
  applyTopBackHandler();

  let released = false;
  return () => {
    if (released) return;
    released = true;
    backHolds -= 1;
    applyTopBackHandler();
  };
}

/**
 * Trigger haptic feedback.
 */
export function hapticFeedback(type: 'light' | 'medium' | 'heavy' | 'success' | 'error' | 'warning') {
  const webApp = getTelegramWebApp();
  if (webApp) {
    if (type === 'success' || type === 'error' || type === 'warning') {
      webApp.HapticFeedback.notificationOccurred(type);
    } else {
      webApp.HapticFeedback.impactOccurred(type);
    }
  }
}

/**
 * Open a t.me link — a person's chat, a channel — in Telegram itself. The
 * Mini App stays open underneath.
 */
export function openTelegramLink(url: string) {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.openTelegramLink(url);
  } else {
    window.open(url, '_blank', 'noopener');
  }
}

/**
 * Ask the user to let the bot message them in private (Bot API 6.9+). Resolves
 * true once granted so the caller can sync reachability or trigger the bot's
 * welcome DM. Resolves false when the method is unavailable (older clients).
 */
export function requestWriteAccess(): Promise<boolean> {
  const wa = getTelegramWebApp();
  return new Promise((resolve) => {
    if (!wa || typeof wa.requestWriteAccess !== 'function') {
      resolve(false);
      return;
    }
    try {
      wa.requestWriteAccess((granted) => resolve(!!granted));
    } catch {
      resolve(false);
    }
  });
}

/**
 * Open Telegram's native QR scanner.
 *
 * `onText` is called for every code the scanner reads; return true from it to
 * close the popup (e.g. once a valid receipt link is found). Returns false if
 * the client doesn't support QR scanning (desktop/web), so the caller can fall
 * back to a photo.
 */
export function scanQrCode(
  onText: (text: string) => boolean,
  hint?: string,
): boolean {
  const wa = getTelegramWebApp();
  if (!wa || typeof wa.showScanQrPopup !== 'function') return false;
  try {
    wa.showScanQrPopup({ text: hint }, onText);
    return true;
  } catch {
    return false;
  }
}

/** Close the native QR scanner opened by scanQrCode(). */
export function closeQrScanner() {
  const wa = getTelegramWebApp();
  try {
    wa?.closeScanQrPopup?.();
  } catch {
    /* no-op */
  }
}

/**
 * Get theme from Telegram.
 */
export function getTelegramTheme(): 'light' | 'dark' {
  const webApp = getTelegramWebApp();
  return webApp?.colorScheme || 'light';
}

/**
 * Whether the Telegram client supports adding the mini app to the home screen
 * (Home Screen Shortcuts, Bot API 8.0).
 */
export function canAddToHomeScreen(): boolean {
  const wa = getTelegramWebApp();
  if (!wa || typeof wa.addToHomeScreen !== 'function') return false;
  return supportsApi('8.0');
}

/**
 * Prompt the user to add the mini app to their home screen. Returns false if
 * the client doesn't support it.
 */
export function addToHomeScreen(): boolean {
  const wa = getTelegramWebApp();
  if (
    !wa ||
    typeof wa.addToHomeScreen !== 'function' ||
    !supportsApi('8.0')
  ) return false;
  try {
    wa.addToHomeScreen();
    track(AnalyticsEvent.AddToHomeScreen, {});
    return true;
  } catch {
    return false;
  }
}

/**
 * Query whether the shortcut is already on the home screen. The callback
 * receives 'added' | 'missed' | 'unsupported' | 'unknown'. Returns false when
 * the method is unavailable (the callback won't fire).
 */
export function checkHomeScreenStatus(
  onStatus: (status: HomeScreenStatus) => void,
): boolean {
  const wa = getTelegramWebApp();
  if (
    !wa ||
    typeof wa.checkHomeScreenStatus !== 'function' ||
    !supportsApi('8.0')
  ) return false;
  try {
    wa.checkHomeScreenStatus(onStatus);
    return true;
  } catch {
    return false;
  }
}

/**
 * Subscribe to the 'homeScreenAdded' event. Returns an unsubscribe function.
 */
export function onHomeScreenAdded(callback: () => void): () => void {
  const wa = getTelegramWebApp();
  if (
    !wa ||
    typeof wa.onEvent !== 'function' ||
    typeof wa.offEvent !== 'function' ||
    !supportsApi('8.0')
  ) return () => {};
  wa.onEvent('homeScreenAdded', callback);
  return () => wa.offEvent('homeScreenAdded', callback);
}
