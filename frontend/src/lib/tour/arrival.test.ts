import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@/types/api';

const store = vi.hoisted(() => ({ currentUser: null as User | null, setLanguage: vi.fn() }));
vi.mock('@/lib/store/useStore', () => ({ useStore: { getState: () => store } }));
const telegram = vi.hoisted(() => ({ getTelegramUser: vi.fn() }));
vi.mock('@/lib/telegram/init', () => telegram);
vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: {} }));

import { arriveAsGuest, languageOfTelegram } from './arrival';
import { useTour } from './useTour';

const user = (settings: User['settings']): User => ({ id: 1, telegram_id: 7, username: 'lea', settings } as User);

beforeEach(() => {
  vi.clearAllMocks();
  useTour.setState({ guestBillId: null });
  telegram.getTelegramUser.mockReturnValue({ id: 7, first_name: 'Lea', language_code: 'uz' });
});

describe('languageOfTelegram', () => {
  it('reads a language the app speaks, region and all', () => {
    expect(languageOfTelegram('en-GB')).toBe('en');
    expect(languageOfTelegram('UZ')).toBe('uz');
  });

  it('has nothing for a language the app does not speak', () => {
    expect(languageOfTelegram('de')).toBeNull();
    expect(languageOfTelegram(undefined)).toBeNull();
  });
});

describe('arriveAsGuest', () => {
  it('speaks the guest’s Telegram language and offers them the tour of that bill', () => {
    store.currentUser = user({});

    arriveAsGuest(42);

    expect(store.setLanguage).toHaveBeenCalledWith('uz');
    expect(useTour.getState().guestBillId).toBe(42);
  });

  it('keeps a language they chose themselves', () => {
    store.currentUser = user({ language: 'ru' });

    arriveAsGuest(42);

    expect(store.setLanguage).not.toHaveBeenCalled();
  });

  it('offers the tour only once in a lifetime', () => {
    store.currentUser = user({ language: 'ru', guest_tour_completed: true });

    arriveAsGuest(42);

    expect(useTour.getState().guestBillId).toBeNull();
  });

  it('spares someone who already knows the app', () => {
    store.currentUser = user({ language: 'ru', onboarding_completed: true });

    arriveAsGuest(42);

    expect(useTour.getState().guestBillId).toBeNull();
  });

  it('takes the offer up once, on that bill only', () => {
    store.currentUser = user({});
    arriveAsGuest(42);

    expect(useTour.getState().takeGuestOffer(7)).toBe(false);
    expect(useTour.getState().takeGuestOffer(42)).toBe(true);
    expect(useTour.getState().takeGuestOffer(42)).toBe(false);
  });
});
