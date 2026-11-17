'use client';

import { useState } from 'react';
import { Check, RotateCcw, UsersRound } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import PaidMark from '@/components/ui/PaidMark';
import RoundCheck, { type CheckState } from '@/components/ui/RoundCheck';
import type { BillDetail, BillParticipant } from '@/types/api';
import { dealDishes, groupPositions, hasPaid, positionsTotal, type BillPosition, type BillPositionGroup } from '@/lib/utils/billPositions';
import { assignBillItemsBatch, type BillItemAssignOp, type BillItemSharedOp } from '@/lib/api/bills';
import { formatAmount, formatCurrency, type Currency } from '@/lib/utils/currency';
import { tableSplit, toCents } from '@/lib/utils/itemSplit';
import { participantLabel } from '@/lib/utils/participants';
import { dishUnit, participantUnit } from '@/lib/utils/plural';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';
import AssignmentAvatars from './AssignmentAvatars';
import { TourAnchor } from '@/lib/tour/anchors';
import LineName from './LineName';
import { track, AnalyticsEvent } from '@/lib/analytics';

/** How much of the dishes being assigned a person is on. */
type Coverage = CheckState;

// The checkbox itself is hidden behind the round tick, so its card shows the focus.
const CARD = 'flex min-h-16 items-center gap-3 rounded-[6px] border-[1.5px] p-2.5 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent';

/**
 * Who shares the given dishes: a single dish, a whole receipt line, or dishes
 * picked across several lines. Ticking a person puts them on every dish in
 * view; someone on only a few of them stays that way unless the tick is changed.
 * Once the ticks change, dishes of one line that divide evenly among the ticked
 * people are handed out instead — three dishes for three people is one each.
 */
export default function ItemAssignmentDialog({ positions, participants, billId, currentUserId, ownerId, requiresRecalculation = false, currency, onBillUpdate, onClose }: {
  positions: BillPosition[];
  participants: BillParticipant[];
  billId: number;
  currentUserId: number;
  ownerId?: number;
  requiresRecalculation?: boolean;
  currency?: Currency;
  onBillUpdate?: (bill: BillDetail) => void;
  onClose: () => void;
}) {
  const { t, language } = useTranslation();
  const lines = groupPositions(positions);
  const whole = (line: BillPositionGroup) => line.positions.length === Math.max(1, line.item.count);
  const amount = positionsTotal(positions);
  const [initial] = useState(() => new Map(participants.map((p): [number, Coverage] => {
    const on = positions.filter((position) => position.participantIds.includes(p.id)).length;
    return [p.id, on === 0 ? 'none' : on === positions.length ? 'all' : 'some'];
  })));
  const [draft, setDraft] = useState(initial);
  const [sharedBefore] = useState(() => lines.every((line) => line.item.is_shared_globally && whole(line)));
  const [shareAll, setShareAll] = useState(sharedBefore);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  // Someone who joins while the sheet is open is on none of these dishes.
  const before = (p: BillParticipant) => initial.get(p.id) ?? 'none';
  const coverage = (p: BillParticipant) => draft.get(p.id) ?? 'none';
  const lockedByPayment = (p: BillParticipant) => hasPaid(p, ownerId);
  const ticked = participants.filter((p) => coverage(p) === 'all').map((p) => p.id);
  const deal = touched && lines.length === 1 && !shareAll && participants.every((p) => coverage(p) !== 'some')
    ? dealDishes(positions, ticked)
    : null;
  // Someone left on only some of the dishes keeps exactly those.
  const wants = (p: BillParticipant, position: BillPosition) => deal
    ? deal.get(position.portionIndex)!.includes(p.id)
    : coverage(p) === 'all' || (coverage(p) === 'some' && position.participantIds.includes(p.id));
  // A paid share must stay as it is, so a dish a paid person is on cannot be re-split.
  const frozen = participants.some((p) => lockedByPayment(p) && before(p) !== 'none');
  // Sharing among all would put a paid person on the dish as well. A whole
  // line becomes shared; part of one gets everyone on its picked dishes.
  const canShareAll = !participants.some(lockedByPayment);

  const everyone = (value: Coverage) => new Map(participants.map((p) => [p.id, value]));
  const toggleShareAll = () => {
    setTouched(true);
    setDraft(everyone(shareAll ? 'none' : 'all'));
    setShareAll(!shareAll);
  };
  const toggle = (p: BillParticipant) => {
    setTouched(true);
    setShareAll(false);
    setDraft((previous) => new Map(previous).set(p.id, previous.get(p.id) === 'all' ? 'none' : 'all'));
  };
  const reset = () => {
    setTouched(true);
    setShareAll(false);
    setDraft(everyone('none'));
  };

  const changesOf = (line: BillPositionGroup, ops: BillItemAssignOp[], shared: BillItemSharedOp[]) => {
    const { item } = line;
    const op = (portionIndex: number, participantId: number, isAssigned: boolean): BillItemAssignOp => ({
      item_id: item.id, portion_index: portionIndex, expected_count: item.count, participant_id: participantId, is_assigned: isAssigned,
    });
    // Nobody's tick differs here: a line picked only alongside others stays as it was.
    const untouched = line.positions.every((position) =>
      participants.every((p) => position.participantIds.includes(p.id) === wants(p, position)));
    if (shareAll && (whole(line) || item.is_shared_globally)) {
      if (!item.is_shared_globally) shared.push({ item_id: item.id, is_shared_globally: true });
    } else if (item.is_shared_globally && !untouched) {
      // Leaving a global share spells out every dish, so dishes outside this
      // dialog stay with everyone instead of falling back to stale assignments.
      shared.push({ item_id: item.id, is_shared_globally: false });
      const inView = new Map(line.positions.map((position) => [position.portionIndex, position]));
      for (let index = 0; index < Math.max(1, item.count); index++) {
        const position = inView.get(index);
        for (const p of participants) ops.push(op(index, p.id, !position || wants(p, position)));
      }
    } else {
      for (const p of participants) {
        for (const position of line.positions) {
          const on = position.participantIds.includes(p.id);
          if (on !== wants(p, position)) ops.push(op(position.portionIndex, p.id, !on));
        }
      }
    }
  };

  const ops: BillItemAssignOp[] = [];
  const shared: BillItemSharedOp[] = [];
  for (const line of lines) changesOf(line, ops, shared);
  const changed = requiresRecalculation || ops.length > 0 || shared.length > 0;

  const table = tableSplit(participants, ownerId, currency);
  const perSeat = new Map<number, number>();
  for (const line of lines) {
    const lineCents = line.positions.reduce((sum, position) => sum + toCents(position.amount), 0);
    for (const [id, cents] of table.splitEvenly(lineCents, participants.map((p) => p.id))) perSeat.set(id, (perSeat.get(id) ?? 0) + cents);
  }
  const lowest = Math.min(...perSeat.values()) / 100;
  const highest = Math.max(...perSeat.values()) / 100;
  const eachShare = lowest === highest ? formatCurrency(highest, currency) : `${formatAmount(lowest)}–${formatCurrency(highest, currency)}`;

  const apply = async () => {
    if (busy || !changed || frozen) return;
    setBusy(true);
    try {
      const updated = await assignBillItemsBatch(billId, currentUserId, ops, shared);
      onBillUpdate?.(updated);
      track(AnalyticsEvent.ItemsAssigned, { bill_id: billId, via: 'dishes', changes: ops.length + shared.length });
      onClose();
    } catch (e) {
      showToast(translateApiError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t));
    } finally { setBusy(false); }
  };

  return (
    <Modal isOpen onClose={() => !busy && onClose()} title={t('bill.assignPeople')} size="sm">
      <div className="flex min-h-0 flex-col gap-4">
        <div>
          <p className="flex flex-wrap justify-between gap-2 text-[13px] font-semibold">
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {lines.length === 1 ? <LineName name={lines[0].item.name} count={positions.length} /> : `${positions.length} ${dishUnit(positions.length, language)}`}
            </span>
            <span className="font-mono">{formatCurrency(amount, currency)}</span>
          </p>
          {lines.length > 1 && (
            <ul aria-label={t('bill.items')} className="mt-2 flex flex-wrap gap-1.5">
              {lines.map((line) => (
                <li key={line.key} className="rounded-[5px] border-[1.5px] border-border bg-background px-2 py-1 text-[12px] font-semibold [overflow-wrap:anywhere]">
                  {whole(line)
                    ? <LineName name={line.item.name} count={line.positions.length} />
                    : `${line.item.name} · ${t('bill.dishesOf', { count: String(line.positions.length), total: String(Math.max(1, line.item.count)) })}`}
                </li>
              ))}
            </ul>
          )}
          {positions.length > 1 && (
            <p className="mt-1.5 font-mono text-[11px] text-muted">
              {lines.length > 1
                ? t('bill.selectionAssignHint')
                : !deal
                  ? t('bill.lineAssignHint', { count: String(positions.length) })
                  : ticked.length <= positions.length
                    ? t('bill.lineDealHint', { count: String(positions.length / ticked.length) })
                    : t('bill.lineDealSharedHint', { count: String(ticked.length / positions.length) })}
            </p>
          )}
        </div>
        {requiresRecalculation && <p role="note" className="border-l-[3px] border-accent pl-3 text-[13px] leading-snug">{t('bill.recalculateSharesHint')}</p>}
        {frozen && <p role="note" className="border-l-[3px] border-success pl-3 text-[13px] leading-snug">{t('bill.paidPositionLocked')}</p>}
        {canShareAll && (
          <div className="flex flex-col gap-3 px-0.5">
            <label className={`${CARD} ${shareAll ? 'border-outline bg-accent-weak' : 'border-border bg-surface'} ${busy ? 'cursor-not-allowed' : 'cursor-pointer'}`}>
              <span aria-hidden="true" className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[5px] border-[1.5px] border-outline bg-emphasis text-emphasis-fg shadow-[var(--shadow-hard-sm)]">
                <UsersRound className="h-3.5 w-3.5" strokeWidth={2.5} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block break-words font-display text-[14px] font-bold">{t('bill.splitAmongAll')}</span>
                <span className="font-mono text-[11px] text-muted">
                  {t('bill.splitAmongAllHint', {
                    people: `${participants.length} ${participantUnit(participants.length, language)}`,
                    amount: eachShare,
                  })}
                </span>
              </span>
              <input type="checkbox" aria-label={t('bill.splitAmongAll')} checked={shareAll} disabled={busy} onChange={toggleShareAll} className="sr-only" />
              <RoundCheck state={shareAll ? 'all' : 'none'} />
            </label>
            <div className="flex items-center gap-2.5 font-mono text-[11px] font-bold uppercase tracking-[0.08em] text-muted">
              {t('bill.orPickPeople')}
              <span aria-hidden="true" className="flex-1 border-t-[1.5px] border-dashed border-border" />
            </div>
          </div>
        )}
        <div className="min-h-0 space-y-2 overflow-y-auto overscroll-contain p-0.5 pb-1" role="group" aria-label={t('bill.participants')}>
          {participants.map((p) => {
            const state = coverage(p);
            const partial = state === 'some' ? positions.filter((position) => position.participantIds.includes(p.id)).length : 0;
            const paid = lockedByPayment(p);
            const disabled = busy || frozen || paid;
            return (
              <label key={p.id} data-tour={TourAnchor.ItemPerson} data-tour-key={p.seat_index} className={`${CARD} ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'} ${state === 'all' ? 'border-outline bg-accent-weak' : state === 'some' ? 'border-outline bg-surface' : 'border-border bg-surface'}`}>
                <AssignmentAvatars participants={[p]} />
                <span className="min-w-0 flex-1">
                  <span className="block break-words font-display text-[14px] font-bold">{participantLabel(p, t)}</span>
                  <span className="font-mono text-[11px] text-muted">
                    {formatCurrency(p.allocated_amount, currency)}
                    {partial > 0 && ` · ${t('bill.dishesOf', { count: String(partial), total: String(positions.length) })}`}
                  </span>
                  {paid && <span className="block font-mono text-[11px] font-semibold text-success">{t('bill.paidAssignmentLocked')}</span>}
                </span>
                <input type="checkbox" aria-label={participantLabel(p, t)} checked={state === 'all'} ref={(input) => { if (input) input.indeterminate = state === 'some'; }} disabled={disabled} onChange={() => toggle(p)} className="sr-only" />
                {paid ? <PaidMark size="sm" /> : <RoundCheck state={state} />}
              </label>
            );
          })}
        </div>
        <div className="flex gap-3">
          <Button variant="outline" aria-label={t('bill.resetSelection')} title={t('bill.resetSelection')} onClick={reset} disabled={busy || frozen} className="!min-h-11 !w-12 shrink-0 !px-0"><RotateCcw className="h-5 w-5" /></Button>
          <Button variant="success" onClick={() => void apply()} disabled={!changed || busy || frozen} isLoading={busy} data-tour={TourAnchor.AssignConfirm} className="min-w-0 flex-1 !text-[13px]"><Check className="h-5 w-5 shrink-0" />{requiresRecalculation ? t('bill.recalculateAndAssign') : t('common.confirm')}</Button>
        </div>
      </div>
    </Modal>
  );
}
