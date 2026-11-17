// Single source of truth for the currencies a bill can be denominated in.
// Kept free of any store/React imports so it can be used from the store, types
// and pure helpers without circular dependencies.

export type Currency =
  | 'usd'
  | 'eur'
  | 'rub'
  | 'byn'
  | 'uzs'
  | 'kzt'
  | 'kgs'
  | 'tjs'
  | 'tmt'
  | 'gbp'
  | 'try'
  | 'aed'
  | 'uah'
  | 'gel'
  | 'azn'
  | 'cny';

/** The money bills are split in here; what a fresh profile and the picker start from. */
export const DEFAULT_CURRENCY: Currency = 'uzs';

export interface CurrencyMeta {
  /** Lowercase internal code, e.g. 'usd'. */
  code: Currency;
  /** Official ticker shown in settings and bill creation, e.g. 'USD'. */
  ticker: string;
  /** Country flag emoji. */
  flag: string;
}

// Display order: USD first, then the regionally relevant ones.
export const CURRENCIES: CurrencyMeta[] = [
  { code: 'usd', ticker: 'USD', flag: '🇺🇸' },
  { code: 'eur', ticker: 'EUR', flag: '🇪🇺' },
  { code: 'rub', ticker: 'RUB', flag: '🇷🇺' },
  { code: 'byn', ticker: 'BYN', flag: '🇧🇾' },
  { code: 'uzs', ticker: 'UZS', flag: '🇺🇿' },
  { code: 'kzt', ticker: 'KZT', flag: '🇰🇿' },
  { code: 'kgs', ticker: 'KGS', flag: '🇰🇬' },
  { code: 'tjs', ticker: 'TJS', flag: '🇹🇯' },
  { code: 'tmt', ticker: 'TMT', flag: '🇹🇲' },
  { code: 'gbp', ticker: 'GBP', flag: '🇬🇧' },
  { code: 'try', ticker: 'TRY', flag: '🇹🇷' },
  { code: 'aed', ticker: 'AED', flag: '🇦🇪' },
  { code: 'uah', ticker: 'UAH', flag: '🇺🇦' },
  { code: 'gel', ticker: 'GEL', flag: '🇬🇪' },
  { code: 'azn', ticker: 'AZN', flag: '🇦🇿' },
  { code: 'cny', ticker: 'CNY', flag: '🇨🇳' },
];

export const CURRENCY_CODES: Currency[] = CURRENCIES.map((c) => c.code);

export function isCurrency(value: unknown): value is Currency {
  return typeof value === 'string' && (CURRENCY_CODES as string[]).includes(value);
}

// UZS keeps its per-UI-language word (сум / so'm / uzs); every other currency
// uses a fixed short label next to amounts — a real symbol where one is widely
// recognised, otherwise the ticker.
const UZS_BY_LANG: Record<string, string> = { ru: 'сум', uz: "so'm", en: 'uzs' };

const SYMBOLS: Record<Currency, string> = {
  usd: '$',
  eur: '€',
  rub: 'руб',
  byn: 'Br',
  uzs: '', // handled per-language below
  kzt: '₸',
  kgs: 'сом',
  tjs: 'смн',
  tmt: 'TMT',
  gbp: '£',
  try: '₺',
  aed: 'AED',
  uah: '₴',
  gel: '₾',
  azn: '₼',
  cny: '¥',
};

/** Short label placed next to amounts for the given currency. */
export function currencySymbolFor(currency: Currency, language?: string): string {
  if (currency === 'uzs') {
    return UZS_BY_LANG[language ?? 'ru'] ?? UZS_BY_LANG.ru;
  }
  return SYMBOLS[currency] || currency.toUpperCase();
}

export function tickerOf(currency: Currency): string {
  return CURRENCIES.find((c) => c.code === currency)?.ticker ?? currency.toUpperCase();
}

// The order a picker offers: the money bills are actually split in here first,
// then the rest of the catalog as listed above. A stable sort keeps the tail in
// catalog order. Shared by settings and the create-bill wizard.
export const PICKER_PRIORITY = ['uzs', 'rub', 'byn', 'usd', 'kzt'];

const priorityRank = (code: string) => {
  const index = PICKER_PRIORITY.indexOf(code);
  return index === -1 ? PICKER_PRIORITY.length : index;
};

export const ORDERED_CURRENCIES = [...CURRENCIES].sort(
  (a, b) => priorityRank(a.code) - priorityRank(b.code),
);

// Nobody pays in tiyins: a share of a bill in sums is rounded to whole sums.
const WHOLE_UNIT_CURRENCIES: ReadonlySet<Currency> = new Set(['uzs']);

/** The smallest amount a share is rounded to, in cents. Mirrors share_step() on the server. */
export function shareStepCents(currency: Currency = DEFAULT_CURRENCY): number {
  return WHOLE_UNIT_CURRENCIES.has(currency) ? 100 : 1;
}
