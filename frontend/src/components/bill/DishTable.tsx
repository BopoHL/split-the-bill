'use client';

import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { createPortal } from 'react-dom';
import { Check, X } from 'lucide-react';
import type { BillDetail, BillParticipant } from '@/types/api';
import { assignBillItemsBatch } from '@/lib/api/bills';
import { billPositions, hasPaid, type BillPosition } from '@/lib/utils/billPositions';
import { formatCurrency, type Currency } from '@/lib/utils/currency';
import { participantInitial, participantLabel } from '@/lib/utils/participants';
import { translateApiError } from '@/lib/utils/apiError';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { hapticFeedback, showBackButton } from '@/lib/telegram/init';
import { useScrollLock } from '@/hooks/useScrollLock';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import AssignmentAvatars, { FreeSeat } from './AssignmentAvatars';
import ItemAssignmentDialog from './ItemAssignmentDialog';
import LineName from './LineName';

/** Held this long without moving, a dish is picked up; moving sooner is a scroll. */
const HOLD_MS = 220;
const SLOP_PX = 8;

interface Press {
  position: BillPosition;
  x: number;
  y: number;
  timer: ReturnType<typeof setTimeout>;
  active: boolean;
}

interface Drag {
  position: BillPosition;
  x: number;
  y: number;
  /** The seat under the finger, by id. */
  seat: number | null;
}

/** The seat under a point on screen, by the data-seat its element carries. */
const seatAt = (x: number, y: number): number | null => {
  const seat = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-seat]');
  return seat ? Number(seat.dataset.seat) : null;
};

function Seat({ participant, currency, ownerId, lit }: {
  participant: BillParticipant;
  currency: Currency;
  ownerId: number;
  lit: boolean;
}) {
  const { t } = useTranslation();
  const label = participantLabel(participant, t);
  const paid = hasPaid(participant, ownerId);
  return (
    <div
      data-seat={participant.id}
      aria-label={label}
      className={`relative flex w-[76px] flex-col items-center gap-1 rounded-xl border-[1.5px] px-1.5 py-2 transition-transform duration-150 ${
        lit ? 'scale-110 border-accent bg-accent-weak shadow-[var(--shadow-hard)]' : 'border-outline bg-surface shadow-[var(--shadow-hard-sm)]'
      } ${paid ? 'opacity-55' : ''}`}
    >
      <span className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border-[1.5px] border-outline bg-background font-display text-[15px] font-bold">
        {participant.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={participant.avatar_url} alt="" className="h-full w-full object-cover" />
        ) : participantInitial(participant, t)}
      </span>
      <span className="w-full truncate text-center text-[11px] font-bold leading-tight">{label}</span>
      <span className="font-mono text-[10px] tabular-nums text-muted">{formatCurrency(participant.allocated_amount, currency)}</span>
      {paid && (
        <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-success text-success-fg">
          <Check className="h-3 w-3" strokeWidth={3} />
        </span>
      )}
    </div>
  );
}

/**
 * The table: the dishes in the middle and the people around them. A dish held
 * and dragged onto someone is theirs; dragged onto someone else as well, it is
 * shared. A tap opens the dish to take people off it.
 */
export default function DishTable({ bill, currentUserId, onBillUpdate, onClose }: {
  bill: BillDetail;
  currentUserId: number;
  onBillUpdate: (bill: BillDetail) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const currency: Currency = bill.currency ?? 'uzs';
  const [drag, setDrag] = useState<Drag | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<BillPosition | null>(null);
  const press = useRef<Press | null>(null);
  // A drop ends with a click on the dish it started from; that click is not a tap.
  const dropped = useRef(false);
  const dishesRef = useRef<HTMLDivElement>(null);
  useScrollLock(true);

  const seats = [...bill.participants].sort((a, b) => a.seat_index - b.seat_index);
  const half = Math.ceil(seats.length / 2);
  // Lines for the whole table are everyone's already; the rest, ones nobody has first.
  const positions = billPositions(bill.items, bill.participants, currency)
    .filter((position) => !position.item.is_shared_globally)
    .sort((a, b) => Number(a.participantIds.length > 0) - Number(b.participantIds.length > 0));

  useEffect(() => showBackButton(onClose), [onClose]);

  // Once a dish is held the finger moves it, not the list under it.
  useEffect(() => {
    const list = dishesRef.current;
    if (!list) return;
    const hold = (event: TouchEvent) => {
      if (press.current?.active) event.preventDefault();
    };
    list.addEventListener('touchmove', hold, { passive: false });
    return () => list.removeEventListener('touchmove', hold);
  }, []);

  const give = async (position: BillPosition, seat: BillParticipant) => {
    if (position.participantIds.includes(seat.id)) return;
    if (hasPaid(seat, bill.owner_id)) {
      hapticFeedback('error');
      showToast(t('bill.paidPositionLocked'));
      return;
    }
    setBusy(true);
    try {
      const updated = await assignBillItemsBatch(bill.id, currentUserId, [{
        item_id: position.item.id,
        participant_id: seat.id,
        is_assigned: true,
        portion_index: position.portionIndex,
        expected_count: position.item.count,
      }]);
      onBillUpdate(updated);
      hapticFeedback('success');
      track(AnalyticsEvent.ItemsAssigned, { bill_id: bill.id, via: 'table', changes: 1 });
    } catch (error) {
      hapticFeedback('error');
      showToast(translateApiError((error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail, t));
    } finally {
      setBusy(false);
    }
  };

  const down = (position: BillPosition) => (event: PointerEvent<HTMLButtonElement>) => {
    // A phone sends no click after a drag, so the last drop's mark goes here.
    dropped.current = false;
    if (busy || event.button > 0) return;
    const card = event.currentTarget;
    const pointerId = event.pointerId;
    const held: Press = {
      position,
      x: event.clientX,
      y: event.clientY,
      active: false,
      timer: setTimeout(() => {
        held.active = true;
        card.setPointerCapture?.(pointerId);
        hapticFeedback('light');
        setDrag({ position, x: held.x, y: held.y, seat: null });
      }, HOLD_MS),
    };
    press.current = held;
  };

  const move = (event: PointerEvent<HTMLButtonElement>) => {
    const held = press.current;
    if (!held) return;
    if (!held.active) {
      if (Math.hypot(event.clientX - held.x, event.clientY - held.y) > SLOP_PX) {
        clearTimeout(held.timer);
        press.current = null;
      }
      return;
    }
    const { clientX: x, clientY: y } = event;
    setDrag((current) => current && { ...current, x, y, seat: seatAt(x, y) });
  };

  const up = (event: PointerEvent<HTMLButtonElement>) => {
    const held = press.current;
    press.current = null;
    if (!held) return;
    clearTimeout(held.timer);
    if (!held.active) return;
    dropped.current = true;
    setDrag(null);
    const seat = seats.find((participant) => participant.id === seatAt(event.clientX, event.clientY));
    if (seat) void give(held.position, seat);
  };

  const cancel = () => {
    if (press.current) clearTimeout(press.current.timer);
    press.current = null;
    setDrag(null);
  };

  const seatRow = (row: BillParticipant[]) => (
    <div className="flex flex-wrap justify-center gap-2 px-3 py-3">
      {row.map((participant) => (
        <Seat key={participant.id} participant={participant} currency={currency} ownerId={bill.owner_id} lit={drag?.seat === participant.id} />
      ))}
    </div>
  );

  if (typeof document === 'undefined') return null;
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('bill.table')}
      className="fixed inset-0 z-40 flex flex-col bg-background pb-[var(--content-safe-bottom)] pt-[var(--content-safe-top)] text-foreground"
    >
      <div className="flex items-center justify-between px-4 pt-2">
        <h2 className="font-display text-[18px] font-extrabold">{t('bill.table')}</h2>
        <button type="button" onClick={onClose} aria-label={t('common.close')} className="flex h-11 w-11 items-center justify-center rounded-lg text-muted hover:text-foreground">
          <X className="h-5 w-5" />
        </button>
      </div>

      {seatRow(seats.slice(0, half))}

      <div ref={dishesRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain border-y-[1.5px] border-dashed border-border bg-surface-2/60 px-3 py-3">
        <ul className="grid grid-cols-2 gap-2">
          {positions.map((position) => {
            const eaters = bill.participants.filter((participant) => position.participantIds.includes(participant.id));
            const free = eaters.length === 0;
            return (
              <li key={position.key}>
                <button
                  type="button"
                  data-position-key={position.key}
                  onPointerDown={down(position)}
                  onPointerMove={move}
                  onPointerUp={up}
                  onPointerCancel={cancel}
                  onContextMenu={(event) => event.preventDefault()}
                  onClick={() => {
                    if (dropped.current) {
                      dropped.current = false;
                      return;
                    }
                    setEditing(position);
                  }}
                  className={`flex min-h-[84px] w-full select-none flex-col items-start gap-1.5 rounded-lg border-[1.5px] bg-surface p-2.5 text-left shadow-[var(--shadow-hard-sm)] [-webkit-touch-callout:none] ${
                    free ? 'border-accent' : 'border-outline'
                  } ${drag?.position.key === position.key ? 'opacity-40' : ''}`}
                >
                  <span className="line-clamp-2 text-[13px] font-semibold leading-snug [overflow-wrap:anywhere]">
                    <LineName name={position.item.name} count={1} />
                  </span>
                  <span className="font-mono text-[12px] tabular-nums text-muted">{formatCurrency(position.amount, currency)}</span>
                  <span className="mt-auto">{free ? <FreeSeat /> : <AssignmentAvatars participants={eaters} />}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {seatRow(seats.slice(half))}

      {drag && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed z-50 w-40 -translate-x-1/2 -translate-y-1/2 rotate-[-4deg] rounded-lg border-2 border-accent bg-surface p-2.5 shadow-[var(--shadow-lifted)]"
          style={{ left: drag.x, top: drag.y }}
        >
          <span className="line-clamp-2 text-[13px] font-semibold leading-snug">{drag.position.item.name}</span>
          <span className="font-mono text-[12px] tabular-nums text-muted">{formatCurrency(drag.position.amount, currency)}</span>
        </div>
      )}

      {editing && (
        <ItemAssignmentDialog
          positions={[positions.find((position) => position.key === editing.key) ?? editing]}
          participants={bill.participants}
          billId={bill.id}
          currentUserId={currentUserId}
          ownerId={bill.owner_id}
          currency={currency}
          onBillUpdate={onBillUpdate}
          onClose={() => setEditing(null)}
        />
      )}
    </div>,
    document.body,
  );
}
