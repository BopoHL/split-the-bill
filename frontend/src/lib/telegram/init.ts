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

  // Get initData from URL for local testing if provided
  const urlParams = new URLSearchParams(window.location.search);
  const urlInitData = urlParams.get('initData');

  const isLocalhost = typeof window !== 'undefined' && 
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

  // Force mock if we are on localhost and there's no real initData, even if the script is loaded
  const needsMock = (process.env.NODE_ENV === 'development' || isLocalhost) && 
                   (!window.Telegram?.WebApp || !window.Telegram.WebApp.initData);

  if (needsMock) {
    
    const mockUser = {
      id: 960374691,
      first_name: 'Leonid',
      last_name: 'Voronin',
      username: 'BopoH_L',
      language_code: 'ru',
      photo_url: 'https://t.me/i/userpic/320/Jf5Nm2OZPuxwxQdmCDahZyMrZ2K4IJFTopNW3dXIQOE.svg'
    };

    const mockInitData = urlInitData || `query_id=MOCK&user=${encodeURIComponent(JSON.stringify(mockUser))}&auth_date=${Math.floor(Date.now() / 1000)}&hash=mock_hash`;

    window.Telegram = {
      WebApp: {
        initData: mockInitData,
        initDataUnsafe: {
          user: mockUser,
          auth_date: Math.floor(Date.now() / 1000),
          hash: 'mock_hash',
          start_param: urlParams.get('startapp') || undefined
        },
        version: '7.0',
        platform: 'tdesktop',
        colorScheme: 'light',
        themeParams: {
          bg_color: '#fff9db',
          text_color: '#000000',
          button_color: '#fcc419',
          button_text_color: '#000000'
        },
        isExpanded: true,
        viewportHeight: 600,
        viewportStableHeight: 600,
        headerColor: '#fff9db',
        backgroundColor: '#fff9db',
        isClosingConfirmationEnabled: false,
        BackButton: {
          isVisible: false,
          onClick: () => {},
          offClick: () => {},
          show: () => {},
          hide: () => {}
        },
        MainButton: {
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
          setParams: () => {}
        },
        HapticFeedback: {
          impactOccurred: () => {},
          notificationOccurred: () => {},
          selectionChanged: () => {}
        },
        close: () => console.log('Mock WebApp closed'),
        ready: () => {},
        expand: () => {},
        enableClosingConfirmation: () => {},
        disableClosingConfirmation: () => {},
        onEvent: () => {},
        offEvent: () => {},
        sendData: () => {},
        openLink: () => {},
        openTelegramLink: () => {},
        openInvoice: () => {},
        showPopup: () => {},
        showAlert: () => {},
        showConfirm: () => {},
        showScanQrPopup: () => {},
        closeScanQrPopup: () => {},
        readTextFromClipboard: () => {},
        requestWriteAccess: () => {},
        requestContact: () => {},
        switchInlineQuery: () => {}
      } as any
    };
  } else if (!window.Telegram?.WebApp) {
    console.warn('Telegram WebApp SDK not found');
    return null;
  }

  webApp = window.Telegram.WebApp;
  
  // Expand the app to full height
  webApp.ready();
  webApp.expand();
  
  // Set header color to match theme if supported
  if ((webApp as any).setHeaderColor) {
    webApp.headerColor = webApp.themeParams.bg_color || '#fff9db';
  }
  
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
  if (typeof window === 'undefined') return false;
  
  const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  
  // In development, we allow running in a normal browser with a mock
  if (process.env.NODE_ENV === 'development' || isLocalhost) return true;
  
  return !!(window.Telegram?.WebApp && window.Telegram.WebApp.initData);
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
