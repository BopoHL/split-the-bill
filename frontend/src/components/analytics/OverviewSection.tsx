'use client';

import Link from 'next/link';
import type { Analytics, TimelinePoint } from '@/types/analytics';
import { formatCurrency } from '@/lib/utils/currency';
import { billUnit } from '@/lib/utils/plural';
import { peak, weekdayNames } from '@/lib/utils/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import CumulativeLine from './charts/CumulativeLine';
import Columns from './charts/Columns';
import { Card, CardTitle, Ledger, Stat } from './parts';
import BadgeRow from './BadgeRow';
import Locked from './Locked';

const DAY_PARTS = ['morning', 'day', 'evening', 'night'] as const;
const LOCKED_ITEMS = ['weekday', 'biggest', 'money', 'badges', 'report'] as const;

/** How much, how often and when — the period at a glance. */
export default function OverviewSection({ data }: { data: Analytics }) {
  const { t, language } = useTranslation();
  const { overview, currency, period } = data;
  const money = (amount: number) => formatCurrency(amount, currency);
  const change = overview.spent_change;
  const describePoint = (point: TimelinePoint, total: number) => {
    const [year, month, day] = point.key.split('-').map(Number);
    const date = new Intl.DateTimeFormat(language, day ? { day: 'numeric', month: 'long' } : { month: 'long', year: 'numeric' })
      .format(new Date(year, month - 1, day || 1));
    return `${date} · ${money(total)}`;
  };

  return (
    <div className="flex flex-col gap-3.5">
      <section className="px-0.5">
        <div className="font-display text-[12px] font-bold uppercase tracking-[0.14em] text-muted">{t('analytics.spent')}</div>
        <div className="mt-1.5 break-words font-mono text-[34px] font-bold leading-none tabular-nums text-foreground">{money(overview.spent)}</div>
        <div className="mt-1.5 text-[13px] text-muted">
          {t('analytics.spentHint', { bills: `${overview.bills} ${billUnit(overview.bills, language)}` })}
          {change !== null && (
            <>
              {' · '}
              <span className="font-semibold text-foreground">
                {t(period.kind === 'year' ? 'analytics.changeYear' : 'analytics.changeMonth', {
                  change: `${change > 0 ? '+' : ''}${new Intl.NumberFormat(language, { maximumFractionDigits: 0 }).format(change)}%`,
                })}
              </span>
            </>
          )}
        </div>
      </section>

      {overview.spent > 0 && (
        <Card>
          <CardTitle>{t('analytics.cumulative')}</CardTitle>
          <CumulativeLine
            // Another period starts unmarked, at its last day or month.
            key={`${period.kind}-${period.year}-${period.month}`}
            points={overview.timeline}
            language={language}
            label={`${t('analytics.cumulative')}: ${money(overview.spent)}`}
            describe={describePoint}
          />
        </Card>
      )}

      <div className="grid grid-cols-[2fr_3fr] gap-2">
        <Stat
          label={t('analytics.billsTitle')}
          value={String(overview.bills)}
          hint={t('analytics.billsSplit', { owned: String(overview.owned), joined: String(overview.joined) })}
        />
        <Stat
          label={t('analytics.averageBill')}
          value={money(overview.average_bill)}
          hint={t('analytics.averageShareHint', { amount: money(overview.average_share) })}
        />
      </div>

      {data.locked ? (
        <Locked title={t('analytics.locked.overview')} items={LOCKED_ITEMS.map((item) => t(`analytics.lockedItem.${item}`))} />
      ) : (
        <Details data={data} />
      )}
    </div>
  );
}

/** The overview below its top: when, the extremes, the money both ways, badges. */
function Details({ data }: { data: Analytics }) {
  const { t, language } = useTranslation();
  const { overview, currency } = data;
  const money = (amount: number) => formatCurrency(amount, currency);
  const longDays = weekdayNames(language, 'long');
  const busiest = peak(overview.weekdays);

  return (
    <>
      <Card>
        <CardTitle>{t('analytics.busiestDay', { day: longDays[busiest] })}</CardTitle>
        <Columns
          values={overview.weekdays}
          labels={weekdayNames(language, 'short')}
          label={t('analytics.busiestDay', { day: longDays[busiest] })}
          highlight={busiest}
        />
        <p className="mt-2.5 text-[13px] text-muted">
          {t('analytics.mostOften', { part: t(`analytics.parts.${DAY_PARTS[peak(overview.day_parts)]}`) })}
        </p>
      </Card>

      {overview.biggest && (
        <Link href={`/bill/${overview.biggest.id}`} className="block rounded-lg border-[1.5px] border-outline bg-surface text-foreground">
          <div className="flex items-start justify-between gap-3 px-4 pb-3 pt-3.5">
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase text-muted">{t('analytics.biggest')}</div>
              <div className="mt-1 truncate font-display text-[16px] font-semibold">{overview.biggest.title || t('bill.untitled')}</div>
              <div className="text-[12px] text-muted">
                {new Intl.DateTimeFormat(language, { day: 'numeric', month: 'long' }).format(new Date(overview.biggest.created_at))}
                {' · '}
                {t('analytics.peopleCount', { count: String(overview.biggest.people) })}
              </div>
            </div>
            <div className="shrink-0 text-right font-mono">
              <div className="text-[17px] font-bold tabular-nums">{money(overview.biggest.total)}</div>
              {overview.biggest.share > 0 && (
                <div className="text-[11px] text-muted">{t('analytics.yourShare', { amount: money(overview.biggest.share) })}</div>
              )}
            </div>
          </div>
          {overview.smallest && (
            <>
              <div className="relative border-t-[1.5px] border-dashed border-border" aria-hidden>
                <span className="absolute -left-2 top-0 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-[1.5px] border-outline bg-background" />
                <span className="absolute -right-2 top-0 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-[1.5px] border-outline bg-background" />
              </div>
              <div className="px-4 py-2.5 text-[13px] text-muted">
                {t('analytics.smallest', { title: overview.smallest.title || t('bill.untitled'), amount: money(overview.smallest.total) })}
              </div>
            </>
          )}
        </Link>
      )}

      {(overview.collected > 0 || overview.transferred > 0) && (
        <Ledger
          lines={[
            { key: 'collected', label: t('analytics.collected'), hint: t('analytics.collectedHint'), value: money(overview.collected) },
            { key: 'transferred', label: t('analytics.transferred'), hint: t('analytics.transferredHint'), value: money(overview.transferred) },
          ]}
        />
      )}

      {data.other_currency_bills > 0 && (
        <p className="text-center text-[12px] text-muted">{t('analytics.otherCurrency', { count: String(data.other_currency_bills) })}</p>
      )}

      {data.badges.length > 0 && <BadgeRow badges={data.badges} />}
    </>
  );
}
