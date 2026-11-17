'use client';

import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import HomeScreenShortcutHelp from '@/components/ui/HomeScreenShortcutHelp';
import {
  addToHomeScreen as tgAddToHomeScreen,
  canAddToHomeScreen,
  checkHomeScreenStatus,
  getTelegramWebApp,
  hapticFeedback,
  onHomeScreenAdded,
} from '@/lib/telegram/init';
import { storageGet, storageSet } from '@/lib/telegram/deviceStorage';
import type { HomeScreenStatus } from '@/types/telegram';

const DISMISS_KEY = 'home_screen_prompt_dismissed';
const STATUS_CHECK_TIMEOUT_MS = 1200;
const POST_ADD_RECHECK_DELAY_MS = 700;

type ShortcutRequestState = 'idle' | 'pending' | 'unconfirmed';

/**
 * Telegram Home Screen Shortcut (Bot API 8.0).
 *
 * Invoking the native prompt is separate from confirming that an icon exists:
 * Telegram may omit `homeScreenAdded`, even after a successful installation.
 * Unknown and missed results therefore stay actionable and open recovery help;
 * only an `added` result or event is treated as installed.
 */
function useHomeScreenShortcutState() {
  const [status, setStatus] = useState<HomeScreenStatus | null>(null);
  const [dismissed, setDismissed] = useState<boolean | null>(null);
  const [requestState, setRequestState] = useState<ShortcutRequestState>('idle');
  const [platform, setPlatform] = useState<string | null>(null);

  const mountedRef = useRef(false);
  const supportedRef = useRef(false);
  const addedRef = useRef(false);
  const requestStateRef = useRef<ShortcutRequestState>('idle');
  const statusCheckIdRef = useRef(0);
  const statusTimerRef = useRef<number | null>(null);
  const postAddTimerRef = useRef<number | null>(null);

  const clearStatusTimer = useCallback(() => {
    if (statusTimerRef.current === null) return;
    window.clearTimeout(statusTimerRef.current);
    statusTimerRef.current = null;
  }, []);

  const clearPostAddTimer = useCallback(() => {
    if (postAddTimerRef.current === null) return;
    window.clearTimeout(postAddTimerRef.current);
    postAddTimerRef.current = null;
  }, []);

  const updateRequestState = useCallback((next: ShortcutRequestState) => {
    requestStateRef.current = next;
    if (mountedRef.current) setRequestState(next);
  }, []);

  const confirmAdded = useCallback(() => {
    if (!mountedRef.current) return;
    addedRef.current = true;
    statusCheckIdRef.current += 1;
    clearStatusTimer();
    clearPostAddTimer();
    setStatus('added');
    updateRequestState('idle');
  }, [clearPostAddTimer, clearStatusTimer, updateRequestState]);

  const runStatusCheck = useCallback((
    recoverPendingRequest = false,
    refreshConfirmedStatus = false,
  ) => {
    if (
      !mountedRef.current ||
      !supportedRef.current ||
      (addedRef.current && !refreshConfirmedStatus)
    ) return;

    const checkId = ++statusCheckIdRef.current;
    clearStatusTimer();

    const finish = (nextStatus: HomeScreenStatus, clientResponded = true) => {
      if (
        !mountedRef.current ||
        checkId !== statusCheckIdRef.current
      ) return;

      clearStatusTimer();
      // A silent refresh does not disprove an earlier confirmed installation.
      if (!clientResponded && addedRef.current) return;
      if (nextStatus === 'added') {
        confirmAdded();
        return;
      }

      addedRef.current = false;
      setStatus(nextStatus);
      if (nextStatus === 'unsupported') {
        supportedRef.current = false;
        updateRequestState('idle');
      } else if (
        recoverPendingRequest ||
        requestStateRef.current === 'pending'
      ) {
        updateRequestState('unconfirmed');
      }
    };

    // Some supported clients expose the method but never invoke its callback.
    // Give the client a bounded chance to answer, then keep the action usable.
    statusTimerRef.current = window.setTimeout(
      () => finish('unknown', false),
      STATUS_CHECK_TIMEOUT_MS,
    );
    checkHomeScreenStatus(finish);
  }, [clearStatusTimer, confirmAdded, updateRequestState]);

  useEffect(() => {
    mountedRef.current = true;
    const wa = getTelegramWebApp();
    const detectedPlatform = wa?.platform ?? null;
    supportedRef.current = canAddToHomeScreen();

    if (!supportedRef.current) {
      return () => {
        mountedRef.current = false;
      };
    }

    void storageGet(DISMISS_KEY)
      .then((value) => {
        if (mountedRef.current) {
          setDismissed(value === 'true');
          setPlatform(detectedPlatform);
        }
      })
      .catch(() => {
        if (mountedRef.current) {
          setDismissed(false);
          setPlatform(detectedPlatform);
        }
      });

    const offAdded = onHomeScreenAdded(confirmAdded);
    const refresh = () => {
      if (document.visibilityState === 'hidden') return;
      clearPostAddTimer();
      runStatusCheck(requestStateRef.current === 'pending', true);
    };

    wa?.onEvent('activated', refresh);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    runStatusCheck();

    return () => {
      mountedRef.current = false;
      statusCheckIdRef.current += 1;
      clearStatusTimer();
      clearPostAddTimer();
      offAdded();
      wa?.offEvent('activated', refresh);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [clearPostAddTimer, clearStatusTimer, confirmAdded, runStatusCheck]);

  const invoke = useCallback((retryFromHelp: boolean) => {
    if (
      !supportedRef.current ||
      addedRef.current ||
      requestStateRef.current === 'pending' ||
      (requestStateRef.current === 'unconfirmed' && !retryFromHelp)
    ) return;

    // Invalidate any initial check before invoking the native API. Otherwise a
    // late `missed` callback could finish this new attempt before the user has
    // returned from Telegram's prompt.
    statusCheckIdRef.current += 1;
    clearStatusTimer();
    clearPostAddTimer();
    updateRequestState('pending');

    try {
      hapticFeedback('light');
    } catch {
      // Haptics are optional and must never block the user-initiated API call.
    }

    // Keep this synchronous in the click handler: Telegram rejects native
    // shortcut requests that are no longer associated with a recent user tap.
    const invoked = tgAddToHomeScreen();
    if (!invoked) {
      updateRequestState('unconfirmed');
      return;
    }
    // Some clients fire the confirmation before the method returns.
    if (addedRef.current) return;

    postAddTimerRef.current = window.setTimeout(() => {
      postAddTimerRef.current = null;
      runStatusCheck(true);
    }, POST_ADD_RECHECK_DELAY_MS);
  }, [
    clearPostAddTimer,
    clearStatusTimer,
    runStatusCheck,
    updateRequestState,
  ]);

  const dismiss = useCallback(() => {
    setDismissed(true);
    void storageSet(DISMISS_KEY, 'true');
  }, []);

  const dismissHelp = useCallback(() => updateRequestState('idle'), [updateRequestState]);
  const add = useCallback(() => invoke(false), [invoke]);
  const retry = useCallback(() => invoke(true), [invoke]);

  return {
    status,
    isAdded: status === 'added',
    isPending: requestState === 'pending',
    showHelp: requestState === 'unconfirmed',
    platform,
    // Wait for the dismissal flag to load so a saved dismissal never flashes.
    showBanner:
      status === 'missed' &&
      dismissed === false &&
      requestState !== 'unconfirmed',
    showInSettings: status === 'missed' || status === 'unknown',
    add,
    retry,
    dismiss,
    dismissHelp,
  };
}

type HomeScreenShortcutContextValue = ReturnType<typeof useHomeScreenShortcutState>;

const HomeScreenShortcutContext = createContext<HomeScreenShortcutContextValue | null>(null);

/**
 * Owns the shortcut request once for the whole app shell. Keeping the native
 * request and its recovery dialog here prevents two consumers (the banner and
 * Settings) from issuing duplicate calls or opening duplicate dialogs.
 */
export function HomeScreenShortcutProvider({ children }: { children: ReactNode }) {
  const shortcut = useHomeScreenShortcutState();

  return createElement(
    HomeScreenShortcutContext.Provider,
    { value: shortcut },
    children,
    createElement(HomeScreenShortcutHelp, {
      isOpen: shortcut.showHelp,
      isPending: shortcut.isPending,
      platform: shortcut.platform,
      onClose: shortcut.dismissHelp,
      onRetry: shortcut.retry,
    }),
  );
}

export function useHomeScreenShortcut() {
  const shortcut = useContext(HomeScreenShortcutContext);
  if (!shortcut) {
    throw new Error('useHomeScreenShortcut must be used within HomeScreenShortcutProvider');
  }
  return shortcut;
}
