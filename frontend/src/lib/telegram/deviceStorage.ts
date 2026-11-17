import { getTelegramWebApp } from './init';

/**
 * Per-device persistent storage for small flags.
 *
 * Prefers Telegram DeviceStorage (Bot API 9.0+), which is durable on iOS where
 * WKWebView may evict the page's localStorage. Falls back to localStorage on
 * older clients (the home-screen feature itself needs only Bot API 8.0) and if
 * a DeviceStorage call errors.
 *
 * Reads distinguish three outcomes explicitly:
 *   - value present                       → the stored string
 *   - key absent (success, empty value)   → null, a normal "not set", NOT an error
 *   - call errored / storage unavailable  → fall back to localStorage
 */

function getDeviceStorage() {
  const wa = getTelegramWebApp();
  if (!wa?.DeviceStorage) return null;
  if (typeof wa.isVersionAtLeast === 'function' && !wa.isVersionAtLeast('9.0')) {
    return null;
  }
  return wa.DeviceStorage;
}

function localGet(key: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function localSet(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage full or disabled — best effort */
  }
}

/** Reads a key. Resolves to the stored string, or null when the key is unset. */
export function storageGet(key: string): Promise<string | null> {
  const ds = getDeviceStorage();
  if (!ds) return Promise.resolve(localGet(key));

  return new Promise((resolve) => {
    try {
      ds.getItem(key, (error, value) => {
        if (error) {
          // A real read error — not "key missing". Fall back to localStorage.
          resolve(localGet(key));
          return;
        }
        // Success: a non-empty string, or null/'' when the key was never set.
        resolve(value ? value : null);
      });
    } catch {
      resolve(localGet(key));
    }
  });
}

/** Writes a key. Best-effort; mirrors to localStorage if the device call errors. */
export function storageSet(key: string, value: string): Promise<void> {
  const ds = getDeviceStorage();
  if (!ds) {
    localSet(key, value);
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    try {
      ds.setItem(key, value, (error) => {
        if (error) localSet(key, value);
        resolve();
      });
    } catch {
      localSet(key, value);
      resolve();
    }
  });
}
