import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import { clearSessionCaches } from '@/lib/cache/sessionCache';

const needsLocalStoragePolyfill = (() => {
  try {
    return (
      typeof window !== 'undefined' &&
      typeof window.localStorage?.setItem !== 'function'
    );
  } catch {
    return true;
  }
})();

if (needsLocalStoragePolyfill) {
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };

  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: storage,
  });
}

// RTL leaves DOM nodes around between tests if you don't clean up,
// which can blow up the next test's queries.
afterEach(() => {
  cleanup();
  clearSessionCaches();
});
