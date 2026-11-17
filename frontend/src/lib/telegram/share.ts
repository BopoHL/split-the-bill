import type { TelegramWebView } from '@/types/telegram';
import {
  exitFullscreen,
  isFullscreen,
  onViewportChanged,
  requestFullscreen,
  supportsApi,
} from './init';

/**
 * Sharing a prepared inline message (Bot API 8.0) — the bill's chat post.
 *
 * Talks to the client through `Telegram.WebView` rather than
 * `WebApp.shareMessage`. The SDK wrapper allows a single sheet and forgets it
 * only when the client reports how it ended; some clients never do — after a
 * send, after a swipe away — and from then on every call throws «Share message
 * is already opened» until the app is restarted. Here a sheet that never
 * reported back is simply superseded by the next one.
 */

const OPEN_SHEET = 'web_app_send_prepared_message';
const SHEET_CLOSED_EVENTS = ['prepared_message_sent', 'prepared_message_failed'];

// Long enough for a client to report the viewport change, short enough that a
// silent one doesn't look like the button did nothing.
const FULLSCREEN_SETTLE_TIMEOUT_MS = 400;

/**
 * The sheet Telegram was last asked to open, until the client says how it
 * ended. The way back to fullscreen outlives a sheet that never reported: the
 * app is still out of fullscreen because of it, so the next sheet owes it.
 */
let pendingSheet: { returnToFullscreen: boolean; stopListening: () => void } | null = null;

function webViewBridge(): TelegramWebView | null {
  if (typeof window === 'undefined') return null;
  return window.Telegram?.WebView ?? null;
}

export function canShareMessage(): boolean {
  return webViewBridge() !== null && supportsApi('8.0');
}

/**
 * Open Telegram's share sheet for a server-prepared message. Returns false when
 * the client can't show one.
 */
export function shareMessage(preparedMessageId: string): boolean {
  const bridge = webViewBridge();
  if (!bridge || !supportsApi('8.0')) return false;

  awaitSheetClosing(bridge);

  const openSheet = () =>
    bridge.postEvent(
      OPEN_SHEET,
      (error) => {
        if (error) closeSheet();
      },
      { id: preparedMessageId },
    );

  // Telegram draws the share sheet itself, over the webview, and in fullscreen
  // it lays the close and send buttons out under the status bar — far enough,
  // sometimes, that neither can be pressed. Nothing on our side reaches that
  // sheet, so the only lever is not to be in fullscreen while it is open. The
  // step out is invisible: the sheet covers the screen the whole time.
  if (isFullscreen()) {
    exitFullscreen();
    whenFullscreenSettles(openSheet);
  } else {
    openSheet();
  }
  return true;
}

function awaitSheetClosing(bridge: TelegramWebView): void {
  const returnToFullscreen = isFullscreen() || (pendingSheet?.returnToFullscreen ?? false);
  pendingSheet?.stopListening();

  const onClosed = () => closeSheet();
  SHEET_CLOSED_EVENTS.forEach((event) => bridge.onEvent(event, onClosed));
  pendingSheet = {
    returnToFullscreen,
    stopListening: () => SHEET_CLOSED_EVENTS.forEach((event) => bridge.offEvent(event, onClosed)),
  };
}

function closeSheet(): void {
  if (!pendingSheet) return;
  const { returnToFullscreen, stopListening } = pendingSheet;
  pendingSheet = null;
  stopListening();
  if (returnToFullscreen) requestFullscreen();
}

/**
 * Run once the client confirms the viewport changed, or give up waiting.
 *
 * Leaving fullscreen is a request, not an assignment — opening the sheet in the
 * same tick lays it out against the viewport we are still leaving, which is why
 * the misplaced buttons came and went. The timeout is there so a client that
 * never reports back still gets its sheet.
 */
function whenFullscreenSettles(run: () => void): void {
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    unsubscribe();
    clearTimeout(timer);
    run();
  };
  const unsubscribe = onViewportChanged(() => {
    if (!isFullscreen()) finish();
  });
  const timer = setTimeout(finish, FULLSCREEN_SETTLE_TIMEOUT_MS);
}
