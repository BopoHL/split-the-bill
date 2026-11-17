'use client';

import Link from 'next/link';
import type { Bill } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';

/** A bill the person has paid their share of, open until the owner closes it. */
export default function SettledRow({ bill }: { bill: Bill }) {
  const { t } = useTranslation();

  return (
    <Link href={`/bill/${bill.id}`} className="flex min-h-14 items-center gap-3 px-3.5 py-2.5 text-foreground">
      <span className="min-w-0 flex-1">
        <span className="block truncate font-display text-[15px] font-semibold leading-tight">
          {bill.title || t('bill.untitled')}
        </span>
        <span className="mt-0.5 block truncate text-[12px] text-muted">
          {t('home.collectedBy', { name: bill.owner?.name ?? '' })}
        </span>
      </span>
      <span className="shrink-0 font-mono text-[14px] font-bold tabular-nums">
        {formatCurrency(bill.my_seat?.amount ?? 0, bill.currency ?? 'uzs')}
      </span>
      <span className="inline-flex shrink-0 -rotate-3 items-center rounded-[5px] border-2 border-success px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-success">
        {t('home.paidStamp')}
      </span>
    </Link>
  );
}
