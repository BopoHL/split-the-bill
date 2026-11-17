'use client';

import { useState } from 'react';
import { Check, DollarSign, RotateCcw } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import type { BillDetail, BillParticipant } from '@/types/api';
import { billPositions, groupPositions, hasPaid, heldByPayment, positionIsPaid, sortByState, type BillPosition, type BillPositionGroup } from '@/lib/utils/billPositions';
import { assignBillItemsBatch } from '@/lib/api/bills';
import { formatCurrency } from '@/lib/utils/currency';
import { participantLabel, splitsByDishes } from '@/lib/utils/participants';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { translateApiError } from '@/lib/utils/apiError';
import { showToast } from '@/lib/toast';
import { TourAnchor } from '@/lib/tour/anchors';
import AssignmentAvatars, { FreeSeat } from './AssignmentAvatars';
import SharedMark from './SharedMark';
import LineName from './LineName';
import { track, AnalyticsEvent } from '@/lib/analytics';

type Section = 'unassigned' | 'others' | 'assigned';
type DishLook = 'picked' | 'paid' | 'theirs' | 'open';

const CARD_LOOK: Record<DishLook, string> = {
  picked: 'border-outline bg-accent-weak',
  paid: 'border-success bg-green-weak',
  theirs: 'border-outline bg-taken',
  open: 'border-border bg-surface',
};
const ROW_LOOK: Record<DishLook, string> = {
  picked: 'bg-accent-weak',
  paid: 'bg-green-weak',
  theirs: 'bg-taken',
  open: '',
};

export default function ParticipantItemsDialog({ bill, participant, currentUserId, onBillUpdate, onClose }: {
  bill: BillDetail;
  participant: BillParticipant;
  currentUserId: number;
  onBillUpdate: (bill: BillDetail) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const currency = bill.currency ?? 'uzs';
  const [busy, setBusy] = useState(false);
  // The order is taken once, so rows never move under a finger while the sheet is open.
  const [positions] = useState(() =>
    sortByState(billPositions(bill.items, bill.participants, bill.currency), bill.participants, bill.owner_id),
  );
  const assigned = (dish: BillPosition) => dish.participantIds.includes(participant.id);
  // The dishes this person is to be on: where they are now, until ticked otherwise.
  const [initial] = useState<ReadonlySet<string>>(() => new Set(positions.filter(assigned).map((dish) => dish.key)));
  const [draft, setDraft] = useState(initial);
  const requiresRecalculation = !splitsByDishes(bill);
  const participantLocked = hasPaid(participant, bill.owner_id);
  const locked = (dish: BillPosition) => participantLocked || heldByPayment(dish.participantIds, bill.participants, bill.owner_id);
  const editable = (dish: BillPosition) => !locked(dish);
  const on = (dish: BillPosition) => draft.has(dish.key);
  const paid = (dish: BillPosition) => !requiresRecalculation && positionIsPaid(dish, bill.participants, bill.owner_id);
  const people = (ids: number[]) => bill.participants.filter((person) => ids.includes(person.id));

  // A line goes where its best dish for this person is: anything nobody has yet
  // puts it with what is left to hand out, then lines where others have dishes
  // (still a valid choice: they can be shared), then lines already all theirs.
  const sectionOf = (line: BillPositionGroup): Section =>
    line.positions.some((dish) => dish.participantIds.length === 0) ? 'unassigned'
      : line.positions.some((dish) => !assigned(dish)) ? 'others' : 'assigned';
  const lines = groupPositions(positions);
  const sections = ([
    { key: 'unassigned', label: t('bill.unassigned') },
    { key: 'others', label: t('bill.assignedToOthers') },
    { key: 'assigned', label: participant.user_id === currentUserId ? t('bill.assignedToYou') : t('bill.assignedToThem') },
  ] as const)
    .map((section) => ({ ...section, lines: lines.filter((line) => sectionOf(line) === section.key) }))
    .filter((section) => section.lines.length > 0);

  const put = (dishes: BillPosition[], value: boolean) => setDraft((previous) => {
    const next = new Set(previous);
    for (const dish of dishes) {
      if (value) next.add(dish.key);
      else next.delete(dish.key);
    }
    return next;
  });
  // A line's tick takes, or gives back, the dishes nobody else is on, and the
  // whole of a line shared among all; joining or leaving someone else's dish
  // changes their share, so it is done dish by dish.
  const takeable = (line: BillPositionGroup) =>
    line.positions.filter((dish) => editable(dish)
      && (dish.item.is_shared_globally || dish.participantIds.every((id) => id === participant.id)));
  const toggleLine = (line: BillPositionGroup) => {
    const own = takeable(line);
    put(own, !own.every(on));
  };

  const additions = positions.filter((dish) => on(dish) && !assigned(dish) && editable(dish));
  const removals = positions.filter((dish) => !on(dish) && assigned(dish) && editable(dish));
  const changed = additions.length + removals.length > 0;
  const apply = async () => {
    if (busy || !changed || bill.status !== 'open') return;
    setBusy(true);
    const op = (dish: BillPosition, participantId: number, isAssigned: boolean) => ({
      item_id: dish.item.id, portion_index: dish.portionIndex, expected_count: dish.item.count, participant_id: participantId, is_assigned: isAssigned,
    });
    // Leaving a line shared among all spells it out: everyone else stays on
    // each of its dishes, and this person only on those still ticked.
    const leaving = new Set(removals.filter((dish) => dish.item.is_shared_globally).map((dish) => dish.item.id));
    const ops = [
      ...additions.map((dish) => op(dish, participant.id, true)),
      ...removals.filter((dish) => !leaving.has(dish.item.id)).map((dish) => op(dish, participant.id, false)),
      ...positions.filter((dish) => leaving.has(dish.item.id)).flatMap((dish) =>
        bill.participants.map((person) => op(dish, person.id, person.id !== participant.id || on(dish)))),
    ];
    const shared = [...leaving].map((itemId) => ({ item_id: itemId, is_shared_globally: false }));
    try {
      onBillUpdate(await assignBillItemsBatch(bill.id, currentUserId, ops, shared));
      track(AnalyticsEvent.ItemsAssigned, { bill_id: bill.id, via: 'person', changes: ops.length + shared.length });
      onClose();
    } catch (e) {
      showToast(translateApiError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t));
    } finally { setBusy(false); }
  };

  const look = (dish: BillPosition): DishLook =>
    on(dish) && !assigned(dish) ? 'picked' : paid(dish) ? 'paid' : on(dish) ? 'theirs' : 'open';
  const checkbox = (label: string, dish: BillPosition) => (
    <input type="checkbox" aria-label={label} checked={on(dish)} disabled={busy || !editable(dish)} onChange={() => put([dish], !on(dish))} className="h-6 w-6 shrink-0 accent-accent disabled:accent-foreground" />
  );
  // A dish for everyone is marked as such rather than with everyone's faces.
  const dishStatus = (dish: BillPosition) => (
    <>
      {dish.item.is_shared_globally ? (
        <SharedMark />
      ) : dish.participantIds.length > 0 ? (
        <AssignmentAvatars participants={people(dish.participantIds)} />
      ) : (
        <FreeSeat />
      )}
      {paid(dish) && <DollarSign aria-label={t('bill.participantPaid')} className="h-4 w-4 text-success" />}
    </>
  );

  const singleDish = (dish: BillPosition) => {
    const label = `${dish.item.name}, ${formatCurrency(dish.amount, currency)}`;
    return (
      <label key={dish.key} data-tour={TourAnchor.AssignDish} className={`flex min-h-[76px] items-center gap-3 rounded-[6px] border-[1.5px] p-2.5 ${CARD_LOOK[look(dish)]}`}>
        <span className="flex min-w-0 flex-1 flex-col gap-2">
          <span className="flex flex-wrap justify-between gap-2 text-[13px] font-semibold"><span className="min-w-0 [overflow-wrap:anywhere]">{dish.item.name}</span><span className="font-mono">{formatCurrency(dish.amount, currency)}</span></span>
          <span className="flex flex-wrap items-center gap-2">{dishStatus(dish)}</span>
        </span>
        {checkbox(label, dish)}
      </label>
    );
  };

  // A line of several dishes: one tick for all its dishes nobody else is on,
  // and each dish below it, named like the line, for just some of them.
  const dishLine = (line: BillPositionGroup) => {
    const { item, positions: dishes } = line;
    const own = takeable(line);
    const all = own.length > 0 ? own.every(on) : dishes.every(on);
    const some = dishes.some(on);
    const label = `${item.name} ×${dishes.length}, ${formatCurrency(item.item_sum, currency)}`;
    return (
      <div key={line.key} className={`overflow-hidden rounded-[6px] border-[1.5px] bg-surface ${some ? 'border-outline' : 'border-border'}`}>
        <label data-tour={TourAnchor.AssignDish} className={`flex min-h-16 items-center gap-3 p-2.5 ${dishes.every(assigned) ? 'bg-taken' : ''}`}>
          <span className="flex min-w-0 flex-1 flex-col gap-2">
            <span className="flex flex-wrap justify-between gap-2 text-[13px] font-semibold"><span className="min-w-0 [overflow-wrap:anywhere]"><LineName name={item.name} count={dishes.length} /></span><span className="font-mono">{formatCurrency(item.item_sum, currency)}</span></span>
            <span className="flex flex-wrap items-center gap-2">
              {item.is_shared_globally ? <SharedMark /> : line.participantIds.length > 0 && <AssignmentAvatars participants={people(line.participantIds)} />}
            </span>
          </span>
          <input type="checkbox" aria-label={label} checked={all} ref={(input) => { if (input) input.indeterminate = some && !all; }} disabled={busy || own.length === 0} onChange={() => toggleLine(line)} className="h-6 w-6 shrink-0 accent-accent disabled:accent-foreground" />
        </label>
        {!item.is_shared_globally && (
          <ul className="border-t border-dashed border-border">
            {dishes.map((dish) => (
              <li key={dish.key} className="border-b border-dashed border-border last:border-b-0">
                <label className={`flex min-h-12 items-center gap-3 py-2 pl-5 pr-2.5 ${ROW_LOOK[look(dish)]}`}>
                  <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="min-w-0 text-[13px] font-medium [overflow-wrap:anywhere]">{item.name}</span>
                    {dishStatus(dish)}
                  </span>
                  <span className="shrink-0 font-mono text-[12px] font-bold">{formatCurrency(dish.amount, currency)}</span>
                  {checkbox(`${item.name}, ${formatCurrency(dish.amount, currency)}`, dish)}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  return (
    <Modal
      isOpen
      onClose={() => !busy && onClose()}
      title={participant.user_id === currentUserId ? t('bill.chooseItems') : t('bill.assignItems')}
      size="sm"
      tourAnchor={TourAnchor.PickSheet}
    >
      <div className="flex min-h-0 flex-col gap-4">
        <div className="flex items-center gap-3"><AssignmentAvatars participants={[participant]} /><span className="font-display text-[14px] font-bold">{participantLabel(participant, t)}</span></div>
        {requiresRecalculation && <p role="note" className="border-l-[3px] border-accent pl-3 text-[13px] leading-snug">{t('bill.recalculateSharesHint')}</p>}
        <div className="min-h-0 space-y-4 overflow-y-auto overscroll-contain p-0.5 pb-1" role="group" aria-label={t('bill.items')}>
          {sections.map((section) => (
            <section key={section.key} data-assignment-group={section.key} className="space-y-2">
              <h3 className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
                {section.label}
              </h3>
              {section.lines.map((line) => line.positions.length === 1 ? singleDish(line.positions[0]) : dishLine(line))}
            </section>
          ))}
          {positions.length === 0 && <p className="text-sm text-muted">{t('bill.noItemsAdded')}</p>}
        </div>
        <p className="text-[12px] text-muted" aria-live="polite">
          {t('bill.newAssignmentsCount', { count: String(additions.length) })}
          {removals.length > 0 && ` · ${t('bill.removedAssignmentsCount', { count: String(removals.length) })}`}
        </p>
        <div className="flex gap-3">
          <Button variant="outline" aria-label={t('bill.resetSelection')} title={t('bill.resetSelection')} onClick={() => setDraft(initial)} disabled={busy} className="!min-h-11 !w-12 shrink-0 !px-0"><RotateCcw className="h-5 w-5" /></Button>
          <Button variant="success" onClick={() => void apply()} disabled={!changed || busy} isLoading={busy} data-tour={TourAnchor.AssignConfirm} className="min-w-0 flex-1 !text-[13px]"><Check className="h-5 w-5 shrink-0" />{requiresRecalculation ? t('bill.recalculateAndAssign') : t('common.confirm')}</Button>
        </div>
      </div>
    </Modal>
  );
}
