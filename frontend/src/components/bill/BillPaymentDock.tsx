'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Check, Copy, DollarSign, RotateCcw, Stamp, Undo2 } from 'lucide-react';
import type { BillDetail, User } from '@/types/api';
import { BillStatus } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { billPositions } from '@/lib/utils/billPositions';
import { splitsByDishes } from '@/lib/utils/participants';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import Button from '@/components/ui/Button';
import Modal from '@/components/ui/Modal';
import PaymentCard, { copyTextToClipboard } from './PaymentCard';
import { TourAnchor } from '@/lib/tour/anchors';

const toMinorUnits = (amount: number) =>
  Math.sign(amount) * Math.round((Math.abs(amount) + Number.EPSILON) * 100);

const minorUnitsToNumericString = (amount: number) => {
  const sign = amount < 0 ? '-' : '';
  const absolute = Math.abs(amount);
  const whole = Math.floor(absolute / 100);
  const fraction = absolute % 100;

  if (fraction === 0) return `${sign}${whole}`;
  return `${sign}${whole}.${fraction.toString().padStart(2, '0').replace(/0$/, '')}`;
};

const DOCK_KEY =
  'flex min-h-11 items-center justify-center gap-1.5 rounded-lg border-[1.5px] px-3.5 py-2 text-center font-display text-[13px] font-bold leading-tight disabled:opacity-50';
// Beside the amount a key takes what it needs; under the card it has the
// whole width.
export const BESIDE_AMOUNT = `${DOCK_KEY} max-w-[58%] flex-shrink-0`;
const UNDER_CARD = `${DOCK_KEY} w-full`;

const isEditableTextEntry = (target: EventTarget | null) => {
  if (!(target instanceof HTMLElement)) return false;
  if (target instanceof HTMLTextAreaElement) return !target.readOnly && !target.disabled;
  if (target instanceof HTMLInputElement) {
    return !target.readOnly
      && !target.disabled
      && !['button', 'checkbox', 'color', 'file', 'hidden', 'radio', 'range', 'reset', 'submit']
        .includes(target.type);
  }
  return target.isContentEditable;
};

export interface BillPaymentDockProps {
  bill: BillDetail;
  currentUser: User | null;
  isCreator?: boolean;
  loading?: boolean;
  onTogglePaid?: () => void;
  onSelectItems?: () => void;
  onUpdatePaymentDetails?: (value: string) => Promise<void>;
  onCloseBill?: () => void;
  onReopenBill?: () => void;
  /** Shown instead of the payment strip while the screen needs the dock for
   *  something else — the owner picking dishes to hand out. */
  takeover?: ReactNode;
  /** A round button that floats over the dock's right edge and moves with it. */
  fab?: ReactNode;
}

/** The room a floating button takes above the dock: its 60px and a gap. */
const FAB_ROOM = 72;

export default function BillPaymentDock({
  bill,
  currentUser,
  isCreator,
  loading = false,
  onTogglePaid,
  onSelectItems,
  onUpdatePaymentDetails,
  onCloseBill,
  onReopenBill,
  takeover,
  fab,
}: BillPaymentDockProps) {
  const { t } = useTranslation();
  const dockRef = useRef<HTMLDivElement>(null);
  const [dockHeight, setDockHeight] = useState(0);
  const [amountCopied, setAmountCopied] = useState(false);
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);
  const [textEntryFocused, setTextEntryFocused] = useState(() =>
    typeof document !== 'undefined' && isEditableTextEntry(document.activeElement),
  );
  const [viewportOccluded, setViewportOccluded] = useState(false);
  const creator = isCreator ?? currentUser?.id === bill.owner_id;
  const isClosed = bill.status === BillStatus.CLOSED;
  const byDishes = splitsByDishes(bill);
  const myParticipation = currentUser
    ? bill.participants.find((participant) => participant.user_id === currentUser.id)
    : undefined;
  const ownerParticipation = bill.participants.find(
    (participant) => participant.user_id === bill.owner_id,
  );
  // The owner sees what the others still owe, counted by the server the way
  // the home screen counts it, so the two never disagree.
  const left = bill.left_to_collect ?? 0;
  // Nobody owes yet while dishes wait to be taken: the bill's total, as the
  // home screen says it, rather than «0 left» on a bill nobody has paid.
  const showTotal = creator && left <= 0 && bill.unallocated_sum > 0;
  const amount = creator ? (showTotal ? bill.total_sum : left) : myParticipation?.allocated_amount ?? 0;
  const amountMinor = toMinorUnits(amount);
  // What the owner had themselves: not among what is left to collect, but
  // what they paid at the table for their own dishes.
  const ownShare = creator ? Math.max(0, ownerParticipation?.allocated_amount ?? 0) : 0;
  const hasAssignedItems = Boolean(
    myParticipation
      && billPositions(bill.items, bill.participants, bill.currency).some(
        (position) => position.participantIds.includes(myParticipation.id),
      ),
  );

  useEffect(() => {
    const dock = dockRef.current;
    if (!dock) return;

    const measure = () => setDockHeight(dock.getBoundingClientRect().height);
    measure();

    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(dock);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;

    const syncOcclusion = () => {
      const hiddenHeight = window.innerHeight - viewport.height - viewport.offsetTop;
      setViewportOccluded(hiddenHeight > 120);
    };

    syncOcclusion();
    viewport.addEventListener('resize', syncOcclusion);
    viewport.addEventListener('scroll', syncOcclusion);
    return () => {
      viewport.removeEventListener('resize', syncOcclusion);
      viewport.removeEventListener('scroll', syncOcclusion);
    };
  }, []);

  const dockSuppressed = textEntryFocused || viewportOccluded;

  useEffect(() => {
    const handleFocusIn = (event: FocusEvent) =>
      setTextEntryFocused(isEditableTextEntry(event.target));
    const handleFocusOut = (event: FocusEvent) =>
      setTextEntryFocused(isEditableTextEntry(event.relatedTarget));

    document.addEventListener('focusin', handleFocusIn);
    document.addEventListener('focusout', handleFocusOut);
    return () => {
      document.removeEventListener('focusin', handleFocusIn);
      document.removeEventListener('focusout', handleFocusOut);
    };
  }, []);

  const copyAmount = async () => {
    try {
      await copyTextToClipboard(minorUnitsToNumericString(amountMinor));
      track(AnalyticsEvent.PayAmountCopied, { bill_id: bill.id });
      setAmountCopied(true);
      setTimeout(() => setAmountCopied(false), 2000);
    } catch {
      showToast(t('common.error'));
    }
  };

  const markedPaid = !creator && !isClosed && amountMinor > 0 && !!myParticipation?.is_paid;
  const canPay = !creator && !isClosed && amountMinor > 0 && !myParticipation?.is_paid;

  const action = creator ? (
    isClosed ? (
      <button
        type="button"
        onClick={onReopenBill}
        disabled={loading || !onReopenBill}
        className={`${BESIDE_AMOUNT} btn-hard-sm border-outline bg-surface text-foreground`}
      >
        <RotateCcw className="h-4 w-4 flex-shrink-0" />
        {t('bill.reopen')}
      </button>
    ) : (
      <button
        type="button"
        onClick={onCloseBill}
        disabled={loading || !onCloseBill}
        data-tour={TourAnchor.CloseBill}
        className={`${BESIDE_AMOUNT} btn-hard border-outline bg-success text-success-fg`}
      >
        <Stamp className="h-4 w-4 flex-shrink-0" />
        {t('bill.closeBill')}
      </button>
    )
  ) : markedPaid ? (
    <button
      type="button"
      onClick={() => setConfirmCancelOpen(true)}
      disabled={loading || !onTogglePaid}
      className={`${UNDER_CARD} border-danger bg-surface text-danger hover:bg-surface-2`}
    >
      <Undo2 className="h-4 w-4 flex-shrink-0" />
      {t('bill.cancelPayment')}
    </button>
  ) : canPay ? (
    <button
      type="button"
      onClick={onTogglePaid}
      disabled={loading || !onTogglePaid}
      data-tour={TourAnchor.IPaid}
      className={`${UNDER_CARD} btn-hard border-outline bg-success text-success-fg`}
    >
      <DollarSign className="h-4 w-4 flex-shrink-0" />
      {t('bill.iPaidShort')}
    </button>
  ) : null;

  // The owner's amount and the one thing to do about it share a row, so the
  // dock stays a strip rather than a third of the screen.
  const amountRow = (
    <div className="flex min-w-0 items-center gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-1.5 font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
          <span>{creator ? t(showTotal ? 'home.total' : 'bill.leftToCollect') : t('bill.yourShare')}</span>
          {markedPaid && (
            <>
              <span aria-hidden="true">·</span>
              <span className="text-success">{t('bill.paymentMarked')}</span>
            </>
          )}
        </div>
        <div className="flex min-w-0 items-center gap-1">
          <span
            className={`min-w-0 whitespace-normal break-words font-mono text-[22px] font-bold leading-tight tabular-nums ${
              markedPaid ? 'text-success' : 'text-foreground'
            }`}
          >
            {formatCurrency(amount, bill.currency ?? 'uzs')}
          </span>
          {!creator && (
            <button
              type="button"
              onClick={() => void copyAmount()}
              aria-label={t('bill.copyAmount')}
              className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:text-accent"
            >
              {amountCopied ? <Check className="h-[18px] w-[18px] text-success" /> : <Copy className="h-[18px] w-[18px]" />}
            </button>
          )}
        </div>
        {ownShare > 0 && (
          <div className="font-mono text-[12px] tabular-nums text-muted">
            {t('bill.ownShare', { amount: formatCurrency(ownShare, bill.currency ?? 'uzs') })}
          </div>
        )}
      </div>
      {creator && action}
    </div>
  );

  const participantContent = !isClosed
    && amountMinor <= 0
    && byDishes
    && !hasAssignedItems ? (
    <div className="flex flex-wrap items-center gap-2.5 rounded-lg border-[1.5px] border-dashed border-border bg-surface-2 px-3 py-2.5">
      <p className="min-w-0 flex-1 basis-40 text-[13px] leading-snug text-muted">
        {t('bill.emptyShareHint')}
      </p>
      <button
        type="button"
        onClick={onSelectItems}
        disabled={!onSelectItems}
        className="flex min-h-11 min-w-0 flex-1 basis-28 items-center justify-center rounded-md border-[1.5px] border-outline bg-surface px-3 text-center font-display text-[13px] font-bold text-foreground btn-hard-sm disabled:opacity-50"
      >
        {t('bill.chooseItems')}
      </button>
    </div>
  ) : !isClosed && amountMinor <= 0 && !byDishes ? (
    <div className="rounded-lg border-[1.5px] border-dashed border-border bg-surface-2 px-3 py-2.5 text-[13px] leading-snug text-muted">
      {t('bill.waitingForShare')}
    </div>
  ) : (
    <>
      <div data-tour={TourAnchor.MyShare} className="flex flex-col gap-2">
        {amountRow}
        <PaymentCard bill={bill} compact />
      </div>
      {action}
      {!isClosed && amountMinor <= 0 && hasAssignedItems && (
        <div className="rounded-lg border-[1.5px] border-dashed border-border bg-surface-2 px-3 py-2.5 text-[13px] leading-snug text-muted">
          {t('bill.noPaymentDue')}
        </div>
      )}
    </>
  );

  return (
    <>
      <div
        aria-hidden="true"
        data-testid="bill-payment-dock-spacer"
        style={{ height: dockHeight + (fab ? FAB_ROOM : 0) }}
      />
      {/* Fixed to the viewport, so it lives on <body>: inside a transformed or
          translated ancestor it would be positioned against that instead. It
          still moves with the page when the back swipe pulls the page aside. */}
      {typeof document !== 'undefined' && createPortal(
        <div
          ref={dockRef}
          data-testid="bill-payment-dock"
          data-back-swipe-layer="page"
          data-keyboard-hidden={dockSuppressed ? 'true' : 'false'}
          aria-hidden={dockSuppressed || undefined}
          className="fixed inset-x-0 bottom-0 z-30 overflow-x-clip border-t-[1.5px] border-outline bg-background shadow-[0_-4px_0_var(--shadow-ink)] transition-[transform,opacity] duration-150"
          style={{
            opacity: dockSuppressed ? 0 : 1,
            pointerEvents: dockSuppressed ? 'none' : undefined,
            transform: dockSuppressed
              ? 'translateY(calc(100% + var(--content-safe-bottom)))'
              : 'translateY(0)',
          }}
        >
          {fab && (
            <div className="pointer-events-none absolute inset-x-0 bottom-full mx-auto flex w-full max-w-2xl justify-end pb-3 pr-[calc(1rem+var(--content-safe-right))]">
              {fab}
            </div>
          )}
          {/* Kept off the screen's rounded corners: at least 20px from the
              bottom edge, or the safe area when that is more. */}
          <div className="mx-auto box-border flex w-full max-w-2xl min-w-0 flex-col gap-2 pt-2.5 pb-[max(1.25rem,var(--content-safe-bottom))] pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))]">
            {takeover ?? (creator ? (
              <>
                {amountRow}
                <PaymentCard
                  bill={bill}
                  compact
                  onUpdate={isClosed ? undefined : onUpdatePaymentDetails}
                />
              </>
            ) : (
              participantContent
            ))}
          </div>
        </div>,
        document.body,
      )}

      <Modal
        isOpen={confirmCancelOpen}
        onClose={() => setConfirmCancelOpen(false)}
        title={t('bill.cancelPaymentTitle')}
        size="sm"
      >
        <p className="text-[15px] leading-snug text-foreground">
          {t('bill.cancelPaymentConfirm')}
        </p>
        <div className="mt-5 flex gap-2.5">
          <Button
            variant="primary"
            className="flex-1"
            onClick={() => setConfirmCancelOpen(false)}
          >
            {t('common.back')}
          </Button>
          <Button
            variant="danger"
            className="flex-1 border-[1.5px] border-danger"
            onClick={() => {
              setConfirmCancelOpen(false);
              onTogglePaid?.();
            }}
          >
            {t('bill.cancelPaymentYes')}
          </Button>
        </div>
      </Modal>
    </>
  );
}
