'use client';

import { CheckCheck, ListPlus } from 'lucide-react';
import { formatCurrency, type Currency } from '@/lib/utils/currency';
import { dishUnit } from '@/lib/utils/plural';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { BESIDE_AMOUNT } from './BillPaymentDock';

/**
 * The dock while the owner picks dishes: how many and for how much, the one
 * thing to do with them, and a shortcut to everything nobody has yet.
 */
export default function DishSelectionBar({ count, amount, currency, freeLeft, onPickFree, onClear, onAssign }: {
  count: number;
  amount: number;
  currency: Currency;
  /** Dishes nobody has yet that are not picked. */
  freeLeft: number;
  onPickFree: () => void;
  onClear: () => void;
  onAssign: () => void;
}) {
  const { t, language } = useTranslation();
  return (
    <>
      <div className="flex min-w-0 items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
            {count > 0 ? t('bill.selectedCount', { count: `${count} ${dishUnit(count, language)}` }) : t('bill.pickDishes')}
          </div>
          <div className="min-w-0 break-words font-mono text-[22px] font-bold leading-tight tabular-nums text-foreground">
            {formatCurrency(amount, currency)}
          </div>
        </div>
        <button type="button" onClick={onAssign} disabled={count === 0} className={`${BESIDE_AMOUNT} btn-hard border-outline bg-accent text-accent-fg`}>
          <ListPlus className="h-4 w-4 flex-shrink-0" />
          {t('bill.assign')}
        </button>
      </div>
      <button
        type="button"
        onClick={freeLeft > 0 ? onPickFree : onClear}
        disabled={freeLeft === 0 && count === 0}
        className="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border-[1.5px] border-dashed border-outline px-3 py-2 font-display text-[13px] font-bold text-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
      >
        <CheckCheck className="h-[18px] w-[18px] flex-shrink-0" />
        {freeLeft > 0 ? t('bill.selectAllFree', { count: String(freeLeft) }) : t('bill.resetSelection')}
      </button>
    </>
  );
}
