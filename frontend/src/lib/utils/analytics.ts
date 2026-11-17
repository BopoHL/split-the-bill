import type { AnalyticsPeriod, AnalyticsPeriodQuery, PeriodKind, TimelinePoint } from '@/types/analytics';

type Translate = (path: string, params?: Record<string, string>) => string;

/** The month or year we are in, or all time. */
export function currentPeriod(kind: PeriodKind, now: Date = new Date()): AnalyticsPeriodQuery {
  if (kind === 'all') return { kind };
  if (kind === 'year') return { kind, year: now.getFullYear() };
  return { kind, year: now.getFullYear(), month: now.getMonth() + 1 };
}

/** A month or a year before or after — all time has no neighbours. */
export function shiftPeriod(period: AnalyticsPeriodQuery, step: -1 | 1): AnalyticsPeriodQuery {
  if (period.kind === 'year' && period.year) return { ...period, year: period.year + step };
  if (period.kind === 'month' && period.year && period.month) {
    const index = period.year * 12 + (period.month - 1) + step;
    return { kind: 'month', year: Math.floor(index / 12), month: (index % 12) + 1 };
  }
  return period;
}

const ordinal = (period: AnalyticsPeriodQuery) => (period.year ?? 0) * 12 + ((period.month ?? 1) - 1);

/** Whether stepping goes somewhere there were bills: not before the first one,
 *  not past today. */
export function canShift(
  period: AnalyticsPeriodQuery,
  step: -1 | 1,
  known: Pick<AnalyticsPeriod, 'first_year' | 'first_month'> | null,
  now: Date = new Date(),
): boolean {
  if (period.kind === 'all') return false;
  const next = shiftPeriod(period, step);
  if (step === 1) {
    const current = currentPeriod(period.kind, now);
    return period.kind === 'year' ? (next.year ?? 0) <= (current.year ?? 0) : ordinal(next) <= ordinal(current);
  }
  if (!known?.first_year) return false;
  if (period.kind === 'year') return (next.year ?? 0) >= known.first_year;
  return ordinal(next) >= ordinal({ kind: 'month', year: known.first_year, month: known.first_month ?? 1 });
}

/** «сен 2026», «2026», «Всё время». */
export function periodLabel(period: AnalyticsPeriodQuery, language: string, t: Translate): string {
  if (period.kind === 'all') return t('analytics.allTime');
  if (period.kind === 'year') return String(period.year);
  const month = new Intl.DateTimeFormat(language, { month: 'short' })
    .format(new Date(period.year ?? 2000, (period.month ?? 1) - 1, 1))
    .replace('.', '');
  return `${month} ${period.year}`;
}

/** The running total after each point. */
export function cumulative(points: TimelinePoint[]): number[] {
  let total = 0;
  return points.map((point) => (total += point.amount));
}

/** «1,28 млн», «640 тыс.» — short enough for an axis. */
export function compactAmount(amount: number, language: string): string {
  return new Intl.NumberFormat(language, { notation: 'compact', maximumFractionDigits: 2 }).format(amount);
}

/** The point's label on the axis: the day of a month, or the month's short name. */
export function timelineTick(key: string, language: string): string {
  const [year, month, day] = key.split('-').map(Number);
  if (day) return String(day);
  return new Intl.DateTimeFormat(language, { month: 'short' }).format(new Date(year, month - 1, 1)).replace('.', '');
}

/** «12 мин», «2 ч», «1,5 дн.». */
export function waitLabel(minutes: number, language: string, t: Translate): string {
  if (minutes < 60) return t('bill.minutesShort', { count: String(Math.max(1, minutes)) });
  if (minutes < 24 * 60) return t('bill.hoursShort', { count: new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(minutes / 60) });
  return t('analytics.daysShort', { count: new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(minutes / 1440) });
}

/** Monday-first weekday names, long («пятница») or short («пт»). */
export function weekdayNames(language: string, width: 'long' | 'short'): string[] {
  // 5 January 2026 was a Monday.
  return Array.from({ length: 7 }, (_, index) =>
    new Intl.DateTimeFormat(language, { weekday: width }).format(new Date(2026, 0, 5 + index)).replace('.', ''),
  );
}

/** The index of the largest value; the first one on a tie. */
export function peak(values: number[]): number {
  return values.reduce((best, value, index) => (value > values[best] ? index : best), 0);
}

/** A picture's address asking for it as a file to save rather than to show. */
export function downloadAddress(url: string): string {
  const address = new URL(url);
  address.searchParams.set('download', 'true');
  return address.toString();
}
