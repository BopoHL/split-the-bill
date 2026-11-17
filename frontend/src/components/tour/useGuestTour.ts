'use client';

import { useEffect } from 'react';
import type { BillDetail, BillParticipant } from '@/types/api';
import { guestTour } from '@/lib/tour/script';
import { useTour } from '@/lib/tour/useTour';
import { canPickOwnItems } from '@/lib/utils/participants';

/** Starts the guest tour on the bill it was offered for, once the person's
 *  seat on it is there to show. */
export function useGuestTour(bill: BillDetail, seat: BillParticipant | undefined) {
  const offered = useTour((state) => state.guestBillId === bill.id);
  const ready = offered && seat != null;
  const canPickItems = seat != null && canPickOwnItems(bill, seat);

  useEffect(() => {
    if (!ready) return;
    const tour = useTour.getState();
    if (!tour.takeGuestOffer(bill.id) || tour.active) return;
    tour.start('invite', guestTour({ canPickItems }));
  }, [ready, bill.id, canPickItems]);
}
