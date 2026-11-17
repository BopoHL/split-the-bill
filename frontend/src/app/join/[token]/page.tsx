'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { claimSeat, getSeatsByToken } from '@/lib/api/bills';
import type { BillSeats, SeatPreview } from '@/types/api';
import { useStore } from '@/lib/store/useStore';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { arriveAsGuest } from '@/lib/tour/arrival';
import AppHeader from '@/components/layout/AppHeader';
import SeatPicker from '@/components/bill/SeatPicker';
import MoveSeatDialog from '@/components/bill/MoveSeatDialog';

/**
 * Landing page for an invite link when the bill has seats to choose from.
 *
 * Reachable without being a participant — the seats endpoint is keyed by the
 * unguessable token, because you cannot be in the bill before you've picked a
 * place in it.
 */
export default function JoinBillPage() {
  const { token } = useParams<{ token: string }>();
  // Carried over by AppShell when the seat had to be picked by hand, so the
  // invite that brought the person here is not lost on the detour — and the
  // seat it named, when it named one: a personal invite that would have moved
  // somebody lands here so the move can be asked about, not forgotten.
  const searchParams = useSearchParams();
  const inviteCode = searchParams.get('inv');
  const invitedSeatId = Number(searchParams.get('seat')) || null;
  const router = useRouter();
  const { t } = useTranslation();
  const currentUser = useStore((s) => s.currentUser);

  const [seats, setSeats] = useState<BillSeats | null>(null);
  const [claiming, setClaiming] = useState<number | null>(null);
  // Set when the server says this pick would move somebody who is already
  // seated — picking a FIRST seat never asks.
  const [movingToSeatId, setMovingToSeatId] = useState<number | null>(null);
  const [error, setError] = useState(false);
  // The invite's own seat is asked about once, as soon as the table is known
  // and the seat is still free; after that the picker is theirs.
  const askedAboutInvitedSeat = useRef(false);

  // The owner keeps assigning items while people are deciding where to sit, so
  // a snapshot taken on load goes stale exactly when it matters most.
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    const askAboutInvitedSeat = (table: BillSeats) => {
      if (!invitedSeatId || askedAboutInvitedSeat.current) return;
      askedAboutInvitedSeat.current = true;
      const invited = table.seats.find((seat) => seat.id === invitedSeatId);
      const seatedElsewhere = table.seats.some((seat) => seat.is_me);
      if (invited && !invited.is_taken && seatedElsewhere) setMovingToSeatId(invitedSeatId);
    };
    const load = () =>
      getSeatsByToken(token, currentUser?.id)
        .then((next) => {
          if (cancelled) return;
          // One failed poll on a shaky connection must not hide the picker for good.
          setError(false);
          setSeats(next);
          askAboutInvitedSeat(next);
        })
        .catch(() => {
          if (!cancelled) setError(true);
        });

    void load();
    const id = setInterval(load, 5000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void load();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [token, currentUser?.id, invitedSeatId]);

  const take = useCallback(
    async (seatId: number, confirmed: boolean) => {
      if (!seats || !currentUser) return;
      setClaiming(seatId);
      try {
        await claimSeat(seats.bill_id, seatId, currentUser.id, inviteCode, confirmed, token);
        track(AnalyticsEvent.ParticipantJoined, { via: 'invite', bill_id: seats.bill_id });
        arriveAsGuest(seats.bill_id);
        router.push(`/bill/${seats.bill_id}`);
      } catch (e) {
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setClaiming(null);
        if (detail === 'SEAT_MOVE_CONFIRM') {
          // They already sit somewhere on this bill; moving swaps their items.
          setMovingToSeatId(seatId);
          return;
        }
        setMovingToSeatId(null);
        showToast(translateApiError(detail, t));
        getSeatsByToken(token, currentUser.id).then(setSeats).catch(() => {});
      }
    },
    [seats, currentUser, router, t, token, inviteCode],
  );

  const handlePick = useCallback(
    async (seat: SeatPreview) => {
      if (!seats || !currentUser) return;
      if (seat.is_me) {
        router.push(`/bill/${seats.bill_id}`);
        return;
      }
      await take(seat.id, false);
    },
    [seats, currentUser, router, take],
  );

  return (
    <div className="min-h-screen bg-background pb-[calc(1rem+var(--content-safe-bottom))]">
      <AppHeader>
        <div className="flex items-center gap-0.5 font-display text-lg font-bold tracking-[0.02em]">
          SPLIT<span className="text-accent">·</span>BILL
        </div>
      </AppHeader>

      {error ? (
        <p className="mx-auto max-w-2xl px-4 py-10 text-center text-[15px] text-muted">
          {t('errors.billNotFound')}
        </p>
      ) : !seats || !currentUser ? (
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-accent" />
        </div>
      ) : (
        <SeatPicker seats={seats} busySeatId={claiming} onPick={handlePick} />
      )}

      <MoveSeatDialog
        isOpen={movingToSeatId != null}
        onCancel={() => setMovingToSeatId(null)}
        onConfirm={() => {
          const target = movingToSeatId!;
          setMovingToSeatId(null);
          void take(target, true);
        }}
      />
    </div>
  );
}
