'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { CircleCheck, Grab, Plus } from 'lucide-react';
import type { BillItem, BillItemUpdate, BillParticipant, BillDetail, Receipt } from '@/types/api';
import type { Currency } from '@/lib/utils/currency';
import { assignBillItemsBatch, deleteBillItem, getBill, updateBillItem } from '@/lib/api/bills';
import { billPositions, groupPositions, heldByPayment, positionIsPaid, sortByState, type BillPosition, type BillPositionGroup } from '@/lib/utils/billPositions';
import { translateApiError } from '@/lib/utils/apiError';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { EASE_OUT } from '@/lib/motion';
import { showToast } from '@/lib/toast';
import type { DishSelection } from '@/hooks/useDishSelection';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import ChipButton from '@/components/ui/ChipButton';
import ItemAssignmentDialog from './ItemAssignmentDialog';
import LineName from './LineName';
import PositionEditor from './PositionEditor';
import { DishRow, LineRow, ROW_PADDING, type ReceiptView, type RowPick } from './ReceiptRows';
import { track, AnalyticsEvent } from '@/lib/analytics';

interface ItemsSectionProps {
  billId: number;
  items: BillItem[];
  participants: BillParticipant[];
  currentUserId: number;
  isCreator: boolean;
  isClosed: boolean;
  ownerId?: number;
  requiresRecalculation?: boolean;
  currency?: Currency;
  isAdding?: boolean;
  onAddItem?: (name: string, price: number, count: number) => void | Promise<void>;
  onCancelAdd?: () => void;
  onStartAdd?: () => void;
  /** Opens the table, where dishes are dragged onto people. */
  onTable?: () => void;
  onBillUpdate?: (bill: BillDetail) => void;
  receipts?: Receipt[];
  /** The owner's picking of several dishes to hand out at once. */
  selection?: DishSelection;
}

// Only what was edited is sent: a line's stored unit price is rounded down,
// so sending it back unchanged would still move the line's total.
const edits = (item: BillItem, name: string, price: number, count: number): BillItemUpdate => ({
  ...(name === item.name ? {} : { name }),
  ...(price === item.price ? {} : { price }),
  ...(count === item.count ? {} : { count }),
});
const ROW_MOTION = { duration: 0.28, ease: EASE_OUT };
const ROW_BOX = '-mx-2 rounded-[6px] border-b border-dashed border-border';

export default function ItemsSection({ billId, items, participants, currentUserId, isCreator, isClosed, ownerId, requiresRecalculation = false, currency, isAdding = false, onAddItem, onCancelAdd, onStartAdd, onTable, onBillUpdate, receipts = [], selection }: ItemsSectionProps) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  // Lines of several dishes start folded so a long receipt stays short.
  const [unfolded, setUnfolded] = useState<ReadonlySet<number>>(new Set());
  const [assigning, setAssigning] = useState<BillPosition[] | null>(null);
  // A line is edited as a whole — name, unit price and how many dishes it has.
  const [editing, setEditing] = useState<BillItem | null>(null);
  // Deleting is part of editing: a line goes from its edit form, whole.
  const [deleting, setDeleting] = useState<BillItem | null>(null);
  const positions = billPositions(items, participants, currency);
  const me = participants.find((p) => p.user_id === currentUserId);
  const view: ReceiptView = { participants, me, ownerId, isCreator, isClosed, requiresRecalculation, currency, busy };
  const picking = !!selection?.active && isCreator && !isClosed;
  // Picking is for more than one dish; once on, «Cancel» stays within reach.
  const canPick = !!selection && isCreator && !isClosed && (positions.length > 1 || picking);

  const run = async (action: () => Promise<void>) => {
    if (busy || isClosed) return;
    setBusy(true);
    try { await action(); } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      showToast(translateApiError(detail, t));
    } finally { setBusy(false); }
  };
  const refresh = async () => onBillUpdate?.(await getBill(billId, currentUserId));
  const take = (position: BillPosition, assigned: boolean) => run(async () => {
    if (!me || me.is_paid || position.item.is_shared_globally || requiresRecalculation) return;
    const updated = await assignBillItemsBatch(billId, currentUserId, [{
      item_id: position.item.id, participant_id: me.id, is_assigned: assigned,
      portion_index: position.portionIndex, expected_count: position.item.count,
    }]);
    onBillUpdate?.(updated);
    track(AnalyticsEvent.ItemTaken, { bill_id: billId, taken: assigned });
  });
  const takeOne = (group: BillPositionGroup) => {
    const free = group.positions.find((position) => position.participantIds.length === 0);
    if (free) void take(free, true);
  };
  const save = async (item: BillItem, name: string, price: number, count: number) => {
    const changes = edits(item, name, price, count);
    if (Object.keys(changes).length === 0) {
      setEditing(null);
      return;
    }
    await updateBillItem(billId, item.id, changes);
    track(AnalyticsEvent.ItemUpdated, { bill_id: billId });
    setEditing(null);
    await refresh();
  };
  const remove = () => run(async () => {
    if (!deleting) return;
    await deleteBillItem(billId, deleting.id);
    track(AnalyticsEvent.ItemDeleted, { bill_id: billId });
    setDeleting(null);
    setEditing(null);
    await refresh();
  });
  const toggleLine = (itemId: number) => setUnfolded((previous) => {
    const next = new Set(previous);
    if (!next.delete(itemId)) next.add(itemId);
    return next;
  });

  // What is still to hand out comes first and settled dishes sink, receipt order
  // within each; a line stands where its most open dish would. A legacy split
  // has no item assignments worth ranking by.
  const lines = groupPositions(requiresRecalculation ? positions : sortByState(positions, participants, ownerId));
  // Rows glide to their new place instead of jumping from under a tap. Measured
  // only when the order changes, so a panel hidden behind the other tab never
  // records a 0×0 box to animate from.
  const orderKey = lines.map((line) => line.positions.map((position) => position.key).join(',')).join('|');
  const sections = receipts.length > 1
    ? [...receipts.map((receipt) => ({ key: String(receipt.task_id), title: `${receipt.index}. ${receipt.merchant_name || t('receipt.untitledReceipt')}`, lines: lines.filter((line) => line.item.receipt_task_id === receipt.task_id) })), {
      key: 'manual', title: t('receipt.withoutReceipt'), lines: lines.filter((line) => !receipts.some((receipt) => receipt.task_id === line.item.receipt_task_id)),
    }].filter((section) => section.lines.length > 0)
    : [{ key: 'all', title: '', lines }];

  const settled = (dishes: BillPosition[]) => !requiresRecalculation && dishes.every((position) => positionIsPaid(position, participants, ownerId));
  // A dish someone has paid for keeps its split, so it cannot be picked.
  const pickOf = (dishes: BillPosition[]): RowPick | undefined => {
    if (!picking) return undefined;
    const open = dishes.filter((position) => !heldByPayment(position.participantIds, participants, ownerId));
    const on = open.filter((position) => selection.keys.has(position.key)).length;
    return {
      state: on === 0 ? 'none' : on === open.length ? 'all' : 'some',
      disabled: busy || open.length === 0,
      onToggle: () => selection.toggle(open.map((position) => position.key)),
    };
  };
  // An open line leaves the tint to the dishes picked in it, unless all are.
  const tone = (dishes: BillPosition[], open = false) => {
    const state = pickOf(dishes)?.state;
    if (state === 'all' || (state === 'some' && !open)) return 'bg-accent-weak';
    return settled(dishes) ? 'bg-green-weak' : '';
  };
  const isEditing = (item: BillItem) => !isClosed && !picking && editing?.id === item.id;
  const editor = (item: BillItem) => (
    <PositionEditor key={item.id} name={item.name} price={item.price} count={item.count} total={item.item_sum} currency={currency} onCancel={() => setEditing(null)} onSave={(name, price, count) => save(item, name, price, count)} onDelete={() => setDeleting(item)} />
  );
  const dish = (position: BillPosition, nested: boolean) => (
    <DishRow
      position={position}
      view={view}
      nested={nested}
      pick={pickOf([position])}
      onTake={(assigned) => void take(position, assigned)}
      onEdit={nested ? undefined : () => setEditing(position.item)}
      onAssign={() => setAssigning([position])}
    />
  );

  return (
    <div>
      {positions.length === 0 && !isAdding && <p className="py-4 text-center font-mono text-[12px] text-muted-2">{t('bill.noItemsAdded')}</p>}
      {(canPick || (onTable && positions.length > 0)) && (
        <div className="mb-2 flex items-center gap-2.5">
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.08em] text-muted">{t('bill.items')} · {lines.length}</span>
          <span aria-hidden="true" className="min-w-3 flex-1 border-t-[1.5px] border-dashed border-border" />
          {onTable && !picking && positions.length > 0 && <ChipButton icon={Grab} onClick={onTable}>{t('bill.table')}</ChipButton>}
          {canPick && (
            <ChipButton icon={picking ? undefined : CircleCheck} aria-pressed={picking} onClick={picking ? selection.stop : selection.start}>
              {picking ? t('common.cancel') : t('bill.selectSeveral')}
            </ChipButton>
          )}
        </div>
      )}
      {sections.map((section) => (
        <section key={section.key} aria-label={section.title || t('bill.items')}>
          {section.title && <h3 className="mb-2 mt-4 border-b border-dashed border-border pb-2 font-mono text-[11px] font-bold text-muted [overflow-wrap:anywhere]">{section.title}</h3>}
          <ul className="space-y-2.5">
            {section.lines.map((line) => {
              const [first] = line.positions;
              return line.positions.length === 1 ? (
                <motion.li key={first.key} layout="position" layoutDependency={orderKey} transition={ROW_MOTION} data-position-key={first.key} className={`${ROW_BOX} ${tone(line.positions)}`}>
                  <div className={`relative rounded-[inherit] ${ROW_PADDING}`}>{isEditing(line.item) ? editor(line.item) : dish(first, false)}</div>
                </motion.li>
              ) : (
                <motion.li key={`line:${line.key}`} layout="position" layoutDependency={orderKey} transition={ROW_MOTION} data-line-key={line.key} className={`${ROW_BOX} ${tone(line.positions, unfolded.has(line.item.id))}`}>
                  {isEditing(line.item) ? <div className={ROW_PADDING}>{editor(line.item)}</div> : (
                    <LineRow
                      group={line}
                      view={view}
                      expanded={unfolded.has(line.item.id)}
                      pick={pickOf(line.positions)}
                      onToggle={() => toggleLine(line.item.id)}
                      onTakeOne={() => takeOne(line)}
                      onEdit={() => setEditing(line.item)}
                      onAssign={() => setAssigning(line.positions)}
                    >
                      <ul className="ml-1 border-l-[1.5px] border-dashed border-border pl-3">
                        {line.positions.map((position) => (
                          <motion.li key={position.key} layout="position" layoutDependency={orderKey} transition={ROW_MOTION} data-position-key={position.key} className={`relative -mr-2 rounded-[6px] border-b border-dashed border-border py-2 pl-2 pr-2 last:border-b-0 ${tone([position])}`}>
                            {dish(position, true)}
                          </motion.li>
                        ))}
                      </ul>
                    </LineRow>
                  )}
                </motion.li>
              );
            })}
          </ul>
        </section>
      ))}
      {!isClosed && isCreator && !picking && (isAdding && onAddItem ? <div className="mt-4"><PositionEditor currency={currency} focusName onSave={onAddItem} onCancel={() => onCancelAdd?.()} /></div> : onStartAdd && (
        <button type="button" onClick={onStartAdd} className="mt-4 flex min-h-11 w-full items-center justify-center gap-2 rounded-[6px] border-[1.5px] border-dashed border-outline bg-surface px-3 py-2 font-display text-[12px] font-bold hover:bg-accent-weak"><Plus className="h-4 w-4" />{t('bill.addItem')}</button>
      ))}
      {assigning && !isClosed && <ItemAssignmentDialog key={assigning.map((position) => position.key).join(',')} positions={assigning} participants={participants} billId={billId} currentUserId={currentUserId} ownerId={ownerId} requiresRecalculation={requiresRecalculation} currency={currency} onBillUpdate={onBillUpdate} onClose={() => setAssigning(null)} />}
      <Modal isOpen={!!deleting && !isClosed} onClose={() => !busy && setDeleting(null)} title={t('bill.deletePosition')} size="sm">
        <p className="mb-5 text-[14px] [overflow-wrap:anywhere]">{deleting && <LineName name={deleting.name} count={deleting.count} />}</p>
        <div className="flex gap-3"><Button variant="outline" onClick={() => setDeleting(null)} disabled={busy} className="flex-1">{t('common.cancel')}</Button><Button variant="danger" onClick={() => void remove()} isLoading={busy} className="flex-1">{t('common.delete')}</Button></div>
      </Modal>
    </div>
  );
}
