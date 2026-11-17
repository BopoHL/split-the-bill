'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Check, Copy } from 'lucide-react';
import type { Bill } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { useCopyDetails } from '@/components/bill/PaymentCard';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { OwnerFace } from './RowParts';

/** How long «Payment marked · Undo» stays before the bill moves to the paid ones. */
export const UNDO_WINDOW_MS = 4000;

type Phase = 'idle' | 'busy' | 'marked';

/**
 * One bill the person owes on: whose it is, their share, the card to copy and
 * «I paid». Marking it says so in place for a few seconds, with an undo, before
 * the bill moves down to the paid ones.
 */
export default function OwingRow({ bill, onMarkPaid, onSettled }: {
  bill: Bill;
  onMarkPaid: (bill: Bill, paid: boolean) => Promise<void>;
  onSettled: (billId: number) => void;
}) {
  const { t } = useTranslation();
  const { copied, copy } = useCopyDetails(bill.payment_details);
  const [phase, setPhase] = useState<Phase>('idle');
  const settleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const amount = bill.my_seat?.amount ?? 0;

  useEffect(() => () => {
    if (settleTimer.current) clearTimeout(settleTimer.current);
  }, []);

  const settleSoon = () => {
    settleTimer.current = setTimeout(() => onSettled(bill.id), UNDO_WINDOW_MS);
  };

  const pay = async () => {
    setPhase('busy');
    try {
      await onMarkPaid(bill, true);
    } catch {
      setPhase('idle');
      return;
    }
    setPhase('marked');
    settleSoon();
  };

  const undo = async () => {
    if (settleTimer.current) clearTimeout(settleTimer.current);
    setPhase('busy');
    try {
      await onMarkPaid(bill, false);
      setPhase('idle');
    } catch {
      setPhase('marked');
      settleSoon();
    }
  };

  return (
    <div className="rounded-lg border-[1.5px] border-outline bg-surface px-3.5 py-3">
      <Link href={`/bill/${bill.id}`} className="flex items-center gap-3 text-foreground">
        <OwnerFace name={bill.owner?.name} avatarUrl={bill.owner?.avatar_url} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-[16px] font-semibold leading-tight">
            {bill.title || t('bill.untitled')}
          </span>
          <span className="mt-0.5 block truncate text-[12px] text-muted">
            {t('home.collectedBy', { name: bill.owner?.name ?? '' })}
          </span>
        </span>
        {amount > 0 ? (
          <span className="shrink-0 font-mono text-[15px] font-bold tabular-nums">
            {formatCurrency(amount, bill.currency ?? 'uzs')}
          </span>
        ) : (
          <span className="max-w-[40%] shrink-0 text-right text-[12px] text-muted">{t('home.shareNotSet')}</span>
        )}
      </Link>

      {amount > 0 && phase !== 'marked' && (
        <div className={`mt-3 grid gap-2.5 ${bill.payment_details ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {bill.payment_details && (
            <button
              type="button"
              onClick={() => void copy()}
              className="btn-hard-sm flex min-h-11 items-center justify-center gap-2 rounded-lg border-[1.5px] border-outline bg-background px-3 font-display text-[13px] font-bold text-foreground"
            >
              {copied ? <Check className="h-4 w-4 text-success" strokeWidth={2.5} /> : <Copy className="h-4 w-4" strokeWidth={2.25} />}
              {copied ? t('home.copied') : t('home.card')}
            </button>
          )}
          <button
            type="button"
            onClick={() => void pay()}
            disabled={phase === 'busy'}
            className="btn-hard-sm flex min-h-11 items-center justify-center gap-2 rounded-lg border-[1.5px] border-outline bg-accent px-3 font-display text-[13px] font-bold text-accent-fg disabled:opacity-60"
          >
            <Check className="h-4 w-4" strokeWidth={2.5} />
            {t('bill.iPaidShort')}
          </button>
        </div>
      )}

      {phase === 'marked' && (
        <div role="status" className="mt-3 flex min-h-11 items-center gap-2 rounded-lg bg-success/10 pl-3 pr-1">
          <Check className="h-4 w-4 shrink-0 text-success" strokeWidth={2.5} />
          <span className="font-display text-[13px] font-bold text-success">{t('home.paidMarked')}</span>
          <button
            type="button"
            onClick={() => void undo()}
            className="ml-auto min-h-10 rounded-md px-3 font-display text-[13px] font-bold text-foreground underline underline-offset-2 hover:bg-surface-2"
          >
            {t('home.undo')}
          </button>
        </div>
      )}
    </div>
  );
}
