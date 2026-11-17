'use client';

import { useState } from 'react';
import { Check, Copy, CreditCard, Eye, Pencil, Plus, X } from 'lucide-react';
import { BillDetail, BillStatus } from '@/types/api';
import PaymentDetailsChooser from '@/components/ui/PaymentDetailsChooser';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { usePaymentChoice } from '@/hooks/usePaymentChoice';
import { sameDetails } from '@/lib/utils/paymentDetails';
import { useFittedFontSize } from '@/hooks/useFittedFontSize';

interface PaymentCardProps {
  bill: BillDetail;
  onUpdate?: (value: string) => Promise<void>;
  compact?: boolean;
}

export async function copyTextToClipboard(value: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  if (typeof document === 'undefined' || typeof document.execCommand !== 'function') {
    throw new Error('Clipboard is unavailable');
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();

  try {
    if (!document.execCommand('copy')) throw new Error('Clipboard copy failed');
  } finally {
    textarea.remove();
  }
}

/** Copies the bill's payment details, marks the copy for two seconds and
 *  counts it; a failure is said in a toast. */
export function useCopyDetails(details: string | null | undefined) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!details) return;
    try {
      await copyTextToClipboard(details);
      track(AnalyticsEvent.PayDetailsCopied, {});
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast(t('common.error'));
    }
  };

  return { copied, copy };
}

/**
 * The bill's card chosen afresh: a saved one or another typed in, put on the
 * bill by «Save» — or taken off it. Mounted only while editing, so nobody
 * else's view of the bill loads the owner's cards.
 */
function PaymentDetailsEditor({ current, onSave, saving }: {
  current: string;
  onSave: (value: string) => void;
  saving: boolean;
}) {
  const { t } = useTranslation();
  const choice = usePaymentChoice({ current });

  return (
    <div className="flex flex-col gap-5">
      <PaymentDetailsChooser choice={choice} />
      <div className="flex items-center gap-2">
        {current && (
          <Button variant="danger" onClick={() => onSave('')} disabled={saving} className="-ml-2 !px-2">
            {t('bill.removeFromBill')}
          </Button>
        )}
        <Button
          className="ml-auto"
          onClick={async () => {
            // Kept first: the bill then finds the card among the saved ones
            // instead of saving it a second time alongside.
            await choice.keep();
            onSave(choice.value);
          }}
          disabled={!choice.value || sameDetails(choice.value, current)}
          isLoading={saving}
        >
          {t('common.save')}
        </Button>
      </div>
    </div>
  );
}

/**
 * Where to send the money.
 *
 * Its own block below the receipt rather than a line inside it: for everyone
 * except the owner this is the one thing they came to the screen for, and it was
 * buried under the items in the same small type as everything else.
 */
export default function PaymentCard({ bill, onUpdate, compact = false }: PaymentCardProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const { copied, copy } = useCopyDetails(bill.payment_details);
  const [showingFull, setShowingFull] = useState(false);
  // The details shrink to fit the dock's line; past the smallest size the
  // rest is cut off and shown in full on request.
  const fitted = useFittedFontSize<HTMLSpanElement, HTMLSpanElement>(bill.payment_details ?? '', 20, 12);

  const editable = !!onUpdate && bill.status === BillStatus.OPEN;

  const save = async (value: string) => {
    if (!onUpdate) return;
    setSaving(true);
    try {
      await onUpdate(value.trim());
      setEditing(false);
    } catch {
      showToast(t('common.error'));
    } finally {
      setSaving(false);
    }
  };

  const closeEditor = () => {
    if (!saving) setEditing(false);
  };

  const editor = <PaymentDetailsEditor current={bill.payment_details ?? ''} onSave={(value) => void save(value)} saving={saving} />;

  if (editing && !compact) {
    return (
      <div className="rounded-lg border-[1.5px] border-outline bg-surface p-4">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">{editor}</div>
          {/* Picking a card saves it immediately, so without this there is no
              way out of the editor except changing something. */}
          <button
            type="button"
            onClick={closeEditor}
            disabled={saving}
            aria-label={t('common.cancel')}
            className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-surface text-muted transition-colors hover:text-danger disabled:opacity-50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
    );
  }

  if (!bill.payment_details) {
    if (!editable && !compact) return null;

    const emptyState = editable ? (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className={`flex w-full items-center justify-center gap-2 rounded-lg border-[1.5px] border-dashed border-outline font-display text-[13px] font-bold text-muted transition-colors hover:border-accent hover:text-accent ${
          compact ? 'min-h-11 px-3 py-2' : 'py-4 uppercase tracking-[0.06em]'
        }`}
      >
        {compact ? <CreditCard className="h-[18px] w-[18px]" /> : <Plus className="h-4 w-4" />}
        {t('bill.addPaymentDetails')}
      </button>
    ) : (
      <div className="flex min-h-11 items-center gap-2 rounded-lg border-[1.5px] border-dashed border-border px-3 py-2 text-[13px] text-muted">
        <CreditCard className="h-[18px] w-[18px] flex-shrink-0" />
        <span>{t('bill.noPaymentDetails')}</span>
      </div>
    );

    return (
      <>
        {emptyState}
        {compact && editable && (
          <Modal
            isOpen={editing}
            onClose={closeEditor}
            title={t('bill.paymentCard')}
            size="sm"
          >
            {editor}
          </Modal>
        )}
      </>
    );
  }

  if (compact) {
    return (
      <>
        <div className="flex min-h-12 w-full max-w-full min-w-0 items-center gap-2 overflow-hidden rounded-lg border-[1.5px] border-outline bg-surface p-1.5 shadow-[var(--shadow-hard-sm)]">
          <CreditCard className="ml-1.5 h-[18px] w-[18px] flex-shrink-0 text-accent" />
          <span
            ref={fitted.boxRef}
            data-ph-mask
            style={{ fontSize: fitted.size }}
            className="min-w-0 flex-1 truncate font-mono font-bold leading-tight text-foreground"
          >
            <span ref={fitted.textRef}>{bill.payment_details}</span>
          </span>
          {fitted.clipped && (
            <button
              type="button"
              onClick={() => setShowingFull(true)}
              aria-label={t('bill.showPaymentDetails')}
              className="flex h-11 w-9 flex-shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-accent"
            >
              <Eye className="h-[18px] w-[18px]" />
            </button>
          )}
          {editable && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              aria-label={t('bill.editPaymentDetails')}
              className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-accent"
            >
              <Pencil className="h-[18px] w-[18px]" />
            </button>
          )}
          <button
            type="button"
            onClick={() => void copy()}
            aria-label={t('bill.copyCard')}
            className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-background text-foreground transition-colors hover:text-accent"
          >
            {copied ? <Check className="h-5 w-5 text-success" /> : <Copy className="h-5 w-5" />}
          </button>
        </div>

        <Modal
          isOpen={editing}
          onClose={closeEditor}
          title={t('bill.paymentCard')}
          size="sm"
        >
          {editor}
        </Modal>

        <Modal
          isOpen={showingFull}
          onClose={() => setShowingFull(false)}
          title={t('bill.paymentCard')}
          size="sm"
        >
          <p data-ph-mask className="font-mono text-[22px] font-bold leading-snug text-foreground [overflow-wrap:anywhere]">
            {bill.payment_details}
          </p>
          <Button className="mt-5 w-full" onClick={() => void copy()}>
            {copied ? <Check className="h-5 w-5" /> : <Copy className="h-5 w-5" />}
            {t('bill.copyCard')}
          </Button>
        </Modal>
      </>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border-[1.5px] border-accent bg-surface shadow-[var(--shadow-hard)]">
      <div className="flex items-center justify-between gap-2 bg-bar py-1.5 pl-4 pr-1.5">
        <span className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-bar-fg">
          {t('bill.paymentCard')}
        </span>
        {editable && (
          <button
            onClick={() => setEditing(true)}
            aria-label={t('bill.editPaymentDetails')}
            className="flex h-9 w-9 items-center justify-center rounded-md text-bar-fg opacity-85 transition-opacity hover:bg-white/15 hover:opacity-100"
          >
            <Pencil className="h-[17px] w-[17px]" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-3 px-4 py-3.5">
        <span
          data-ph-mask
          className="min-w-0 flex-1 font-mono text-[20px] font-bold leading-tight tracking-[0.02em] text-foreground [overflow-wrap:anywhere]"
        >
          {bill.payment_details}
        </span>
        <button
          onClick={() => void copy()}
          aria-label={t('common.copy')}
          className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-background text-foreground transition-colors hover:text-accent"
        >
          {copied ? <Check className="h-6 w-6 text-success" /> : <Copy className="h-6 w-6" />}
        </button>
      </div>
    </div>
  );
}
