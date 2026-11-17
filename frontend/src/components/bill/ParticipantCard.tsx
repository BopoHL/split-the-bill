'use client';

import { useId, useState, type FormEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Armchair,
  Check,
  ChevronDown,
  DollarSign,
  ListPlus,
  Loader2,
  RotateCcw,
  Trash2,
  Undo2,
  User,
  UserPlus,
  WalletCards,
  X,
} from 'lucide-react';
import { BillStatus, SplitType, type BillDetail, type BillParticipant } from '@/types/api';
import { participantInitial, participantLabel } from '@/lib/utils/participants';
import { formatCurrency, currencyLabel } from '@/lib/utils/currency';
import { evaluate } from '@/lib/utils/calc';
import { billPositions } from '@/lib/utils/billPositions';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { EASE_OUT } from '@/lib/motion';
import { useStore } from '@/lib/store/useStore';
import ChipButton from '@/components/ui/ChipButton';
import PaidMark from '@/components/ui/PaidMark';
import NumericKeypad from '@/components/ui/NumericKeypad';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import { TourAnchor } from '@/lib/tour/anchors';
import { canBeReminded, reminderState } from '@/lib/utils/reminders';
import UserBadge from '@/components/profile/UserBadge';
import ParticipantPositions from './ParticipantPositions';
import RemindChip, { remindHint } from './RemindChip';

const ROW_INDENT = 'pl-[58px] pr-3';

interface ParticipantCardProps {
  bill: BillDetail;
  participant: BillParticipant;
  /** Open on first render — the viewer's own seat, closed for everyone else. */
  defaultExpanded?: boolean;
  /** Owner: pick dishes for this seat. */
  onAssignItems?: () => void;
  /** Participant, own seat: go and take dishes on the receipt. */
  onPickItems?: () => void;
  /** Owner, manual split: set this seat's amount directly. */
  onAssignAmount?: (id: number, amount: number) => Promise<void>;
  /** Owner: mark an empty seat as paid — nobody is there to press it. */
  onTogglePayment?: (id: number, currentPaid: boolean) => void;
  onDelete?: (id: number) => void;
  onRenameGuest?: (id: number, name: string) => Promise<void>;
  /** Owner: seat somebody on this empty seat or send its personal invite. */
  onAddPerson?: (id: number) => void;
  /** Participant: move onto this empty seat, taking its dishes. */
  onTakeSeat?: () => void;
  /** Owner: remind someone who joined and still owes. */
  onRemind?: (id: number) => Promise<void>;
}

export default function ParticipantCard({
  bill,
  participant: p,
  defaultExpanded = false,
  onAssignItems,
  onPickItems,
  onAssignAmount,
  onTogglePayment,
  onDelete,
  onRenameGuest,
  onAddPerson,
  onTakeSeat,
  onRemind,
}: ParticipantCardProps) {
  const { t } = useTranslation();
  const currentUserId = useStore((s) => s.currentUser?.id);
  const bodyId = useId();
  const [disclosure, setDisclosure] = useState({ defaultExpanded, expanded: defaultExpanded });
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [savingName, setSavingName] = useState(false);
  const [nameSaved, setNameSaved] = useState(false);
  const [editingAmount, setEditingAmount] = useState(false);
  const [amountDraft, setAmountDraft] = useState('');
  const [keypadOpen, setKeypadOpen] = useState(false);
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);
  const [reminding, setReminding] = useState(false);

  const isMe = currentUserId != null && p.user_id === currentUserId;
  const isOwnerRow = p.user_id === bill.owner_id;
  const isOpen = bill.status === BillStatus.OPEN;
  const isClosed = bill.status === BillStatus.CLOSED;
  const byItems = bill.split_type === SplitType.BY_ITEMS;
  const currency = bill.currency ?? 'uzs';
  const displayName = participantLabel(p, t);
  const positionCount = byItems
    ? billPositions(bill.items, bill.participants, bill.currency).filter((position) => position.participantIds.includes(p.id)).length
    : 0;

  // An empty seat has no account to press «paid», so the owner does it for it.
  const canMarkPaid = !!onTogglePayment && p.is_guest && !isOwnerRow && !isClosed && p.allocated_amount > 0;
  const canRename = !!onRenameGuest && p.is_guest && isOpen;
  const canDelete = !!onDelete && !isOwnerRow && isOpen;
  // An empty seat is removed the way it is renamed, from its name; somebody
  // sitting there has no name to edit, so their row keeps the button.
  const deletesFromName = canDelete && canRename;
  const canSetAmount = !!onAssignAmount && isOpen && !byItems;
  // Filling an empty seat is the owner's main job for it, so it stays in sight.
  const canAddPerson = !!onAddPerson && p.is_guest && isOpen;
  const canTakeSeat = !!onTakeSeat && p.is_guest && isOpen;
  // Someone who joined confirms their own payment; the owner can only take one
  // back that never arrived.
  const canUndoPayment = !!onTogglePayment && !p.is_guest && !isOwnerRow && !isClosed && p.is_paid;
  // A paid share is settled; only the owner's own payment leaves it open.
  const canAssignItems = !!onAssignItems && (!p.is_paid || isOwnerRow);
  const canRemind = !!onRemind && canBeReminded(bill, p);
  const now = new Date();
  const reminder = reminderState(p.reminder, now);
  const reminderNote = canRemind ? remindHint(reminder, now, t) : null;
  const hasActions = canAssignItems || !!onPickItems || canSetAmount || canMarkPaid || canUndoPayment
    || (canDelete && !deletesFromName) || canTakeSeat || canRemind;
  // Who and how much stay in sight; the dishes and what can be done with the
  // seat fold away — a list where every row shows its buttons reads as a wall.
  const expandable = positionCount > 0 || hasActions;

  // A seat move can turn this mounted row from someone else's into mine. Follow
  // the new default without an effect, and keep manual toggles across refreshes.
  const expanded = expandable
    && (disclosure.defaultExpanded === defaultExpanded ? disclosure.expanded : defaultExpanded);

  const remind = async () => {
    setReminding(true);
    try {
      await onRemind?.(p.id);
    } finally {
      setReminding(false);
    }
  };

  const startRename = () => {
    setNameDraft(p.guest_name || '');
    setRenaming(true);
  };

  const submitRename = async (event: FormEvent) => {
    event.preventDefault();
    const next = nameDraft.trim();
    if (next === (p.guest_name || '').trim()) {
      setRenaming(false);
      return;
    }
    setSavingName(true);
    try {
      await onRenameGuest?.(p.id, next);
      setRenaming(false);
      setNameSaved(true);
      setTimeout(() => setNameSaved(false), 1600);
    } catch {
      // The caller has already said what went wrong; keep the draft to retry.
    } finally {
      setSavingName(false);
    }
  };

  const startAmountEdit = () => {
    setAmountDraft(p.allocated_amount ? p.allocated_amount.toString() : '');
    setEditingAmount(true);
  };

  const closeAmountEdit = () => {
    setEditingAmount(false);
    setKeypadOpen(false);
  };

  // Folding the seat takes an amount being typed in with it.
  const toggle = () => {
    if (expanded) closeAmountEdit();
    setDisclosure({ defaultExpanded, expanded: !expanded });
  };

  const saveAmount = async () => {
    // The price field's calculator: «5000-3000» is 2000, not 5000. A share
    // below zero is refused; an emptied field still means zero.
    const amount = amountDraft.trim() === '' ? 0 : evaluate(amountDraft);
    if (amount == null || amount < 0 || !onAssignAmount) return;
    await onAssignAmount(p.id, amount);
    closeAmountEdit();
  };

  // On an empty seat the owner can fill, the face's place is the way to fill
  // it: nobody is sitting there to show, and the row stays one line.
  const avatar = canAddPerson ? (
    <button
      type="button"
      onClick={() => onAddPerson?.(p.id)}
      aria-label={t('bill.assignUser')}
      title={t('bill.assignUser')}
      className="btn-hard-sm pointer-events-auto flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-accent text-accent-fg"
    >
      <UserPlus className="h-[17px] w-[17px]" strokeWidth={2.25} />
    </button>
  ) : (
    <span
      className={`flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center overflow-hidden rounded-[6px] font-display text-[13px] font-bold ${
        p.is_guest
          ? 'border-[1.5px] border-dashed border-muted-2 bg-surface-2 text-muted'
          : isMe
            ? 'border-[1.5px] border-outline bg-accent text-accent-fg shadow-[var(--shadow-hard-sm)]'
            : 'border-[1.5px] border-outline bg-surface text-foreground shadow-[var(--shadow-hard-sm)]'
      }`}
    >
      {p.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={p.avatar_url} alt="" className="h-full w-full object-cover" />
      ) : p.is_guest ? (
        // An outline rather than an initial: nobody is sitting here yet.
        <User className="h-[17px] w-[17px]" strokeWidth={1.75} />
      ) : (
        participantInitial(p, t)
      )}
    </span>
  );

  const identity = (
    <span className="min-w-0 flex-1">
      <span className="flex min-w-0 items-center gap-1.5">
        {canRename ? (
          // The name itself is the way to rename an empty seat; the rest of the
          // row still opens it.
          <button
            type="button"
            onClick={startRename}
            aria-label={`${t('bill.renameSeat')}: ${displayName}`}
            className="pointer-events-auto -my-1.5 min-w-0 truncate rounded-[3px] py-1.5 text-left text-[15px] font-semibold leading-tight text-muted underline decoration-muted-2 decoration-dotted decoration-[1.5px] underline-offset-4 transition-colors hover:text-foreground"
          >
            {displayName}
          </button>
        ) : (
          <span className={`truncate text-[15px] font-semibold leading-tight ${p.is_guest ? 'text-muted' : 'text-foreground'}`}>
            {displayName}
          </span>
        )}
        <UserBadge badge={p.badge} />
        <AnimatePresence>
          {nameSaved && (
            <motion.span
              key="saved"
              role="status"
              aria-label={t('common.saved')}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: EASE_OUT }}
              className="flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-full bg-success text-success-fg"
            >
              <Check className="h-3 w-3" strokeWidth={3} />
            </motion.span>
          )}
        </AnimatePresence>
      </span>
    </span>
  );

  const amount = (
    <span className="flex flex-shrink-0 items-center gap-1.5">
      <AnimatePresence initial={false}>
        {p.is_paid && (
          <motion.span
            key="paid"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.6 }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
            className="flex"
          >
            <PaidMark size="sm" />
          </motion.span>
        )}
      </AnimatePresence>
      <span
        className={`font-mono text-[14px] font-bold tabular-nums transition-colors ${
          p.is_paid ? 'text-success' : p.allocated_amount > 0 ? 'text-foreground' : 'text-muted-2'
        }`}
      >
        {formatCurrency(p.allocated_amount, currency)}
      </span>
    </span>
  );

  return (
    <div className="rounded-[inherit]" data-tour={isMe ? TourAnchor.MySeat : undefined}>
      {renaming ? (
        <form onSubmit={(event) => void submitRename(event)} className="flex items-center gap-3 px-3 py-2.5">
          {avatar}
          <span className="flex min-w-0 flex-1 items-center gap-1.5">
            <input
              value={nameDraft}
              onChange={(event) => setNameDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') setRenaming(false);
              }}
              placeholder={t('bill.guestN', { n: String(p.seat_index) })}
              aria-label={t('bill.renameSeat')}
              maxLength={40}
              autoFocus
              className="min-w-0 flex-1 rounded-[6px] border-[1.5px] border-outline bg-background px-2.5 py-1.5 font-medium outline-none focus:border-accent"
            />
            {deletesFromName && (
              <button
                type="button"
                onClick={() => onDelete?.(p.id)}
                disabled={savingName}
                aria-label={t('common.delete')}
                title={t('common.delete')}
                className="btn-hard-sm flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-danger bg-surface text-danger disabled:opacity-60"
              >
                <Trash2 className="h-5 w-5" />
              </button>
            )}
            <button
              type="submit"
              disabled={savingName}
              aria-label={t('common.save')}
              className="btn-hard-sm flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-success text-success-fg disabled:opacity-60"
            >
              {savingName ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Check className="h-5 w-5" strokeWidth={2.5} />}
            </button>
            <button
              type="button"
              onClick={() => setRenaming(false)}
              disabled={savingName}
              aria-label={t('common.cancel')}
              className="btn-hard-sm flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-surface text-muted"
            >
              <X className="h-5 w-5" />
            </button>
          </span>
        </form>
      ) : (
        // The row's summary: everything shown while it is folded, so a press
        // lights all of it.
        <div className={`relative ${expanded ? 'rounded-t-[inherit]' : 'rounded-[inherit]'}`}>
          {expandable && (
            // Stretched under the content so the whole row opens it, while the
            // guest's name and «Add a person» on top of it stay separate targets.
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={bodyId}
              aria-label={displayName}
              onClick={toggle}
              data-tour={TourAnchor.OpenSeat}
              data-tour-key={p.seat_index}
              className="row-press absolute inset-0 rounded-[inherit]"
            />
          )}
          <span className="pointer-events-none relative flex min-w-0 items-center gap-3 px-3 py-2.5">
            {avatar}
            {identity}
            {amount}
            {expandable && (
              <ChevronDown
                aria-hidden="true"
                className={`h-4 w-4 flex-shrink-0 text-muted transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
              />
            )}
          </span>
        </div>
      )}

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="body"
            id={bodyId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <div className={`flex flex-col gap-2.5 pb-3 pt-0.5 ${ROW_INDENT}`}>
              {positionCount > 0 && <ParticipantPositions bill={bill} participant={p} />}
              {editingAmount && (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    inputMode="none"
                    value={amountDraft}
                    onChange={(event) => setAmountDraft(event.target.value)}
                    onFocus={() => setKeypadOpen(true)}
                    aria-label={t('bill.setAmount')}
                    autoFocus
                    className="min-w-0 flex-1 rounded-[6px] border-[1.5px] border-outline bg-background px-3 py-2 text-right font-mono font-semibold text-foreground outline-none focus:border-accent"
                  />
                  <button
                    type="button"
                    onClick={() => void saveAmount()}
                    aria-label={t('common.save')}
                    className="btn-hard-sm flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-success text-success-fg"
                  >
                    <Check className="h-5 w-5" strokeWidth={2.5} />
                  </button>
                  <button
                    type="button"
                    onClick={closeAmountEdit}
                    aria-label={t('common.cancel')}
                    className="btn-hard-sm flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-surface text-muted"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              )}
              {hasActions && (
                <div className="flex flex-wrap items-center gap-2">
                  {canAssignItems && (
                    <ChipButton
                      tone="accent"
                      icon={ListPlus}
                      onClick={onAssignItems}
                      data-tour={TourAnchor.AssignItems}
                      data-tour-key={p.seat_index}
                    >
                      {t('bill.assign')}
                    </ChipButton>
                  )}
                  {canRemind && (
                    <RemindChip state={reminder} now={now} busy={reminding} onRemind={() => void remind()} />
                  )}
                  {onPickItems && (
                    <ChipButton icon={ListPlus} onClick={onPickItems} data-tour={TourAnchor.ChooseItems}>
                      {t('bill.chooseItems')}
                    </ChipButton>
                  )}
                  {canSetAmount && !editingAmount && (
                    <ChipButton icon={WalletCards} onClick={startAmountEdit}>{t('bill.setAmount')}</ChipButton>
                  )}
                  {canSetAmount && !p.is_paid && p.allocated_amount > 0 && (
                    <ChipButton icon={RotateCcw} onClick={() => setConfirmResetOpen(true)}>{t('bill.resetShare')}</ChipButton>
                  )}
                  {(canUndoPayment || (canMarkPaid && p.is_paid)) && (
                    <ChipButton tone="danger" icon={Undo2} onClick={() => setConfirmCancelOpen(true)}>{t('bill.undoPayment')}</ChipButton>
                  )}
                  {canMarkPaid && !p.is_paid && (
                    <ChipButton tone="success" icon={DollarSign} onClick={() => onTogglePayment?.(p.id, false)}>
                      {t('bill.markGuestPaid')}
                    </ChipButton>
                  )}
                  {canTakeSeat && (
                    <ChipButton icon={Armchair} onClick={onTakeSeat}>{t('bill.changeSeat')}</ChipButton>
                  )}
                  {canDelete && !deletesFromName && (
                    <ChipButton
                      tone="danger"
                      icon={Trash2}
                      onClick={() => onDelete?.(p.id)}
                      aria-label={t('common.delete')}
                      title={t('common.delete')}
                      className="ml-auto"
                    />
                  )}
                </div>
              )}
              {reminderNote && <p className="text-[12px] leading-snug text-muted">{reminderNote}</p>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <NumericKeypad
        open={editingAmount && keypadOpen}
        label={t('bill.setAmount')}
        value={amountDraft}
        unit={currencyLabel(currency)}
        thousands
        onChange={setAmountDraft}
        onClose={() => setKeypadOpen(false)}
      />

      <Modal
        isOpen={confirmCancelOpen}
        onClose={() => setConfirmCancelOpen(false)}
        title={t('bill.cancelPaymentTitle')}
        size="sm"
      >
        <p className="text-[15px] leading-snug text-foreground">{t('bill.cancelPaymentConfirm')}</p>
        <div className="mt-5 flex gap-2.5">
          <Button variant="primary" className="flex-1" onClick={() => setConfirmCancelOpen(false)}>
            {t('common.back')}
          </Button>
          <Button
            variant="danger"
            className="flex-1 border-[1.5px] border-danger"
            onClick={() => {
              setConfirmCancelOpen(false);
              onTogglePayment?.(p.id, true);
            }}
          >
            {t('bill.cancelPaymentYes')}
          </Button>
        </div>
      </Modal>

      <Modal
        isOpen={confirmResetOpen}
        onClose={() => setConfirmResetOpen(false)}
        title={t('bill.resetShare')}
        size="sm"
      >
        <p className="text-[15px] leading-snug text-foreground">{t('bill.cancelAllocationAlert')}</p>
        <div className="mt-5 flex gap-2.5">
          <Button variant="primary" className="flex-1" onClick={() => setConfirmResetOpen(false)}>
            {t('common.back')}
          </Button>
          <Button
            variant="danger"
            className="flex-1 border-[1.5px] border-danger"
            onClick={() => {
              setConfirmResetOpen(false);
              void onAssignAmount?.(p.id, 0);
            }}
          >
            {t('common.confirm')}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
