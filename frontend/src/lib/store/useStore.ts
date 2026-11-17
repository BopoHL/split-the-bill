import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, UserSettings } from '@/types/api';
import { updateUserSettings } from '@/lib/api/users';
import { type Currency, DEFAULT_CURRENCY, isCurrency } from '@/lib/utils/currencyCatalog';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { isTheme, type Theme } from '@/lib/utils/themes';

export type ToastVariant = 'error' | 'success' | 'info';

export interface ToastState {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface AppState {
  // User state
  currentUser: User | null;
  setCurrentUser: (user: User | null) => void;
  /** First-run onboarding is behind them. True once the server has it. */
  completeOnboarding: () => Promise<boolean>;
  /** The tour of a bill they joined is behind them — finished or skipped. */
  completeGuestTour: () => Promise<boolean>;

  // Transient toast (styled in-app replacement for alert())
  toast: ToastState | null;
  showToast: (message: string, variant?: ToastVariant) => void;
  dismissToast: () => void;
  
  // Theme state
  /** The theme chosen — the one shown may differ while Pro is locked. */
  theme: Theme;
  setTheme: (theme: Theme) => void;
  /** The viewer's own choice: applied and saved to their profile. */
  selectTheme: (theme: Theme) => void;
  
  // Language state
  language: 'en' | 'ru' | 'uz';
  setLanguage: (language: 'en' | 'ru' | 'uz') => void;

  // Currency state
  currency: Currency;

  // Apply theme/language/currency fetched from the server (no autosave echo)
  applyServerSettings: (settings?: UserSettings | null) => void;
}

type TourFlag = 'onboarding_completed' | 'guest_tour_completed';

/** A tour behind them, finished or skipped: on the profile at once, so it is
 *  not offered again while the request is still on its way. True once the
 *  server has it; false when it was there already or did not get there. */
async function settleTour(get: () => AppState, set: (state: Partial<AppState>) => void, flag: TourFlag): Promise<boolean> {
  const { currentUser } = get();
  if (!currentUser || currentUser.settings?.[flag]) return false;
  set({
    currentUser: {
      ...currentUser,
      settings: { ...(currentUser.settings || {}), [flag]: true },
    },
  });
  return updateUserSettings(currentUser.id, { [flag]: true }).then(() => true, () => false);
}

export const useStore = create<AppState>()(
  persist(
    (set, get) => ({
      // User state
      currentUser: null,
      setCurrentUser: (user) => set({ currentUser: user }),
      completeOnboarding: () => settleTour(get, set, 'onboarding_completed'),
      completeGuestTour: () => settleTour(get, set, 'guest_tour_completed'),

      // Toast
      toast: null,
      showToast: (message, variant = 'error') =>
        set({ toast: { id: Date.now(), message, variant } }),
      dismissToast: () => set({ toast: null }),

      // Theme state
      theme: 'light',
      setTheme: (theme) => set({ theme }),
      selectTheme: (theme) => {
        const previous = get().theme;
        set({ theme });
        const { currentUser } = get();
        if (!currentUser) return;
        void updateUserSettings(currentUser.id, { theme }).then(
          () => track(AnalyticsEvent.ThemeChanged, { theme }),
          () => {
            // Not kept — a Pro theme after Pro ended, say: back to the one that is.
            if (get().theme === theme) set({ theme: previous });
          },
        );
      },

      // Language state
      language: 'ru',
      setLanguage: (language) => {
        set({ language });
        track(AnalyticsEvent.LanguageChanged, { language });
        const { currentUser } = get();
        if (currentUser) {
          void updateUserSettings(currentUser.id, { language }).catch(() => {});
        }
      },

      // Currency state — the profile's default, read where no bill is in
      // play; a bill's currency is chosen when it is created and kept on it.
      currency: DEFAULT_CURRENCY,

      // Apply preferences fetched from the server; never echoes back.
      applyServerSettings: (settings) => {
        if (!settings) return;
        const patch: {
          theme?: Theme;
          language?: 'en' | 'ru' | 'uz';
          currency?: Currency;
        } = {};
        if (isTheme(settings.theme)) {
          patch.theme = settings.theme;
        }
        if (
          settings.language === 'en' ||
          settings.language === 'ru' ||
          settings.language === 'uz'
        ) {
          patch.language = settings.language;
        }
        // The profile is the source of truth for the currency: a choice made
        // in settings is written there, so a profile without one means nothing
        // was chosen — and the default replaces whatever an older session had
        // persisted locally (it used to start from USD).
        patch.currency = isCurrency(settings.currency) ? settings.currency : DEFAULT_CURRENCY;
        set(patch);
      },
    }),
    {
      name: 'split-the-bill-storage',
      partialize: (state) => ({
        theme: state.theme,
        language: state.language,
        currency: state.currency,
        currentUser: state.currentUser,
      }),
    }
  )
);
