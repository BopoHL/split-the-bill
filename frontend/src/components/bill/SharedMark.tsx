'use client';

import { UsersRound } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

/**
 * What a line shared among everyone shows where a dish shows its people: one
 * tile for the whole table, drawn like their faces beside it.
 */
export default function SharedMark() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex h-[26px] shrink-0 items-center gap-1 rounded-[5px] border-[1.5px] border-outline bg-accent-weak px-1.5 font-display text-[11px] font-bold text-foreground shadow-[var(--shadow-hard-sm)]">
      <UsersRound aria-hidden="true" className="h-3.5 w-3.5 text-accent" strokeWidth={2.5} />
      {t('bill.sharedSection')}
    </span>
  );
}
