'use client';

import { useId, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, ListPlus, Pencil, Plus, Undo2 } from 'lucide-react';
import type { BillParticipant } from '@/types/api';
import { formatCurrency, type Currency } from '@/lib/utils/currency';
import { heldByPayment, positionIsPaid, type BillPosition, type BillPositionGroup } from '@/lib/utils/billPositions';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { EASE_OUT } from '@/lib/motion';
import ChipButton from '@/components/ui/ChipButton';
import PaidMark from '@/components/ui/PaidMark';
import RoundCheck, { type CheckState } from '@/components/ui/RoundCheck';
import AssignmentAvatars, { FreeSeat } from './AssignmentAvatars';
import SharedMark from './SharedMark';
import { TourAnchor } from '@/lib/tour/anchors';
import LineName from './LineName';

/** Who is looking at the receipt and what they may do there, shared by every row. */
export interface ReceiptView {
  participants: BillParticipant[];
  me?: BillParticipant;
  ownerId?: number;
  isCreator: boolean;
  isClosed: boolean;
  requiresRecalculation: boolean;
  currency?: Currency;
  busy: boolean;
}

interface OwnerRowActions {
  /** Lines are edited — and deleted — whole, from their edit form, so a dish
   *  inside one has no edit of its own. */
  onEdit?: () => void;
  onAssign: () => void;
}

/** A row while dishes are being picked: the row itself is the checkbox. */
export interface RowPick {
  state: CheckState;
  disabled: boolean;
  onToggle: () => void;
}

/** A receipt row's own padding; a row fills its list item edge to edge. */
export const ROW_PADDING = 'px-2 py-2.5';
const ROW_NAME = 'min-w-0 flex-1 text-[14px] font-medium leading-snug [overflow-wrap:anywhere]';
const ROW_AMOUNT = 'shrink-0 whitespace-nowrap font-mono text-[13px] font-bold tabular-nums';

const holdsPayment = (view: ReceiptView, ids: number[]) => heldByPayment(ids, view.participants, view.ownerId);

/** The owner's row actions, icons only so a row keeps to one line. */
function OwnerActions({ label, locked, busy, onEdit, onAssign }: OwnerRowActions & { label: string; locked: boolean; busy: boolean }) {
  const { t } = useTranslation();
  const lockHint = locked ? t('bill.paidPositionLocked') : undefined;
  return (
    <>
      {onEdit && <button type="button" disabled={busy || locked} title={lockHint ?? t('common.edit')} aria-label={`${t('common.edit')}: ${label}`} onClick={onEdit} className="flex h-9 w-9 items-center justify-center rounded-[5px] text-muted hover:bg-surface-2 hover:text-accent disabled:opacity-35"><Pencil className="h-4 w-4" /></button>}
      <ChipButton tone="accent" icon={ListPlus} disabled={busy || locked} onClick={onAssign} title={lockHint ?? t('bill.assign')} aria-label={t('bill.assign')} data-tour={TourAnchor.ItemAssign} />
    </>
  );
}

/**
 * A row being picked. A tap anywhere on it ticks it — the target is stretched
 * under the row, padding included — and the round tick leads the row. Its
 * actions step aside meanwhile; whatever stays pressable inside opts back in.
 */
function Picked({ label, pick, small = false, children }: { label: string; pick: RowPick; small?: boolean; children: ReactNode }) {
  return (
    <>
      <button
        type="button"
        role="checkbox"
        aria-checked={pick.state === 'all' ? true : pick.state === 'some' ? 'mixed' : false}
        aria-label={label}
        disabled={pick.disabled}
        onClick={pick.onToggle}
        className="row-press absolute inset-0 rounded-[inherit] disabled:cursor-not-allowed"
      />
      <div className={`pointer-events-none relative flex items-start gap-2.5 ${pick.disabled ? 'opacity-50' : ''}`}>
        <span className="flex h-9 shrink-0 items-center"><RoundCheck state={pick.state} size={small ? 'sm' : 'md'} /></span>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </>
  );
}

/**
 * One dish: a line of a single dish, or — `nested` — one of a longer line's
 * dishes. Either keeps to one line where it fits: name, amount, actions. A
 * single dish adds a second line only for who is on it; a nested one keeps
 * even that inline, drops the word from its «Take», and shows a free dish as
 * an empty seat.
 */
export function DishRow({ position, view, nested = false, pick, onTake, ...owner }: OwnerRowActions & {
  position: BillPosition;
  view: ReceiptView;
  nested?: boolean;
  pick?: RowPick;
  onTake: (assigned: boolean) => void;
}) {
  const { t } = useTranslation();
  const { participants, me, ownerId, isCreator, isClosed, requiresRecalculation, currency, busy } = view;
  const assigned = participants.filter((p) => position.participantIds.includes(p.id));
  const paid = !requiresRecalculation && positionIsPaid(position, participants, ownerId);
  const locked = holdsPayment(view, position.participantIds);
  const mine = !!me && position.participantIds.includes(me.id);
  const shared = position.item.is_shared_globally;
  const amount = formatCurrency(position.amount, currency);
  const lineHeight = pick ? 'min-h-9' : '';

  // A dish everyone shares says so; the whole table's faces would add nothing.
  const status = (
    <>
      {shared ? <SharedMark /> : requiresRecalculation ? null : assigned.length > 0 ? <AssignmentAvatars participants={assigned} /> : nested ? <FreeSeat /> : null}
      {paid && <PaidMark />}
    </>
  );
  const actions = isClosed || pick ? null : isCreator ? (
    <OwnerActions label={position.item.name} locked={locked} busy={busy} {...owner} />
  ) : me && !shared && !paid && !requiresRecalculation ? (
    <ChipButton tone={mine ? 'default' : 'accent'} icon={mine ? Undo2 : Plus} disabled={busy || me.is_paid || locked} onClick={() => onTake(!mine)} title={locked || me.is_paid ? t('bill.paidPositionLocked') : mine ? t('bill.dropMine') : undefined} aria-label={mine ? t('bill.dropMine') : t('bill.take')}>
      {mine || nested ? null : t('bill.take')}
    </ChipButton>
  ) : null;

  // One line — name, amount, actions — and, for a single dish, a second only
  // for who is on it.
  const hasStatus = (!requiresRecalculation && assigned.length > 0) || shared || paid;
  const row = nested ? (
    <div className={`flex flex-wrap items-center gap-x-2 gap-y-1.5 ${lineHeight}`}>
      <span className="flex min-w-0 flex-1 basis-0 flex-wrap items-center gap-x-2 gap-y-1">
        <span className="min-w-0 text-[13px] font-medium leading-snug [overflow-wrap:anywhere]">{position.item.name}</span>
        {status}
      </span>
      <span className="shrink-0 font-mono text-[12px] font-bold tabular-nums">{amount}</span>
      {actions && <div className="ml-auto flex shrink-0 items-center gap-1">{actions}</div>}
    </div>
  ) : (
    <>
      <div className={`flex items-center gap-2 ${lineHeight}`}>
        <span className={ROW_NAME}>{position.item.name}</span>
        <span className={ROW_AMOUNT}>{amount}</span>
        {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
      </div>
      {hasStatus && <div className="mt-1.5 flex flex-wrap items-center gap-2">{status}</div>}
    </>
  );
  if (!pick) return row;
  // A line's dishes share its name, so each is told apart by its place in it.
  const label = nested
    ? `${position.item.name} · ${t('bill.dishesOf', { count: String(position.portionIndex + 1), total: String(Math.max(1, position.item.count)) })}`
    : position.item.name;
  return <Picked label={label} pick={pick} small={nested}>{row}</Picked>;
}

/**
 * A line of several dishes, folded into one row: «Samsa ×4», its total, who is
 * on it and how many dishes are still free. The whole line is assigned, shared,
 * edited or removed from here; its dishes open underneath for one-by-one work.
 * A line shared among everyone has nothing to open — every dish is everyone's.
 * It fills the row it sits in, padding included, so a press lights the row whole.
 * While dishes are being picked, a tap picks the line and only its chevron opens it.
 */
export function LineRow({ group, view, expanded, onToggle, onTakeOne, pick, children, ...owner }: OwnerRowActions & {
  group: BillPositionGroup;
  view: ReceiptView;
  expanded: boolean;
  onToggle: () => void;
  onTakeOne: () => void;
  pick?: RowPick;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const dishesId = useId();
  const { participants, me, ownerId, isCreator, isClosed, requiresRecalculation, currency, busy } = view;
  const { item, positions } = group;
  const shared = item.is_shared_globally;
  const label = `${item.name} ×${positions.length}`;
  const assigned = participants.filter((p) => group.participantIds.includes(p.id));
  const free = positions.filter((position) => position.participantIds.length === 0).length;
  const paid = !requiresRecalculation && positions.every((position) => positionIsPaid(position, participants, ownerId));
  const locked = holdsPayment(view, group.participantIds);
  const chevron = `h-4 w-4 text-muted transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`;

  const row = (
    <>
      <div className={`flex items-center gap-2 ${pick ? 'min-h-9' : ''}`}>
        <span className={ROW_NAME}>
          <LineName name={item.name} count={positions.length} />
          {!shared && (pick ? (
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={dishesId}
              aria-label={`${t('bill.showDishes')}: ${label}`}
              onClick={onToggle}
              className="pointer-events-auto -my-2 ml-0.5 inline-flex h-8 w-8 items-center justify-center rounded-md align-middle hover:bg-surface-2"
            >
              <ChevronDown aria-hidden="true" className={chevron} />
            </button>
          ) : (
            <ChevronDown aria-hidden="true" className={`ml-1 inline align-[-3px] ${chevron}`} />
          ))}
        </span>
        <span className={ROW_AMOUNT}>{formatCurrency(item.item_sum, currency)}</span>
        {!isClosed && !pick && (
          <div className="pointer-events-auto flex shrink-0 items-center gap-1">
            {isCreator ? (
              <OwnerActions label={label} locked={locked} busy={busy} {...owner} />
            ) : me && !shared && !requiresRecalculation && free > 0 ? (
              <ChipButton tone="accent" icon={Plus} disabled={busy || me.is_paid} onClick={onTakeOne} title={me.is_paid ? t('bill.paidPositionLocked') : undefined} aria-label={`${t('bill.takeOne')}: ${label}`}>
                {t('bill.takeOne')}
              </ChipButton>
            ) : null}
          </div>
        )}
      </div>
      {((!requiresRecalculation && assigned.length > 0) || shared || paid) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {shared ? <SharedMark /> : !requiresRecalculation && assigned.length > 0 && <AssignmentAvatars participants={assigned} />}
          {paid && <PaidMark />}
        </div>
      )}
    </>
  );

  return (
    <>
      <div className={`relative ${ROW_PADDING} ${expanded ? 'rounded-t-[inherit]' : 'rounded-[inherit]'}`}>
        {pick ? <Picked label={label} pick={pick}>{row}</Picked> : (
          <>
            {!shared && (
              // Stretched under the row so a tap anywhere opens the dishes, while
              // the actions above it stay their own targets.
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={dishesId}
                aria-label={label}
                onClick={onToggle}
                className="row-press absolute inset-0 rounded-[inherit]"
              />
            )}
            <div className="pointer-events-none relative">{row}</div>
          </>
        )}
      </div>
      <AnimatePresence initial={false}>
        {!shared && expanded && (
          <motion.div
            key="dishes"
            id={dishesId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <div className="px-2 pb-2.5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
