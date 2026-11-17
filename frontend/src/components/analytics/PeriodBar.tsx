'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { AnalyticsPeriod, AnalyticsPeriodQuery, PeriodKind } from '@/types/analytics';
import { canShift, currentPeriod, periodLabel, shiftPeriod } from '@/lib/utils/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';

const KINDS: PeriodKind[] = ['month', 'year', 'all'];

/** Month, year or all time — and which month or year, a step at a time. */
export default function PeriodBar({ period, known, onChange }: {
  period: AnalyticsPeriodQuery;
  /** How far back there are bills, once the server has said. */
  known: Pick<AnalyticsPeriod, 'first_year' | 'first_month'> | null;
  onChange: (period: AnalyticsPeriodQuery) => void;
}) {
  const { t, language } = useTranslation();
  const arrow = 'flex h-10 w-10 items-center justify-center rounded-lg border-[1.5px] border-outline bg-surface text-foreground disabled:border-border disabled:bg-transparent disabled:text-muted-2';

  return (
    <div className="flex items-center gap-2">
      <div role="group" aria-label={t('analytics.period')} className="flex gap-0.5 rounded-full border-[1.5px] border-outline bg-surface p-[3px]">
        {KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            aria-pressed={period.kind === kind}
            onClick={() => onChange(currentPeriod(kind))}
            className={`min-h-9 rounded-full px-3 font-display text-[13px] font-bold transition-colors ${
              period.kind === kind ? 'bg-emphasis text-emphasis-fg' : 'text-foreground'
            }`}
          >
            {t(`analytics.${kind}`)}
          </button>
        ))}
      </div>
      <span className="flex-1" />
      {period.kind !== 'all' && (
        <>
          <button type="button" aria-label={t('analytics.previous')} disabled={!canShift(period, -1, known)} onClick={() => onChange(shiftPeriod(period, -1))} className={arrow}>
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[70px] text-center font-mono text-[13px] font-bold text-foreground" aria-live="polite">
            {periodLabel(period, language, t)}
          </span>
          <button type="button" aria-label={t('analytics.next')} disabled={!canShift(period, 1, known)} onClick={() => onChange(shiftPeriod(period, 1))} className={arrow}>
            <ChevronRight className="h-4 w-4" />
          </button>
        </>
      )}
    </div>
  );
}
