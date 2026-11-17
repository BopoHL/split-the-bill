/**
 * Human-friendly relative date formatting. Used on bill cards.
 *
 * Strategy:
 *  - same calendar day  → "today"
 *  - one day earlier    → "yesterday"
 *  - 2..6 days earlier  → "N days ago"
 *  - otherwise          → locale-aware short date ("3 Mar" or "3 Mar 2025"
 *                         if the year differs from today's)
 *
 * The translator function is passed in to keep this file UI-framework-
 * agnostic; pass `t` from `useTranslation()`.
 */
type Translator = (path: string, params?: Record<string, string>) => string;

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function formatRelativeDate(
  input: string | number | Date,
  language: string,
  t: Translator,
  now: Date = new Date(),
): string {
  const date = input instanceof Date ? input : new Date(input);
  if (isNaN(date.getTime())) return '';

  const daysDiff = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);

  if (daysDiff === 0) return t('date.today');
  if (daysDiff === 1) return t('date.yesterday');
  if (daysDiff > 1 && daysDiff < 7) {
    return t('date.daysAgo', { count: String(daysDiff) });
  }

  // Older than a week — fall back to absolute date.
  const sameYear = date.getFullYear() === now.getFullYear();
  return new Intl.DateTimeFormat(language, {
    day: 'numeric',
    month: 'short',
    year: sameYear ? undefined : 'numeric',
  }).format(date);
}
