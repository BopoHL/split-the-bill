'use client';

import type { Analytics, Companion } from '@/types/analytics';
import { formatCurrency } from '@/lib/utils/currency';
import { waitLabel } from '@/lib/utils/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import BarList from './charts/BarList';
import { Card, CardTitle, Empty, Stamp, Swatch } from './parts';

const PODIUM_HIGH = 112;
const PODIUM_LOW = 40;

/**
 * Who sits at the person's tables, who calls whom, who pays fast. Waits run
 * from minutes to days, so their bars grow on a log scale for both to show.
 */
export default function PeopleSection({ data }: { data: Analytics }) {
  const { t, language } = useTranslation();
  const { people, currency } = data;
  const money = (amount: number) => formatCurrency(amount, currency);

  if (people.companions.length === 0) return <Empty title={t('analytics.noPeople')} />;

  const podium = podiumOrder(people.companions.slice(0, 3));
  const podiumTop = people.companions[0].together;
  const most = Math.max(...people.companions.map((companion) => Math.max(companion.invited, companion.invited_me)), 1);
  const closest = people.companions[0];
  const fastest = people.speed[0];
  const slowest = people.speed.length > 1 ? people.speed[people.speed.length - 1] : null;

  return (
    <div className="flex flex-col gap-3.5">
      <Card className="pb-0">
        <CardTitle>{t('analytics.company')}</CardTitle>
        <ol className="m-0 grid list-none grid-cols-3 items-end gap-2 p-0">
          {podium.map(({ companion, place }) => (
            <li key={companion.user_id} className="flex flex-col items-center gap-1.5">
              <Face companion={companion} size={place === 1 ? 'lg' : 'md'} />
              <span className="max-w-full truncate text-[14px] font-semibold text-foreground">{companion.name}</span>
              <div
                className={`flex w-full flex-col items-center justify-center rounded-t-lg border-[1.5px] border-b-0 border-outline ${
                  place === 1 ? 'bg-emphasis text-emphasis-fg' : 'bg-surface-2 text-foreground'
                }`}
                style={{ height: PODIUM_LOW + (PODIUM_HIGH - PODIUM_LOW) * (companion.together / podiumTop) }}
              >
                <span className="font-mono text-[22px] font-bold">{companion.together}</span>
                <span className="text-[11px]">{t('analytics.billsTogether')}</span>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <Card>
        <CardTitle>{t('analytics.whoInvites')}</CardTitle>
        <div className="mb-2.5 flex justify-between text-[12px] text-muted">
          <span className="flex items-center gap-1.5"><Swatch tone="bg-chart-2" />{t('analytics.youInvite')}</span>
          <span className="flex items-center gap-1.5">{t('analytics.theyInvite')}<Swatch tone="bg-chart-1" /></span>
        </div>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {people.companions.map((companion) => (
            <li key={companion.user_id} className="grid grid-cols-[22px_minmax(0,1fr)_76px_minmax(0,1fr)_22px] items-center gap-1.5">
              <span className="text-right font-mono text-[12px] font-bold text-foreground">{companion.invited}</span>
              <span className="flex h-3 justify-end" aria-hidden>
                <span className="block h-3 rounded-l-[4px] bg-chart-2" style={{ width: `${(companion.invited / most) * 100}%` }} />
              </span>
              <span className="truncate text-center text-[13px] font-semibold text-foreground">{companion.name}</span>
              <span className="flex h-3" aria-hidden>
                <span className="block h-3 rounded-r-[4px] bg-chart-1" style={{ width: `${(companion.invited_me / most) * 100}%` }} />
              </span>
              <span className="font-mono text-[12px] font-bold text-foreground">{companion.invited_me}</span>
            </li>
          ))}
        </ul>
      </Card>

      {people.speed.length > 0 && (
        <Card>
          <CardTitle aside={t('analytics.onAverage')}>{t('analytics.speed')}</CardTitle>
          <BarList
            labelWidth="w-[72px]"
            rows={people.speed.map((entry) => ({
              key: String(entry.user_id),
              label: entry.name,
              value: Math.log1p(entry.minutes),
              shown: waitLabel(entry.minutes, language, t),
            }))}
          />
          {(fastest || slowest) && (
            <div className="mt-3 flex flex-wrap gap-2.5">
              {fastest && <Stamp tone="success">{t('analytics.fastest', { name: fastest.name ?? '' })}</Stamp>}
              {slowest && <Stamp tone="danger" tilt={2}>{t('analytics.slowest', { name: slowest.name ?? '' })}</Stamp>}
            </div>
          )}
        </Card>
      )}

      <Card>
        <div className="flex items-center gap-2.5">
          <Face companion={closest} size="md" />
          <div className="min-w-0">
            <div className="truncate font-display text-[15px] font-bold text-foreground">{t('analytics.youAnd', { name: closest.name ?? '' })}</div>
            <div className="text-[12px] text-muted">{t('analytics.togetherCount', { count: String(closest.together) })}</div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <div className="rounded-lg bg-surface-2 px-3 py-2">
            <div className="font-mono text-[10px] uppercase text-muted">{t('analytics.theyPaid')}</div>
            <div className="font-mono text-[15px] font-bold tabular-nums text-foreground">{money(closest.paid_me)}</div>
          </div>
          <div className="rounded-lg bg-surface-2 px-3 py-2">
            <div className="font-mono text-[10px] uppercase text-muted">{t('analytics.youPaid')}</div>
            <div className="font-mono text-[15px] font-bold tabular-nums text-foreground">{money(closest.paid_them)}</div>
          </div>
        </div>
      </Card>
    </div>
  );
}

/** Second, first, third — the first in the middle and tallest. */
function podiumOrder(top: Companion[]): Array<{ companion: Companion; place: number }> {
  const placed = top.map((companion, index) => ({ companion, place: index + 1 }));
  return placed.length === 3 ? [placed[1], placed[0], placed[2]] : placed;
}

function Face({ companion, size }: { companion: Companion; size: 'md' | 'lg' }) {
  const box = size === 'lg' ? 'h-12 w-12 text-[19px]' : 'h-10 w-10 text-[16px]';
  return (
    <span className={`flex shrink-0 items-center justify-center overflow-hidden rounded-[10px] border-[1.5px] border-outline bg-surface-2 font-display font-extrabold text-foreground ${box}`}>
      {companion.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={companion.avatar_url} alt="" className="h-full w-full object-cover" />
      ) : (
        (companion.name || '?').charAt(0).toUpperCase()
      )}
    </span>
  );
}
