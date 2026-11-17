'use client';

import { useRouter } from 'next/navigation';
import { eraseDemoBill } from '@/lib/api/demoBills';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { useStore } from '@/lib/store/useStore';
import { useTour } from '@/lib/tour/useTour';

/** The two ways out of a tour. Either way it is not offered on its own again,
 *  and the host tour's demo bill goes. */
export function useTourExit() {
  const router = useRouter();
  const completeOnboarding = useStore((state) => state.completeOnboarding);
  const completeGuestTour = useStore((state) => state.completeGuestTour);

  const settle = () => {
    const { tour, demoBillId } = useTour.getState();
    if (tour.name === 'guest') {
      void completeGuestTour();
      return;
    }
    if (demoBillId != null) void eraseDemoBill(demoBillId).catch(() => {});
    void completeOnboarding();
  };

  const skip = () => {
    const { tour, stepIndex, demoBillId, stop } = useTour.getState();
    track(AnalyticsEvent.TourSkipped, { step: tour.steps[stepIndex].id, tour: tour.name });
    settle();
    stop();
    // On the bill about to be erased, or on the way to it.
    if (demoBillId != null) router.replace('/');
  };

  /** Reached the end. The host tour stays on screen for its last words. */
  const complete = () => {
    track(AnalyticsEvent.TourCompleted, { tour: useTour.getState().tour.name });
    settle();
    useTour.getState().forgetDemoBill();
  };

  return { skip, complete };
}
