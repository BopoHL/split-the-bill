import { create } from 'zustand';

/**
 * A bill just made in the app, whose owner is asked to invite the table as the
 * bill first opens. A bill lives on its invite: owners who invited nobody
 * seldom came back to it. Asked once: a bill opened again does not ask again,
 * answered or not.
 */
interface InvitePromptState {
  billId: number | null;
  offer: (billId: number) => void;
  /** Takes the offer for this bill: true only for the first to take it. */
  claim: (billId: number) => boolean;
}

export const useInvitePrompt = create<InvitePromptState>()((set, get) => ({
  billId: null,
  offer: (billId) => set({ billId }),
  claim: (billId) => {
    if (get().billId !== billId) return false;
    set({ billId: null });
    return true;
  },
}));
