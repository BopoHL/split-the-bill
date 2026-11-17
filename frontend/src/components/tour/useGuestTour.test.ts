import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BillStatus, SplitType } from '@/types/api';
import { billFixture, participantFixture } from '@/test/billFixtures';

vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: {} }));

import { useTour } from '@/lib/tour/useTour';
import { useGuestTour } from './useGuestTour';

const seat = participantFixture({ id: 2, user_id: 20, seat_index: 1 });
const ids = () => useTour.getState().tour.steps.map((step) => step.id);

afterEach(() => useTour.setState({ active: false, stepIndex: 0, guestBillId: null }));

describe('useGuestTour', () => {
  it('starts the guest tour on the bill it was offered for', () => {
    useTour.getState().offerGuestTour(1);

    renderHook(() => useGuestTour(billFixture(), seat));

    expect(useTour.getState()).toMatchObject({ active: true, guestBillId: null });
    expect(ids()).toContain('guestPick');
  });

  it('leaves picking out of it on a bill already split by hand', () => {
    useTour.getState().offerGuestTour(1);

    const shared = billFixture({
      split_type: SplitType.MANUAL,
      participants: [participantFixture({ allocated_amount: 500 }), { ...seat, allocated_amount: 500 }],
    });

    renderHook(() => useGuestTour(shared, seat));

    expect(ids()).not.toContain('guestPick');
  });

  it('does nothing on a bill nobody offered it for', () => {
    useTour.getState().offerGuestTour(99);

    renderHook(() => useGuestTour(billFixture(), seat));

    expect(useTour.getState().active).toBe(false);
  });

  it('waits for the guest’s seat to be there to show', () => {
    useTour.getState().offerGuestTour(1);
    const { rerender } = renderHook(({ mine }) => useGuestTour(billFixture({ status: BillStatus.OPEN }), mine), {
      initialProps: { mine: undefined as typeof seat | undefined },
    });
    expect(useTour.getState().active).toBe(false);

    rerender({ mine: seat });

    expect(useTour.getState().active).toBe(true);
  });

  it('does not cut into a tour already running', () => {
    useTour.getState().start('settings');
    useTour.getState().offerGuestTour(1);

    renderHook(() => useGuestTour(billFixture(), seat));

    expect(useTour.getState().tour.name).toBe('host');
  });
});
