'use client';

import { BillDetail, BillStatus } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { Check, Pencil, X, Loader2, AlertTriangle } from 'lucide-react';
import { ReactNode, useState } from 'react';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useStore } from '@/lib/store/useStore';
import { showToast } from '@/lib/toast';
import BillPlace from './BillPlace';

interface BillOverviewProps {
  bill: BillDetail;
  /** Rename the bill from the receipt title (owner of an open bill). */
  onUpdateTitle?: (newTitle: string) => Promise<void>;
  canEditTitle?: boolean;
  /** The owner names where the bill was; anyone sees it once it is known. */
  onPlaceChange?: (place: string | null) => void;
  /** Item rows — rendered inside the receipt between the rules. */
  children?: ReactNode;
}

export default function BillOverview({
  bill,
  onUpdateTitle,
  canEditTitle,
  onPlaceChange,
  children,
}: BillOverviewProps) {
  const { t, language } = useTranslation();
  // Old bills may lack a stored currency → fall back to the historical 'uzs'
  // (never the viewer's setting, so an existing bill never re-denominates).
  const billCurrency = bill.currency ?? 'uzs';
  // Editing payment details state


  const userId = useStore((s) => s.currentUser?.id);

  // Inline title editing (owner of an open bill).
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  // The mismatch nudge is advice, not a blocker — let it be put away.
  const [mismatchDismissed, setMismatchDismissed] = useState(false);
  const [titleDraft, setTitleDraft] = useState(bill.title || '');
  const [savingTitle, setSavingTitle] = useState(false);

  const saveTitle = async () => {
    if (!onUpdateTitle) return;
    const next = titleDraft.trim().slice(0, 100);
    if (next === (bill.title || '')) {
      setIsEditingTitle(false);
      return;
    }
    setSavingTitle(true);
    try {
      await onUpdateTitle(next);
      setIsEditingTitle(false);
    } catch {
      showToast(t('common.error'));
    } finally {
      setSavingTitle(false);
    }
  };

  const isOwner = userId === bill.owner_id;

  const totalAmount = bill.total_sum;

  // Receipt date line (merchant name = bill title in our model).
  const dateLocale = language === 'en' ? 'en-GB' : language === 'uz' ? 'uz-UZ' : 'ru-RU';
  let dateStr = '';
  try {
    dateStr = new Date(bill.created_at).toLocaleDateString(dateLocale, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    dateStr = '';
  }



  return (
    <div className="relative rounded-lg border-[1.5px] border-outline bg-surface px-4 pb-4 pt-[22px] shadow-[var(--shadow-hard)] sm:px-5">
      {/* The receipts themselves are listed by ReceiptsSection, which also owns
          adding and removing them — this block used to duplicate both. */}
      <div className="text-center">
        {/* Status stamps */}
        {bill.status === BillStatus.PAID && (
          <div className="mb-3 inline-flex -rotate-2 items-center gap-1.5 rounded-[5px] border-2 border-accent px-[9px] py-[3px] font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-accent">
            {t('bill.statusPaid')}
          </div>
        )}
        {bill.status === BillStatus.CLOSED && (
          <div className="mb-3 inline-flex -rotate-2 items-center gap-1.5 rounded-[5px] border-2 border-success px-[9px] py-[3px] font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-success">
            <Check className="h-3 w-3" strokeWidth={2.5} />
            {t('bill.statusClosed')}
          </div>
        )}

        {/* Merchant (title) + date — title is editable here for the owner. */}
        <div className="text-center">
          {canEditTitle && isEditingTitle ? (
            <div className="flex items-center justify-center gap-1.5">
              <input
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void saveTitle();
                  if (e.key === 'Escape') {
                    setTitleDraft(bill.title || '');
                    setIsEditingTitle(false);
                  }
                }}
                maxLength={100}
                autoFocus
                className="min-w-0 max-w-[220px] rounded-md border-[1.5px] border-outline bg-background px-2.5 py-1.5 text-center font-display text-[18px] font-bold text-foreground outline-none focus:border-accent"
              />
              <button
                type="button"
                onClick={saveTitle}
                disabled={savingTitle}
                aria-label={t('common.save')}
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] border-success bg-success text-success-fg disabled:opacity-50"
              >
                {savingTitle ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-[18px] w-[18px]" />}
              </button>
              <button
                type="button"
                onClick={() => {
                  setTitleDraft(bill.title || '');
                  setIsEditingTitle(false);
                }}
                aria-label={t('common.cancel')}
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-surface text-muted hover:text-danger"
              >
                <X className="h-[18px] w-[18px]" />
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-center gap-1.5">
              <div className="min-w-0 font-display text-[21px] font-bold leading-tight text-foreground [overflow-wrap:anywhere]">
                {bill.title || t('bill.untitled')}
              </div>
              {canEditTitle && (
                <button
                  type="button"
                  onClick={() => {
                    setTitleDraft(bill.title || '');
                    setIsEditingTitle(true);
                  }}
                  aria-label={t('bill.renameBill')}
                  className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-muted-2 transition-colors hover:text-accent"
                >
                  <Pencil className="h-4 w-4" />
                </button>
              )}
            </div>
          )}
          <BillPlace bill={bill} ownerId={bill.owner_id} canEdit={isOwner && !!onPlaceChange} onChange={(place) => onPlaceChange?.(place)} />
          {dateStr && (
            <div className="mt-1.5 font-mono text-[11px] tracking-[0.03em] text-muted-2">{dateStr}</div>
          )}
        </div>
      </div>

      {/* Surface scan quality before the long receipt so a large bill cannot
          push the warning below the fold. It remains advice, not a blocker. */}
      {isOwner && bill.scan_total_mismatch && !mismatchDismissed && (
        <div role="note" className="mt-4 flex items-start gap-2 rounded-md border-[1.5px] border-outline bg-accent-weak px-3 py-3 shadow-[var(--shadow-hard-sm)]">
          <AlertTriangle className="mt-px h-4 w-4 flex-shrink-0 text-accent" />
          <p className="min-w-0 flex-1 font-mono text-[11px] leading-snug text-foreground">
            {t('bill.scanTotalMismatch', {
              amount: formatCurrency(bill.receipt_total_sum ?? 0, billCurrency),
            })}
          </p>
          <button
            type="button"
            onClick={() => setMismatchDismissed(true)}
            aria-label={t('common.close')}
            className="-mr-1 -mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-muted-2 transition-colors hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Items */}
      <hr className="my-4 border-0 border-t-[1.5px] border-dashed border-border" />
      {children}
      <hr className="my-4 border-0 border-t-[1.5px] border-outline" />

      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-2">
        <span className="font-display text-[13px] font-bold uppercase text-foreground">
          {t('bill.totalBill')}
        </span>
        <span className="max-w-full font-mono text-[24px] font-bold leading-tight text-foreground tabular-nums [overflow-wrap:anywhere]">
          {formatCurrency(totalAmount, billCurrency)}
        </span>
      </div>

    </div>
  );
}
