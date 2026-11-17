// Telegram WebApp types

export interface TelegramChat {
  id: number;
  type: 'group' | 'supergroup' | 'channel';
  title: string;
  username?: string;
  photo_url?: string;
}

export interface TelegramContact {
  user_id: number;
  phone_number: string;
  first_name: string;
  last_name?: string;
}

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  allows_write_to_pm?: boolean;
  photo_url?: string;
}

export type HomeScreenStatus = 'unsupported' | 'unknown' | 'added' | 'missed';

export interface TelegramStoryParams {
  /** Up to 200 characters; 2048 for Premium subscribers. */
  text?: string;
  /** A link on the story; only Premium subscribers may post one. */
  widget_link?: { url: string; name?: string };
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    query_id?: string;
    user?: TelegramUser;
    receiver?: TelegramUser;
    chat?: TelegramChat;
    chat_type?: string;
    chat_instance?: string;
    start_param?: string;
    can_send_after?: number;
    auth_date: number;
    hash: string;
  };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  themeParams: {
    bg_color?: string;
    text_color?: string;
    hint_color?: string;
    link_color?: string;
    button_color?: string;
    button_text_color?: string;
    secondary_bg_color?: string;
  };
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  headerColor: string;
  backgroundColor: string;
  isClosingConfirmationEnabled: boolean;
  BackButton: {
    isVisible: boolean;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
    show(): void;
    hide(): void;
  };
  MainButton: {
    text: string;
    color: string;
    textColor: string;
    isVisible: boolean;
    isActive: boolean;
    isProgressVisible: boolean;
    setText(text: string): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
    show(): void;
    hide(): void;
    enable(): void;
    disable(): void;
    showProgress(leaveActive?: boolean): void;
    hideProgress(): void;
    setParams(params: {
      text?: string;
      color?: string;
      text_color?: string;
      is_active?: boolean;
      is_visible?: boolean;
    }): void;
  };
  HapticFeedback: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  close(): void;
  ready(): void;
  expand(): void;
  enableClosingConfirmation(): void;
  disableClosingConfirmation(): void;
  onEvent(eventType: string, callback: () => void): void;
  offEvent(eventType: string, callback: () => void): void;
  sendData(data: string): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, callback?: (status: string) => void): void;
  showPopup(params: {
    title?: string;
    message: string;
    buttons?: Array<{
      id?: string;
      type?: 'default' | 'ok' | 'close' | 'cancel' | 'destructive';
      text?: string;
    }>;
  }, callback?: (buttonId: string) => void): void;
  showAlert(message: string, callback?: () => void): void;
  showConfirm(message: string, callback?: (confirmed: boolean) => void): void;
  showScanQrPopup(params: { text?: string }, callback?: (text: string) => boolean): void;
  closeScanQrPopup(): void;
  readTextFromClipboard(callback?: (text: string) => void): void;
  requestWriteAccess(callback?: (granted: boolean) => void): void;
  requestContact(callback?: (granted: boolean, contact?: TelegramContact) => void): void;
  switchInlineQuery(query: string, choose_chat_types?: string[]): void;
  // Stories (Bot API 7.8)
  shareToStory?(mediaUrl: string, params?: TelegramStoryParams): void;
  // Downloads (Bot API 8.0)
  downloadFile?(params: { url: string; file_name: string }, callback?: (accepted: boolean) => void): void;
  // Home Screen Shortcuts (Bot API 8.0)
  isVersionAtLeast?(version: string): boolean;
  addToHomeScreen?(): void;
  checkHomeScreenStatus?(callback: (status: HomeScreenStatus) => void): void;
  // Fullscreen + safe areas (Bot API 8.0)
  isFullscreen?: boolean;
  requestFullscreen?(): void;
  exitFullscreen?(): void;
  safeAreaInset?: TelegramInsets;
  contentSafeAreaInset?: TelegramInsets;
  disableVerticalSwipes?(): void;
  enableVerticalSwipes?(): void;
  // Device Storage (Bot API 9.0) — persistent per-device key/value store
  DeviceStorage?: TelegramDeviceStorage;
}

export interface TelegramInsets {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface TelegramDeviceStorage {
  getItem(key: string, callback: (error: string | null, value: string | null) => void): void;
  setItem(key: string, value: string, callback?: (error: string | null, stored: boolean) => void): void;
  removeItem(key: string, callback?: (error: string | null, removed: boolean) => void): void;
  clear(callback?: (error: string | null, cleared: boolean) => void): void;
}

/** The raw channel to the client that `WebApp` is built on (telegram-web-app.js). */
export interface TelegramWebView {
  postEvent(eventType: string, callback?: (error?: unknown) => void, eventData?: unknown): void;
  onEvent(eventType: string, callback: (eventType: string, eventData: unknown) => void): void;
  offEvent(eventType: string, callback: (eventType: string, eventData: unknown) => void): void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
      WebView?: TelegramWebView;
    };
  }
}

export {};
