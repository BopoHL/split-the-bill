'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Check } from 'lucide-react';
import type { BillSeats, SeatPreview } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface SeatPickerProps {
  seats: BillSeats;
  busySeatId?: number | null;
  onPick: (seat: SeatPreview) => void;
}

/**
 * «Which one are you?» — the screen a guest lands on from an invite link.
 *
 * Seats exist before anyone joins, so this is not a formality: the owner may
 * have already put dishes on each plate, and picking a seat is what makes those
 * dishes yours. That's why every seat shows what it already owes.
 */
export default function SeatPicker({ seats, busySeatId, onPick }: SeatPickerProps) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<number | null>(null);

  const label = (seat: SeatPreview) =>
    seat.display_name || seat.guest_name || t('bill.guestN', { n: String(seat.seat_index) });

  return (
    <div className="mx-auto w-full max-w-[calc(42rem+var(--content-safe-left)+var(--content-safe-right))] py-6 pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))]">
      <h1 className="font-display text-[22px] font-bold text-foreground">{t('bill.pickSeat')}</h1>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{t('bill.pickSeatHint')}</p>

      <div className="mt-5 flex flex-col gap-2.5">
        {seats.seats.map((seat) => {
          const disabled = seat.is_taken && !seat.is_me;
          const busy = pending === seat.id || busySeatId === seat.id;

          return (
            <motion.button
              key={seat.id}
              type="button"
              disabled={disabled || busy}
              whileTap={disabled ? undefined : { x: 2, y: 3 }}
              onClick={() => {
                setPending(seat.id);
                onPick(seat);
              }}
              className={`flex w-full items-start gap-3 rounded-[10px] border-[1.5px] p-3.5 text-left transition-colors ${
                disabled
                  ? 'border-border bg-surface-2 opacity-60'
                  : 'border-outline bg-surface shadow-[var(--shadow-hard-sm)]'
              }`}
            >
              <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-[7px] border-[1.5px] border-outline bg-background font-display text-[14px] font-bold">
                {seat.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={seat.avatar_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  label(seat).charAt(0).toUpperCase()
                )}
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate font-display text-[15px] font-bold text-foreground">
                    {label(seat)}
                  </span>
                  {seat.is_me && <Check className="h-4 w-4 flex-shrink-0 text-success" />}
                </span>

                {seat.items.length > 0 && (
                  <span className="mt-1 block font-mono text-[11px] leading-relaxed text-muted-2">
                    {seat.items.map((i) => i.name).join(', ')}
                  </span>
                )}
              </span>

              <span className="flex flex-shrink-0 flex-col items-end gap-1">
                <span className="font-mono text-[15px] font-bold tabular-nums text-foreground">
                  {formatCurrency(seat.allocated_amount, seats.currency)}
                </span>
                <span className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-muted-2">
                  {seat.is_me
                    ? t('bill.yourSeat')
                    : disabled
                      ? t('bill.seatTaken')
                      : t('bill.takeSeat')}
                </span>
              </span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
