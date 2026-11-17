'use client';

import { useEffect, useState } from 'react';
import type { OwedSummary } from '@/types/api';
import { getOwed } from '@/lib/api/reminders';
import { formatCurrency } from '@/lib/utils/currency';
import { peopleUnit } from '@/lib/utils/plural';
import { useTranslation } from '@/lib/i18n/useTranslation';

/** What others owe the viewer, said where reminders are sold: the money the
 *  reminders are there to bring back. Nothing while nobody owes. */
export default function OwedNote({ userId }: { userId: number }) {
  const { t, language } = useTranslation();
  const [owed, setOwed] = useState<OwedSummary | null>(null);

  useEffect(() => {
    let current = true;
    getOwed(userId)
      .then((summary) => current && setOwed(summary))
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [userId]);

  if (!owed || owed.people === 0 || owed.totals.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border-[1.5px] border-outline bg-surface px-3 py-2 shadow-[var(--shadow-hard-sm)]">
      <span className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{t('home.owedTitle')}</span>
      <span className="font-mono text-[18px] font-bold tabular-nums">
        {owed.totals.map((total) => formatCurrency(total.amount, total.currency)).join(' + ')}
      </span>
      <span className="font-mono text-[12px] text-muted">
        {owed.people} {peopleUnit(owed.people, language)}
      </span>
    </div>
  );
}
