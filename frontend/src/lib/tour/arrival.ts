import type { Language } from '@/lib/i18n/translations';
import { useStore } from '@/lib/store/useStore';
import { getTelegramUser } from '@/lib/telegram/init';
import { useTour } from './useTour';

const LANGUAGES: readonly Language[] = ['en', 'ru', 'uz'];

/** The app's language for Telegram's `language_code`, when it speaks it. */
export function languageOfTelegram(code: string | undefined): Language | null {
  const short = code?.split('-')[0]?.toLowerCase();
  return LANGUAGES.find((language) => language === short) ?? null;
}

/**
 * Someone has just taken a seat on another person's bill. Nobody asks them
 * for a language — if they never chose one, the app takes their Telegram's —
 * and the bill is shown to them once.
 */
export function arriveAsGuest(billId: number) {
  const { currentUser, setLanguage } = useStore.getState();
  if (!currentUser) return;
  if (!currentUser.settings?.language) {
    const language = languageOfTelegram(getTelegramUser()?.language_code);
    if (language) setLanguage(language);
  }
  // Someone who already knows the app — they went through the host's tour —
  // needs no walk round a bill.
  const { guest_tour_completed, onboarding_completed } = currentUser.settings ?? {};
  if (!guest_tour_completed && !onboarding_completed) useTour.getState().offerGuestTour(billId);
}
