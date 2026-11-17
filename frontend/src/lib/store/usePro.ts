import { create } from 'zustand';
import type { PaywallReason, ProOverview } from '@/types/pro';
import { getPro } from '@/lib/api/pro';
import { setPersonProperties, track, AnalyticsEvent } from '@/lib/analytics';

interface ProState {
  /** What the server last said about the viewer's Pro; null until it has. */
  overview: ProOverview | null;
  load: (userId: number) => Promise<ProOverview | null>;
  set: (overview: ProOverview) => void;
  /** The paywall is open over this, or closed. */
  paywall: PaywallReason | null;
  /** What the person was doing when the paywall stopped them, to carry on with once they have Pro. */
  resume: (() => void) | null;
  openPaywall: (reason?: PaywallReason, resume?: () => void) => void;
  closePaywall: () => void;
  /** Whether a scan may start now; when today's free ones are spent the
   *  paywall opens instead. Unknown counts let it through to the server. */
  allowScan: () => boolean;
}

export const usePro = create<ProState>()((set, get) => {
  const remember = (overview: ProOverview) => {
    set({ overview });
    setPersonProperties({ pro: overview.active, pro_trial: overview.trial, pro_subscription: overview.subscription });
  };
  const showPaywall = (reason: PaywallReason, resume: (() => void) | null = null) => {
    if (get().paywall === reason) return;
    set({ paywall: reason, resume });
    track(AnalyticsEvent.PaywallOpened, { reason });
  };
  return {
    overview: null,
    load: async (userId) => {
      try {
        const overview = await getPro(userId);
        remember(overview);
        return overview;
      } catch (error) {
        console.error('Error loading Pro:', error);
        return null;
      }
    },
    set: remember,
    paywall: null,
    resume: null,
    openPaywall: (reason = 'general', resume) => showPaywall(reason, resume),
    closePaywall: () => set({ paywall: null, resume: null }),
    allowScan: () => {
      if (get().overview?.scans_left_today !== 0) return true;
      showPaywall('scans');
      return false;
    },
  };
});

/** Whether the viewer has Pro right now, as far as the app knows. */
export const useIsPro = () => usePro((state) => state.overview?.active ?? false);

/**
 * For something only Pro can do: whether it is locked for the viewer, and a
 * wrapper that runs the action or opens the paywall over it instead. Until the
 * status is known nothing is locked — the server has the last word anyway.
 */
export function useProGate(reason: PaywallReason, freeLeft?: (overview: ProOverview) => number | null | undefined) {
  // A few go free without Pro: locked once they are spent, or when the count is unknown.
  const locked = usePro((state) => state.overview !== null && !state.overview.active
    && (freeLeft ? (freeLeft(state.overview) ?? 0) === 0 : true));
  const openPaywall = usePro((state) => state.openPaywall);
  const gated = <Args extends unknown[]>(action: (...args: Args) => unknown) =>
    (...args: Args) => {
      if (locked) openPaywall(reason, () => void action(...args));
      else void action(...args);
    };
  return { locked, gated };
}

/** «Remind everyone» — free a few times a month, unlimited with Pro. */
export const remindersLeft = (overview: ProOverview) => overview.reminders_left_this_month;
