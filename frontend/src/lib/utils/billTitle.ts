import type { Bill } from '@/types/api';

type Translator = (path: string, params?: Record<string, string>) => string;

interface DefaultBillTitleOptions {
  ownerId?: number;
  now?: Date;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * Build the default title shown as placeholder in the create-bill form.
 *
 * Strategy:
 *  - "Bill {DD MMM}" when the user has no other bills created today
 *  - "Bill {DD MMM} #N" otherwise, where N is one more than how many
 *    bills they already have today
 *
 * The locale-aware short date comes from Intl.DateTimeFormat; the
 * surrounding template is translated via i18n keys.
 */
export function buildDefaultBillTitle(
  existingBills: Bill[],
  language: string,
  t: Translator,
  options: DefaultBillTitleOptions = {},
): string {
  const now = options.now ?? new Date();
  const dateStr = new Intl.DateTimeFormat(language, {
    day: 'numeric',
    month: 'short',
  }).format(now);

  const billsForOwner =
    options.ownerId == null
      ? existingBills
      : existingBills.filter((b) => b.owner_id === options.ownerId);

  const todayCount = billsForOwner.reduce((acc, b) => {
    const created = new Date(b.created_at);
    return isSameDay(created, now) ? acc + 1 : acc;
  }, 0);

  if (todayCount === 0) return t('bill.defaultTitle', { date: dateStr });
  return t('bill.defaultTitleN', {
    date: dateStr,
    n: String(todayCount + 1),
  });
}
