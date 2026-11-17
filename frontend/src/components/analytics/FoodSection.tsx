'use client';

import type { Analytics } from '@/types/analytics';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';
import BarList from './charts/BarList';
import { Card, CardTitle, Empty, GROUP_TONES, Stamp, Swatch } from './parts';
import { SectionHeading } from '@/components/dashboard/RowParts';

/** Labeling is still under way while less than this much is done. */
const LABELED_ENOUGH = 0.95;

/** What the person ate and drank, where the money went, and the champions. */
export default function FoodSection({ data }: { data: Analytics }) {
  const { t, language } = useTranslation();
  const { food, currency } = data;
  const money = (amount: number) => formatCurrency(amount, currency);
  const spent = food.groups.reduce((sum, group) => sum + group.amount, 0);

  if (food.groups.length === 0 && food.top.length === 0) {
    return <Empty title={t('analytics.noFood')} />;
  }

  return (
    <div className="flex flex-col gap-3.5">
      {food.labeled < LABELED_ENOUGH && (
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-[12px] text-muted">
          {t('analytics.labeling', { percent: String(Math.round(food.labeled * 100)) })}
        </p>
      )}

      {spent > 0 && (
        <Card>
          <CardTitle>{t('analytics.groupsTitle')}</CardTitle>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {food.groups.map((group) => {
              const share = Math.round((group.amount / spent) * 100);
              return (
                <li key={group.group}>
                  <div className="flex items-baseline gap-2 text-[14px] text-foreground">
                    <Swatch tone={GROUP_TONES[group.group]} />
                    <span>{t(`analytics.groups.${group.group}`)}</span>
                    <span className="flex-1" />
                    <span className="font-mono text-[13px] font-bold tabular-nums">{money(group.amount)}</span>
                    <span className="w-9 text-right font-mono text-[11px] text-muted">{share}%</span>
                  </div>
                  <div className="mt-1.5 h-2 rounded-[4px] bg-surface-2" aria-hidden>
                    <div className={`h-2 rounded-[4px] ${GROUP_TONES[group.group]}`} style={{ width: `${Math.max(2, (group.amount / food.groups[0].amount) * 100)}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {food.champions.length > 0 && (
        <section>
          <SectionHeading title={t('analytics.champions')} />
          <ul className="m-0 grid list-none grid-cols-2 gap-2.5 p-0">
            {food.champions.map((champion) => {
              const often = t('analytics.often', { count: String(champion.often_count) });
              const priciest = t('analytics.priciest', { amount: money(champion.priciest_price) });
              const entries = champion.often === champion.priciest
                ? [{ labels: [often, priciest], dish: champion.often }]
                : [{ labels: [often], dish: champion.often }, { labels: [priciest], dish: champion.priciest }];
              return (
                <li key={champion.kind} className="rounded-lg border-[1.5px] border-outline bg-surface">
                  <div className="border-b-[1.5px] border-dashed border-border px-3 py-2 font-display text-[13px] font-extrabold uppercase tracking-[0.1em] text-foreground">
                    {champion.name}
                  </div>
                  <div className="flex flex-col gap-1.5 px-3 pb-2.5 pt-2">
                    {entries.map(({ labels, dish }) => (
                      <div key={labels.join()}>
                        {labels.map((label) => (
                          <div key={label} className="font-mono text-[10px] uppercase text-muted">{label}</div>
                        ))}
                        <div className="break-words text-[13px] font-semibold text-foreground">{dish}</div>
                      </div>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {food.top.length > 0 && (
        <Card>
          <CardTitle aside={t('analytics.times')}>{t('analytics.topDishes')}</CardTitle>
          <BarList rows={food.top.map((dish) => ({ key: dish.kind ?? dish.name, label: dish.name, value: dish.count, shown: String(dish.count) }))} />
        </Card>
      )}

      {food.price_rises.map((rise) => (
        <Card key={`${rise.place}-${rise.dish}`}>
          <div className="font-mono text-[10px] uppercase text-muted">{t('analytics.priceRise')}</div>
          <div className="mt-1 font-display text-[16px] font-bold text-foreground">{rise.dish}</div>
          <div className="mt-2.5 flex flex-wrap items-center gap-3">
            <span className="font-mono text-[15px] text-muted line-through">{money(rise.first_price)}</span>
            <span className="font-mono text-[20px] font-bold text-foreground">{money(rise.last_price)}</span>
            <Stamp tone="danger">+{new Intl.NumberFormat(language, { maximumFractionDigits: 0 }).format(rise.change)}%</Stamp>
          </div>
          <div className="mt-1.5 text-[12px] text-muted">
            {t('analytics.priceRiseHint', {
              place: rise.place,
              date: new Intl.DateTimeFormat(language, { day: 'numeric', month: 'long' }).format(new Date(rise.since)),
            })}
          </div>
        </Card>
      ))}

      {food.fees > 0 && (
        <p className="rounded-lg bg-surface-2 px-3 py-2.5 text-[13px] text-foreground">
          {t('analytics.fees', { amount: money(food.fees) })}
        </p>
      )}
    </div>
  );
}
