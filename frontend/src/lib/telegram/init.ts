import type { TelegramWebApp } from '@/types/telegram';

let webApp: TelegramWebApp | null = null;

/**
 * Initialize Telegram WebApp SDK
 * Should be called once on app startup
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
  
  // Expand the app to full height
  webApp.ready();
  webApp.expand();
  
  // Set header color to match theme
  webApp.headerColor = webApp.themeParams.bg_color || '#fff9db';
  
  return webApp;
}

/**
 * Get Telegram WebApp instance
 */
export function getTelegramWebApp(): TelegramWebApp | null {
  if (!webApp && typeof window !== 'undefined') {
    webApp = initTelegramSDK();
  }
  return webApp;
}

/**
 * Check if app is running inside Telegram
 */
export function isTelegramWebApp(): boolean {
  return typeof window !== 'undefined' && !!window.Telegram?.WebApp;
}

/**
 * Get current user from Telegram
 */
export function getTelegramUser() {
  const webApp = getTelegramWebApp();
  return webApp?.initDataUnsafe?.user || null;
}

/**
 * Get start parameter from Telegram (e.g., invite code)
 */
export function getStartParam(): string | null {
  const webApp = getTelegramWebApp();
  return webApp?.initDataUnsafe?.start_param || null;
}

/**
 * Show Telegram back button
 */
export function showBackButton(onClick: () => void) {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.BackButton.onClick(onClick);
    webApp.BackButton.show();
  }
}

/**
 * Hide Telegram back button
 */
export function hideBackButton() {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.BackButton.hide();
  }
}

/**
 * Show Telegram main button
 */
export function showMainButton(text: string, onClick: () => void) {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.MainButton.setText(text);
    webApp.MainButton.onClick(onClick);
    webApp.MainButton.show();
  }
}

/**
 * Hide Telegram main button
 */
export function hideMainButton() {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.MainButton.hide();
  }
}

/**
 * Trigger haptic feedback
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
 * Close the mini app
 */
export function closeTelegramApp() {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.close();
  }
}

/**
 * Share link via Telegram
 */
export function shareLink(url: string) {
  const webApp = getTelegramWebApp();
  if (webApp) {
    webApp.openTelegramLink(url);
  }
}

/**
 * Get theme from Telegram
 */
export function getTelegramTheme(): 'light' | 'dark' {
  const webApp = getTelegramWebApp();
  return webApp?.colorScheme || 'light';
}
