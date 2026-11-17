/**
 * Dev-only Telegram WebApp mock.
 *
 * This module is imported ONLY when `isMockEnabled()` returns true
 * (see init.ts). The check uses `process.env.NODE_ENV !== 'production'`
 * so the entire branch — and this module — gets tree-shaken out of the
 * production bundle.
 *
 * Switch users with `?mockUser=leonid|alice|bob` in the URL.
 * Add new presets to MOCK_USERS below.
 */

import type { TelegramWebApp } from '@/types/telegram';

export type MockUserKey = 'leonid' | 'alice' | 'bob';

export interface MockUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  allows_write_to_pm?: boolean;
  photo_url?: string;
}

export const MOCK_USERS: Record<MockUserKey, MockUser> = {
  leonid: {
    id: 100000000,
    first_name: 'Leonid',
    last_name: 'Petrov',
    username: 'leonid_dev',
    language_code: 'ru',
    allows_write_to_pm: true,
  },
  alice: {
    id: 100000001,
    first_name: 'Alice',
    last_name: 'Tester',
    username: 'alice_dev',
    language_code: 'en',
    allows_write_to_pm: true,
  },
  bob: {
    id: 100000002,
    first_name: 'Bob',
    last_name: 'Guest',
    username: 'bob_dev',
    language_code: 'en',
    allows_write_to_pm: true,
  },
};

const STORAGE_KEY = 'stb_dev_mock_user';
const DEFAULT_USER: MockUserKey = 'leonid';

/**
 * Build a `Telegram.WebApp.initData` query-string for a mock user.
 * The backend accepts it unsigned only with ALLOW_UNSIGNED_INIT_DATA=true.
 */
export function buildMockInitData(user: MockUser): string {
  return (
    `query_id=MOCK&user=${encodeURIComponent(JSON.stringify(user))}` +
    `&auth_date=${Math.floor(Date.now() / 1000)}&hash=mock_hash`
  );
}

/** Picks user from ?mockUser=… , falls back to localStorage, then default. */
export function resolveMockUser(): { key: MockUserKey; user: MockUser } {
  let key: MockUserKey = DEFAULT_USER;
  if (typeof window !== 'undefined') {
    const fromUrl = new URLSearchParams(window.location.search).get('mockUser');
    const fromStorage = window.localStorage.getItem(STORAGE_KEY);
    const candidate = (fromUrl || fromStorage || DEFAULT_USER) as MockUserKey;
    if (candidate in MOCK_USERS) {
      key = candidate;
      // remember choice so other tabs / refreshes keep the same identity
      if (fromUrl) window.localStorage.setItem(STORAGE_KEY, key);
    }
  }
  return { key, user: MOCK_USERS[key] };
}

/** Builds a fake `window.Telegram.WebApp` and installs it. */
export function installMockWebApp(): TelegramWebApp {
  const { user } = resolveMockUser();
  const urlParams = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : new URLSearchParams();
  const startParam = urlParams.get('startapp') || urlParams.get('start_param') || undefined;

  const initData = buildMockInitData(user);

  const webApp = {
    initData,
    initDataUnsafe: {
      user,
      auth_date: Math.floor(Date.now() / 1000),
      hash: 'mock_hash',
      start_param: startParam,
    },
    version: '7.0',
    platform: 'tdesktop',
    colorScheme: 'light' as const,
    themeParams: {
      bg_color: '#fff9db',
      text_color: '#000000',
      button_color: '#fcc419',
      button_text_color: '#000000',
    },
    isExpanded: true,
    viewportHeight: typeof window !== 'undefined' ? window.innerHeight : 600,
    viewportStableHeight: typeof window !== 'undefined' ? window.innerHeight : 600,
    headerColor: '#fff9db',
    backgroundColor: '#fff9db',
    isClosingConfirmationEnabled: false,
    BackButton: noopButton(),
    MainButton: noopMainButton(),
    HapticFeedback: {
      impactOccurred: () => {},
      notificationOccurred: () => {},
      selectionChanged: () => {},
    },
    close: () => console.info('[mock] WebApp.close()'),
    ready: () => {},
    expand: () => {},
    enableClosingConfirmation: () => {},
    disableClosingConfirmation: () => {},
    onEvent: () => {},
    offEvent: () => {},
    sendData: () => {},
    openLink: (url: string) => window.open(url, '_blank'),
    openTelegramLink: (url: string) => window.open(url, '_blank'),
    openInvoice: () => {},
    showPopup: () => {},
    showAlert: (msg: string) => window.alert(msg),
    showConfirm: () => {},
    // Dev mock: prompt for the QR text so the Soliq-import flow is testable
    // without a phone camera.
    showScanQrPopup: (
      _params: { text?: string },
      cb?: (text: string) => boolean,
    ) => {
      const text = window.prompt(
        '[mock] Scan QR — paste text',
        'https://ofd.soliq.uz/check?t=LG420211643372&r=11975&c=20260619124101&s=133935061946',
      );
      if (text && cb) cb(text);
    },
    closeScanQrPopup: () => {},
    readTextFromClipboard: () => {},
    requestWriteAccess: (cb?: (granted: boolean) => void) => cb?.(true),
    requestContact: () => {},
    switchInlineQuery: () => {},
    addToHomeScreen: () => {
      console.info('[mock] WebApp.addToHomeScreen()');
      window.alert('[mock] Added to home screen');
    },
    checkHomeScreenStatus: (cb?: (status: string) => void) => cb?.('missed'),
    // Dev mock: the picture in a new tab stands in for the story editor and
    // for the saved file.
    shareToStory: (url: string, params?: { text?: string }) => {
      console.info('[mock] WebApp.shareToStory()', params?.text);
      window.open(url, '_blank');
    },
    downloadFile: (params: { url: string }) => window.open(params.url, '_blank'),
  } as unknown as TelegramWebApp;

  window.Telegram = { WebApp: webApp };
  return webApp;
}

function noopButton() {
  return {
    isVisible: false,
    onClick: () => {},
    offClick: () => {},
    show: () => {},
    hide: () => {},
  };
}

function noopMainButton() {
  return {
    text: 'CONTINUE',
    color: '#fcc419',
    textColor: '#000000',
    isVisible: false,
    isActive: true,
    isProgressVisible: false,
    setText: () => {},
    onClick: () => {},
    offClick: () => {},
    show: () => {},
    hide: () => {},
    enable: () => {},
    disable: () => {},
    showProgress: () => {},
    hideProgress: () => {},
    setParams: () => {},
  };
}
