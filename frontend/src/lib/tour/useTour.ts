import { create } from 'zustand';
import { track, setAnalyticsContext, AnalyticsEvent } from '@/lib/analytics';
import { HOST_TOUR, type Tour, type TourStep, type TourStepId } from './script';

/** home: asked for from the empty home screen, where a newcomer lands. */
export type TourSource = 'first_run' | 'settings' | 'invite' | 'home';

interface TourState {
  active: boolean;
  tour: Tour;
  stepIndex: number;
  /** The bill the tour made, once it exists — the one to erase afterwards. */
  demoBillId: number | null;
  /** Who «sat down» after the pretend invite, for the bubbles that name them. */
  friends: string[];
  /** The tour typed its card into the new bill. */
  cardStaged: boolean;
  start: (source: TourSource, tour?: Tour) => void;
  /** Move on from `from`. A no-op once the tour is past it, so a tap that
   *  lands twice (a label forwarding its click to its checkbox) moves once. */
  advance: (from: TourStepId) => void;
  /** Back to the step before `from` — its press did not lead anywhere. */
  rewind: (from: TourStepId) => void;
  setDemoBill: (billId: number) => void;
  /** The demo bill is gone; nothing left to clean up. */
  forgetDemoBill: () => void;
  setFriends: (names: string[]) => void;
  stageCard: () => void;
  stop: () => void;
  /** An invite is being opened: home is only passed through on the way to the
   *  bill, and its first-run welcome waits. */
  arriving: boolean;
  setArriving: (arriving: boolean) => void;
  /** The bill someone has just joined, where the guest tour is to start. */
  guestBillId: number | null;
  offerGuestTour: (billId: number) => void;
  /** Takes up the offer made for this bill, if any — it is good once. */
  takeGuestOffer: (billId: number) => boolean;
}

const IDLE = { active: false, tour: HOST_TOUR, stepIndex: 0, demoBillId: null, friends: [], cardStaged: false };

export const useTour = create<TourState>()((set, get) => ({
  ...IDLE,
  start: (source, tour = HOST_TOUR) => {
    set({ ...IDLE, active: true, tour });
    setAnalyticsContext({ in_tour: tour.name });
    track(AnalyticsEvent.TourStarted, { source, tour: tour.name });
  },
  advance: (from) => {
    const { active, tour, stepIndex } = get();
    if (!active || tour.steps[stepIndex].id !== from) return;
    const next = Math.min(stepIndex + 1, tour.steps.length - 1);
    set({ stepIndex: next });
    track(AnalyticsEvent.TourStep, { step: tour.steps[next].id });
  },
  rewind: (from) => {
    const { active, tour, stepIndex } = get();
    if (!active || stepIndex === 0 || tour.steps[stepIndex].id !== from) return;
    set({ stepIndex: stepIndex - 1 });
  },
  setDemoBill: (demoBillId) => set({ demoBillId }),
  forgetDemoBill: () => set({ demoBillId: null }),
  setFriends: (friends) => set({ friends }),
  stageCard: () => set({ cardStaged: true }),
  stop: () => {
    set(IDLE);
    setAnalyticsContext({});
  },
  arriving: false,
  setArriving: (arriving) => set({ arriving }),
  guestBillId: null,
  offerGuestTour: (guestBillId) => set({ guestBillId }),
  takeGuestOffer: (billId) => {
    if (get().guestBillId !== billId) return false;
    set({ guestBillId: null });
    return true;
  },
}));

export function useTourStep(): TourStep | null {
  return useTour((state) => (state.active ? state.tour.steps[state.stepIndex] : null));
}
