'use client';

import { Star, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { Receipt } from '@/types/api';
import type { Currency } from '@/lib/utils/currency';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';
import ReceiptThumb from './ReceiptThumb';
import { useAuthenticatedImage } from '@/hooks/useAuthenticatedImage';

interface ReceiptCardProps {
  receipt: Receipt;
  currency?: Currency;
  /** API path of the photo; the card fetches it with the caller's identity. */
  imagePath?: string | null;
  onOpenPhoto?: (url: string) => void;
  onDelete?: () => void;
  /** Rate this scan. Absent for photos that were never recognised. */
  onRate?: (rating: number) => void;
}

export default function ReceiptCard({
  receipt,
  currency,
  imagePath,
  onOpenPhoto,
  onDelete,
  onRate,
}: ReceiptCardProps) {
  const { t } = useTranslation();
  const [rating, setRating] = useState(receipt.quality ?? 0);
  const imageUrl = useAuthenticatedImage(imagePath);

  // A photo attached without recognition never goes through the pipeline, so it
  // has no progress to show and nothing to rate.
  const recognised = receipt.source !== 'manual_photo';
  const scanning =
    recognised &&
    (receipt.status === 'pending' ||
      receipt.status === 'processing' ||
      receipt.status === 'structuring');
  const failed = recognised && (receipt.status === 'failed' || receipt.status === 'cancelled');

  const meta = scanning
    ? t('receipt.recognising')
    : failed
      ? t('receipt.notRecognised')
      : recognised
        ? [
            t('receipt.itemsCount', { count: String(receipt.items_count) }),
            receipt.total != null ? formatCurrency(receipt.total, currency) : null,
          ]
            .filter(Boolean)
            .join(' · ')
        : t('receipt.photoOnly');

  return (
    <div className="flex w-[190px] flex-shrink-0 flex-col overflow-hidden rounded-[10px] border-[1.5px] border-outline bg-surface shadow-[var(--shadow-hard-sm)]">
      <div className="flex flex-1 items-center gap-3 p-2.5">
        <button
          type="button"
          disabled={!imageUrl || !onOpenPhoto}
          onClick={imageUrl && onOpenPhoto ? () => onOpenPhoto(imageUrl) : undefined}
          className="flex-shrink-0 disabled:cursor-default"
        >
          <ReceiptThumb src={imageUrl} index={receipt.index} scanning={scanning} />
        </button>

        <div className="min-w-0 flex-1">
          <div className="truncate font-display text-[13px] font-bold text-foreground">
            {receipt.merchant_name || t('receipt.untitledReceipt')}
          </div>
          <div
            className={`mt-0.5 font-mono text-[11px] leading-snug ${failed ? 'text-danger' : 'text-muted-2'}`}
          >
            {meta}
          </div>
        </div>
      </div>

      {onRate && recognised && !scanning && !failed && (
        <div className="flex flex-col items-center gap-1 border-t-[1.5px] border-dashed border-border py-2">
          <span className="text-center font-mono text-[9px] uppercase leading-tight tracking-[0.08em] text-muted-2">
            {t('receipt.rateScanHint')}
          </span>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                aria-label={String(n)}
                onClick={() => {
                  setRating(n); // optimistic
                  onRate(n);
                }}
                className="transition-transform active:scale-90"
              >
                <Star
                  className={`h-[14px] w-[14px] ${
                    n <= rating ? 'fill-accent text-accent' : 'text-muted-2'
                  }`}
                />
              </button>
            ))}
          </div>
        </div>
      )}

      {onDelete && (
        <div className="border-t-[1.5px] border-dashed border-border">
          <button
            type="button"
            onClick={onDelete}
            disabled={scanning}
            className="flex w-full items-center justify-center gap-1.5 py-2 font-display text-[10px] font-bold uppercase tracking-[0.06em] text-muted transition-colors hover:bg-surface-2 hover:text-danger disabled:pointer-events-none disabled:opacity-40"
          >
            <Trash2 className="h-[13px] w-[13px]" />
            {t('common.delete')}
          </button>
        </div>
      )}
    </div>
  );
}
