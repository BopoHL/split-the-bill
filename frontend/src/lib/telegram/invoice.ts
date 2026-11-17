import { getTelegramWebApp, supportsApi } from './init';

export type InvoiceStatus = 'paid' | 'cancelled' | 'failed' | 'pending';

export function canOpenInvoice(): boolean {
  const wa = getTelegramWebApp();
  return !!wa && typeof wa.openInvoice === 'function' && supportsApi('6.1');
}

/**
 * Open Telegram's payment sheet on an invoice link and learn how it closed.
 * «paid» only says the sheet went through; Pro itself arrives with the
 * payment the server hears about, a moment later.
 */
export function openInvoice(link: string): Promise<InvoiceStatus> {
  const wa = getTelegramWebApp();
  return new Promise((resolve) => {
    if (!wa || !canOpenInvoice()) {
      resolve('failed');
      return;
    }
    try {
      wa.openInvoice(link, (status) => resolve(status as InvoiceStatus));
    } catch (error) {
      console.warn('openInvoice failed', error);
      resolve('failed');
    }
  });
}
