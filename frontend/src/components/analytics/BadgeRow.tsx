'use client';

import type { Badge } from '@/types/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { Stamp } from './parts';

const TONES = ['accent', 'ink', 'success', 'danger'] as const;

/** The titles the period earned, stamped, each with the number behind it. */
export default function BadgeRow({ badges }: { badges: Badge[] }) {
  const { t } = useTranslation();

  return (
    <section aria-label={t('analytics.badges')}>
      <div className="mb-3 flex items-center gap-2.5">
        <h3 className="font-display text-[12px] font-bold uppercase tracking-[0.14em] text-muted">{t('analytics.badges')}</h3>
        <span className="h-0 flex-1 border-t-[1.5px] border-dashed border-border" aria-hidden />
      </div>
      <ul className="m-0 grid list-none grid-cols-2 gap-2.5 p-0">
        {badges.map((badge, index) => (
          <li key={badge.key} className="flex flex-col items-start gap-2 rounded-lg border-[1.5px] border-outline bg-surface p-3">
            <Stamp tone={TONES[index % TONES.length]} tilt={index % 2 ? 2 : -3}>{t(`analytics.badge.${badge.key}.title`)}</Stamp>
            <span className="text-[12px] text-muted">
              {t(`analytics.badge.${badge.key}.detail`, { value: String(badge.value), subject: badge.subject ?? '' })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
