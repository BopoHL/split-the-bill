import { useStore } from '@/lib/store/useStore';
import { type Currency, DEFAULT_CURRENCY, currencySymbolFor } from '@/lib/utils/currencyCatalog';

// Re-export the catalog so existing imports from '@/lib/utils/currency' keep
// working (Currency type, the full list, helpers).
export type { Currency };
export {
  CURRENCIES,
  CURRENCY_CODES,
  DEFAULT_CURRENCY,
  ORDERED_CURRENCIES,
  isCurrency,
  currencySymbolFor,
  tickerOf,
} from '@/lib/utils/currencyCatalog';

function readStore(): { currency?: Currency; language?: string } {
  return typeof useStore.getState === 'function' ? useStore.getState() : {};
}

function labelFor(currency: Currency, language?: string): string {
  return currencySymbolFor(currency, language);
}

/**
 * Currency label. Pass the bill's currency to label a bill's amounts; omit it
 * (creation/new-bill contexts) to use the viewer's current setting from the
 * store. A bill's amounts must always be labelled with the bill's own currency
 * so a viewer's settings change never re-denominates an existing bill. The UZS
 * word follows the viewer's UI language; USD/RUB are fixed ($ / руб).
 */
export function currencyLabel(currency?: Currency): string {
  const s = readStore();
  const cur = currency ?? (s.currency as Currency) ?? DEFAULT_CURRENCY;
  return labelFor(cur, s.language);
}

/**
 * Format an amount with thousands separators and a currency label,
 * e.g. 1250 -> "1 250 сум" / "1 250 $" / "1 250 руб". Pass the bill's currency
 * for bill amounts; omit it to use the store's current currency.
 */
export function formatCurrency(amount: number, currency?: Currency): string {
  const s = readStore();
  const cur = currency ?? (s.currency as Currency) ?? DEFAULT_CURRENCY;
  return `${formatAmount(amount)} ${labelFor(cur, s.language)}`;
}

/** An amount without its currency, e.g. 1250 -> "1 250", 12.5 -> "12.5". */
export function formatAmount(amount: number): string {
  // Round to 2 decimals first — kills binary-float tails like
  // 67199.97999999998 that come from summing/subtracting amounts. Then drop a
  // trailing ".00" / zeros and add thousands separators.
  const rounded = Math.round((amount + Number.EPSILON) * 100) / 100;
  const [intRaw, decRaw = ''] = rounded.toFixed(2).split('.');
  const intFmt = intRaw.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const dec = decRaw === '00' ? '' : `.${decRaw.replace(/0+$/, '')}`;
  return `${intFmt}${dec}`;
}

