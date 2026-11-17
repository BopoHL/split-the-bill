'use client';

import { Trash2 } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import type { Receipt, ReceiptDeleteImpact } from '@/types/api';
import type { Currency } from '@/lib/utils/currency';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface DeleteReceiptDialogProps {
  receipt: Receipt | null;
  impact: ReceiptDeleteImpact | null;
  currency?: Currency;
  busy?: boolean;
  onClose: () => void;
  onConfirm: (keepItems: boolean) => void;
}

/**
 * Removing a receipt always asks the same question, because it's the one part
 * that can't be undone: do its lines go with it, or stay on the bill?
 */
export default function DeleteReceiptDialog({
  receipt,
  impact,
  currency,
  busy,
  onClose,
  onConfirm,
}: DeleteReceiptDialogProps) {
  const { t } = useTranslation();

  return (
    <Modal isOpen={!!receipt} onClose={onClose} title={t('receipt.deleteTitle')} size="sm">
      {receipt && (
        <>
          <p className="text-[14px] leading-relaxed text-muted">
            {t('receipt.deleteIntro', {
              name: receipt.merchant_name || t('receipt.untitledReceipt'),
            })}
          </p>
          {(impact?.items_count ?? receipt.items_count) > 0 && (
            <p className="mt-3.5 font-display text-base font-extrabold leading-snug text-foreground">
              {t('receipt.deleteQuestion')}
            </p>
          )}
          {impact && (
            <p className="mt-1.5 font-mono text-[11px] text-muted-2">
              {[
                t('receipt.itemsCount', { count: String(impact.items_count) }),
                formatCurrency(impact.total, currency),
                impact.assigned_count > 0
                  ? t('receipt.alreadyAssigned', { count: String(impact.assigned_count) })
                  : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}

          <div className="mt-5 flex flex-col gap-2.5">
            <Button
              variant="danger"
              className="w-full border-[1.5px] border-danger"
              isLoading={busy}
              onClick={() => onConfirm(false)}
            >
              <Trash2 className="mr-2 h-[17px] w-[17px]" />
              {(impact?.items_count ?? receipt.items_count) > 0
                ? t('receipt.deleteWithItems')
                : t('common.delete')}
            </Button>
            {/* A receipt that brought nothing in has no second option to offer. */}
            {(impact?.items_count ?? receipt.items_count) > 0 && (
              <Button variant="outline" className="w-full" onClick={() => onConfirm(true)}>
                {t('receipt.deleteKeepItems')}
              </Button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="py-1 font-display text-[11px] font-bold uppercase tracking-[0.08em] text-muted-2 transition-colors hover:text-accent"
            >
              {t('common.cancel')}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
