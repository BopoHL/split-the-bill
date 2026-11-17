'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Bill } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { dayAndMonth } from '@/lib/utils/home';
import { participantUnit } from '@/lib/utils/plural';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { DeleteButton, DeleteConfirm } from './RowParts';

/** One closed bill: when, what, whose it was, the total and the person's own share. */
export default function ArchiveRow({ bill, userId, onDelete }: {
  bill: Bill;
  userId: number;
  onDelete: (billId: number) => Promise<void>;
}) {
  const { t, language } = useTranslation();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const { day, month } = dayAndMonth(bill.created_at, language);
  const currency = bill.currency ?? 'uzs';
  const mine = bill.owner_id === userId;
  const people = `${bill.participants_count} ${participantUnit(bill.participants_count, language)}`;
  const whose = mine ? t('home.yourBill') : bill.owner?.name;

  return (
    <div>
      <div className="flex items-center gap-1 pr-2">
        <Link href={`/bill/${bill.id}`} className="flex min-h-14 min-w-0 flex-1 items-center gap-3 py-2.5 pl-3.5 text-foreground">
          <span className="flex w-[34px] shrink-0 flex-col items-center font-mono" aria-hidden>
            <span className="text-[16px] font-bold leading-none">{day}</span>
            <span className="mt-[3px] text-[10px] uppercase text-muted">{month}</span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-display text-[15px] font-semibold leading-tight">
              {bill.title || t('bill.untitled')}
            </span>
            <span className="mt-0.5 block truncate text-[12px] text-muted">{whose ? `${people} · ${whose}` : people}</span>
          </span>
          <span className="shrink-0 text-right font-mono">
            <span className="block text-[14px] font-bold tabular-nums">{formatCurrency(bill.total_sum, currency)}</span>
            {bill.my_seat && bill.my_seat.amount > 0 && (
              <span className="mt-0.5 block text-[11px] text-muted">
                {t('home.yourShare', { amount: formatCurrency(bill.my_seat.amount, currency) })}
              </span>
            )}
          </span>
        </Link>
        {mine && <DeleteButton open={confirmingDelete} onToggle={() => setConfirmingDelete((open) => !open)} />}
      </div>
      {confirmingDelete && (
        <DeleteConfirm onCancel={() => setConfirmingDelete(false)} onConfirm={() => onDelete(bill.id)} />
      )}
    </div>
  );
}
