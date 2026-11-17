'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Bell, BellRing } from 'lucide-react';
import type { Bill } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { shortDuration, sinceLabel } from '@/lib/utils/reminders';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { remindersLeft, useProGate } from '@/lib/store/usePro';
import ProCorner from '@/components/pro/ProCorner';
import PaidProgress from './PaidProgress';
import { DeleteButton, DeleteConfirm } from './RowParts';

type BellState =
  | { kind: 'none' }
  | { kind: 'ready' }
  | { kind: 'waiting'; remindedAt: Date | null; nextAt: Date };

function bellOf(bill: Bill, now: Date): BellState {
  const collection = bill.collection;
  if (!collection || collection.left <= 0) return { kind: 'none' };
  if (collection.remindable > 0) return { kind: 'ready' };
  const nextAt = collection.next_reminder_at ? new Date(collection.next_reminder_at) : null;
  if (!nextAt || nextAt <= now) return { kind: 'none' };
  return { kind: 'waiting', remindedAt: collection.reminded_at ? new Date(collection.reminded_at) : null, nextAt };
}

/**
 * One bill the person collects on: who has paid, what is still owed, and the
 * bell that reminds everyone who has not — quiet for an hour once it rang.
 */
export default function CollectingRow({ bill, onRemind, onDelete }: {
  bill: Bill;
  onRemind: (bill: Bill) => Promise<void>;
  onDelete: (billId: number) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [reminding, setReminding] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const { locked, gated } = useProGate('reminders', remindersLeft);
  const now = new Date();
  const bell = bellOf(bill, now);
  const currency = bill.currency ?? 'uzs';
  const left = bill.collection?.left ?? 0;
  const everyonePaid = left <= 0 && (bill.payers_count ?? 0) > 0 && bill.payers_paid === bill.payers_count;

  const remind = async () => {
    setReminding(true);
    try {
      await onRemind(bill);
    } finally {
      setReminding(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-3 px-3.5 py-3">
        <Link href={`/bill/${bill.id}`} className="min-w-0 flex-1 text-foreground">
          <span className="block truncate font-display text-[16px] font-semibold leading-tight">
            {bill.title || t('bill.untitled')}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
            <PaidProgress bill={bill} />
            <span className="font-mono text-[13px] tabular-nums">
              <span className={`mr-1.5 text-[11px] ${everyonePaid ? 'text-success' : 'text-muted'}`}>
                {left > 0 ? t('home.left') : everyonePaid ? t('home.allCollected') : t('home.total')}
              </span>
              <b className="font-bold text-foreground">{formatCurrency(left > 0 ? left : bill.total_sum, currency)}</b>
            </span>
          </span>
          {bell.kind === 'waiting' && (
            <span className="mt-1 flex items-center gap-1.5 font-mono text-[11px] text-muted">
              <BellRing className="h-3 w-3 shrink-0" strokeWidth={2.25} />
              {bell.remindedAt
                ? t('home.remindedAgo', { ago: sinceLabel(bell.remindedAt, now, t) })
                : t('bill.remindNextIn', { left: shortDuration(bell.nextAt.getTime() - now.getTime(), t) })}
            </span>
          )}
        </Link>

        {bell.kind === 'ready' && (
          <button
            type="button"
            onClick={gated(remind)}
            disabled={reminding}
            aria-label={t('home.remindBill')}
            className="btn-hard-sm relative flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border-[1.5px] border-outline bg-background text-foreground disabled:opacity-60"
          >
            <Bell className="h-[18px] w-[18px]" strokeWidth={2.25} />
            {locked && <ProCorner />}
          </button>
        )}
        {bell.kind === 'waiting' && (
          <button
            type="button"
            disabled
            aria-label={t('bill.remindNextIn', { left: shortDuration(bell.nextAt.getTime() - now.getTime(), t) })}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border-[1.5px] border-border text-muted"
          >
            <BellRing className="h-[18px] w-[18px]" strokeWidth={2.25} />
          </button>
        )}
        <DeleteButton open={confirmingDelete} onToggle={() => setConfirmingDelete((open) => !open)} />
      </div>
      {confirmingDelete && (
        <DeleteConfirm onCancel={() => setConfirmingDelete(false)} onConfirm={() => onDelete(bill.id)} />
      )}
    </div>
  );
}
