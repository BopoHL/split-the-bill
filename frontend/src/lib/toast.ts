import { useStore, type ToastVariant } from '@/lib/store/useStore';

/**
 * Imperative toast — a styled in-app replacement for `alert()`. Callable from
 * anywhere (handlers, non-React code) via the store's `getState`.
 */
export function showToast(message: string, variant: ToastVariant = 'error') {
  useStore.getState().showToast(message, variant);
}
