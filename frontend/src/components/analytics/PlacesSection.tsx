'use client';

import type { Analytics } from '@/types/analytics';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { Card, CardTitle, Empty, Stamp } from './parts';

/** Where the person goes, how often, and what a bill there comes to. */
export default function PlacesSection({ data }: { data: Analytics }) {
  const { t } = useTranslation();
  const { places, currency } = data;

  return (
    <div className="flex flex-col gap-3.5">
      {places.top.length === 0 ? (
        <Empty title={t('analytics.noPlaces')} />
      ) : (
        <Card className="py-1.5">
          <ol className="m-0 list-none divide-y-[1.5px] divide-dashed divide-border p-0">
            {places.top.map((place, index) => (
              <li key={place.id} className="flex min-h-[52px] items-center gap-3">
                <span className="w-5 font-mono text-[11px] text-muted">{String(index + 1).padStart(2, '0')}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-display text-[15px] font-semibold text-foreground">{place.name}</span>
                  {place.average_bill > 0 && (
                    <span className="block text-[12px] text-muted">{t('analytics.averageCheck', { amount: formatCurrency(place.average_bill, currency) })}</span>
                  )}
                </span>
                <span className="font-mono text-[13px] font-bold tabular-nums text-foreground">×{place.visits}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {places.new.length > 0 && (
        <Card>
          <CardTitle>{t('analytics.newPlaces')}</CardTitle>
          <div className="flex flex-wrap gap-2.5">
            {places.new.map((name, index) => (
              <Stamp key={name} tone={index % 2 ? 'ink' : 'accent'} tilt={index % 2 ? 2 : -2}>{name}</Stamp>
            ))}
          </div>
        </Card>
      )}

      {places.unplaced > 0 && (
        <p className="rounded-lg bg-surface-2 px-3 py-2.5 text-[12px] text-muted">{t('analytics.unplaced', { count: String(places.unplaced) })}</p>
      )}
    </div>
  );
}
