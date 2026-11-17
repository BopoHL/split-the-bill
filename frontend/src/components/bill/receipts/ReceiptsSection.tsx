'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Plus, ReceiptText } from 'lucide-react';
import type { BillDetail, Receipt, ReceiptDeleteImpact } from '@/types/api';
import type { Currency } from '@/lib/utils/currency';
import { deleteReceipt, getReceiptDeleteImpact, rateReceipt, receiptImagePath } from '@/lib/api/bills';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import ReceiptCard from './ReceiptCard';
import DeleteReceiptDialog from './DeleteReceiptDialog';
import PhotoViewer from './PhotoViewer';
import AddReceiptDialog from './AddReceiptDialog';

interface ReceiptsSectionProps {
  bill: BillDetail;
  currentUserId?: number;
  isCreator: boolean;
  currency?: Currency;
  onBillUpdate: (bill: BillDetail) => void;
  /** Refetch after a receipt was added — the scan finishes in the background. */
  onReload: () => void;
}

/**
 * The receipts attached to a bill, in a single swipeable row.
 *
 * Sideways scrolling is suppressed everywhere else in the app, because on iOS a
 * horizontal pan drags the Telegram viewport and reads as the whole app sliding.
 * This strip opts back in deliberately and contains it: `overscroll-x-contain`
 * stops the gesture at its own edges. It must still allow `pan-y`: a finger
 * that lands on a receipt and moves vertically has to scroll the page. And a
 * sideways drag is only the strip's while it has somewhere to scroll; when it
 * fits, or is at its edge, the drag pages the bill's tabs as anywhere else.
 */
export default function ReceiptsSection({
  bill,
  currentUserId,
  isCreator,
  currency,
  onBillUpdate,
  onReload,
}: ReceiptsSectionProps) {
  const { t } = useTranslation();

  const [pendingDelete, setPendingDelete] = useState<Receipt | null>(null);
  const [impact, setImpact] = useState<ReceiptDeleteImpact | null>(null);
  const [busy, setBusy] = useState(false);
  const [photo, setPhoto] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [autoScan, setAutoScan] = useState(false);

  // The bot's scan link lands here. Read straight off the URL rather than
  // threaded down from the page: this section is rendered from three
  // different bill views, and none of them has any other use for the flag.
  const router = useRouter();
  const searchParams = useSearchParams();
  const wantsScan = searchParams.get('scan') === '1';

  useEffect(() => {
    if (!wantsScan || !isCreator || bill.status !== 'open') return;
    setAdding(true);
    setAutoScan(true);
    // Consumed — otherwise going back to the bill reopens the scanner.
    router.replace(`/bill/${bill.id}`);
  }, [wantsScan, isCreator, bill.status, bill.id, router]);

  const receipts = bill.receipts ?? [];
  const canEdit = isCreator && bill.status === 'open';
  // Rating outlives the bill: it is feedback on the scan, not an edit to the
  // split — and it is usually only obvious afterwards whether the parse was good.
  const canRate = isCreator;

  if (receipts.length === 0 && !canEdit) return null;

  const askDelete = async (receipt: Receipt) => {
    setPendingDelete(receipt);
    setImpact(null);
    if (!currentUserId) return;
    try {
      setImpact(await getReceiptDeleteImpact(bill.id, receipt.task_id, currentUserId));
    } catch {
      /* the dialog still works without the summary */
    }
  };

  const confirmDelete = async (keepItems: boolean) => {
    if (!pendingDelete || !currentUserId) return;
    setBusy(true);
    try {
      onBillUpdate(await deleteReceipt(bill.id, pendingDelete.task_id, currentUserId, keepItems));
      track(AnalyticsEvent.ReceiptDeleted, { bill_id: bill.id, kept_items: keepItems });
      setPendingDelete(null);
    } catch {
      showToast(t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-5">
      <div
        data-sideways-scroller
        className={`-mx-1 flex gap-2.5 overflow-x-auto overscroll-x-contain px-1 pb-2 ${
          receipts.length <= 1 ? 'justify-center' : ''
        }`}
        style={{ touchAction: 'pan-x pan-y', scrollSnapType: 'x mandatory' }}
      >
        {receipts.map((receipt) => {
          const imagePath = receipt.has_photo
            ? receiptImagePath(bill.id, receipt.task_id)
            : null;

          return (
            <div key={receipt.task_id} style={{ scrollSnapAlign: 'start' }} className="flex">
              <ReceiptCard
                receipt={receipt}
                currency={currency}
                imagePath={imagePath}
                onOpenPhoto={setPhoto}
                onDelete={canEdit ? () => void askDelete(receipt) : undefined}
                onRate={
                  canRate && currentUserId
                    ? (rating) => {
                        void rateReceipt(bill.id, receipt.task_id, rating, currentUserId).then(
                          () => track(AnalyticsEvent.ReceiptRated, { bill_id: bill.id, rating }),
                          () => showToast(t('common.error')),
                        );
                      }
                    : undefined
                }
              />
            </div>
          );
        })}
        {canEdit && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            aria-label={t('receipt.addReceipt')}
            title={t('receipt.addReceipt')}
            style={{ scrollSnapAlign: 'start' }}
            className="btn-hard-sm group relative flex h-[86px] w-[86px] flex-shrink-0 items-center justify-center self-start rounded-[6px] border-[1.5px] border-outline bg-surface text-muted hover:border-accent hover:text-accent"
          >
            <ReceiptText className="h-7 w-7" strokeWidth={1.75} />
            <span className="absolute bottom-3 right-3 flex h-5 w-5 items-center justify-center rounded-[6px] border-[1.5px] border-current bg-surface">
              <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            </span>
          </button>
        )}
      </div>

      <AddReceiptDialog
        isOpen={adding}
        billId={bill.id}
        currency={currency}
        userId={currentUserId}
        autoScan={autoScan}
        onClose={() => {
          setAdding(false);
          setAutoScan(false);
        }}
        onAdded={onReload}
      />

      <PhotoViewer src={photo} onClose={() => setPhoto(null)} />

      <DeleteReceiptDialog
        receipt={pendingDelete}
        impact={impact}
        currency={currency}
        busy={busy}
        onClose={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
