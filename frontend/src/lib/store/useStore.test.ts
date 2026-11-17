import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { User } from '@/types/api';

// Capture autosave calls without hitting the network.
const updateUserSettings = vi.fn();
vi.mock('@/lib/api/users', () => ({
  // Record the call for assertions; it answers like the real axios call.
  updateUserSettings: (...args: unknown[]) => updateUserSettings(...args) ?? Promise.resolve(),
}));

const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));

import { useStore } from './useStore';

const mkUser = (id: number): User => ({
  id,
  telegram_id: id,
  username: 'u',
  name: null,
  surname: null,
  avatar_url: null,
});

const reset = () =>
  useStore.setState({ theme: 'light', language: 'ru', currency: 'uzs', currentUser: null });

describe('useStore — settings persistence', () => {
  beforeEach(() => {
    updateUserSettings.mockReset();
    track.mockReset();
    reset();
  });

  it('applyServerSettings sets theme/language and does NOT autosave', () => {
    useStore.getState().applyServerSettings({ theme: 'dark', language: 'ru' });
    expect(useStore.getState().theme).toBe('dark');
    expect(useStore.getState().language).toBe('ru');
    expect(updateUserSettings).not.toHaveBeenCalled();
  });

  it('applyServerSettings ignores missing/invalid values', () => {
    useStore.getState().applyServerSettings(null);
    useStore.getState().applyServerSettings({});
    expect(useStore.getState().theme).toBe('light');
    expect(useStore.getState().language).toBe('ru');
  });

  it('selectTheme autosaves when a user is signed in', () => {
    useStore.setState({ currentUser: mkUser(7) });
    useStore.getState().selectTheme('dark');
    expect(useStore.getState().theme).toBe('dark');
    expect(updateUserSettings).toHaveBeenCalledWith(7, { theme: 'dark' });
  });

  it('counts a theme once the server has kept it', async () => {
    useStore.setState({ currentUser: mkUser(7) });
    useStore.getState().selectTheme('dark');

    await vi.waitFor(() => expect(track).toHaveBeenCalledWith('theme_changed', { theme: 'dark' }));
  });

  it('selectTheme goes back to the theme before when the server does not keep it', async () => {
    useStore.setState({ currentUser: mkUser(7) });
    updateUserSettings.mockReturnValueOnce(Promise.reject(new Error('402')));

    useStore.getState().selectTheme('dark');
    expect(useStore.getState().theme).toBe('dark');

    await vi.waitFor(() => expect(useStore.getState().theme).toBe('light'));
    expect(track).not.toHaveBeenCalledWith('theme_changed', expect.anything());
  });

  it('selectTheme does not autosave when signed out', () => {
    useStore.getState().selectTheme('dark');
    expect(useStore.getState().theme).toBe('dark');
    expect(updateUserSettings).not.toHaveBeenCalled();
  });

  it('setLanguage autosaves when a user is signed in', () => {
    useStore.setState({ currentUser: mkUser(7) });
    useStore.getState().setLanguage('uz');
    expect(updateUserSettings).toHaveBeenCalledWith(7, { language: 'uz' });
  });

  it('a profile without a currency resets what an older session persisted', () => {
    // Before the default moved to sums the store started from USD and kept it
    // in local storage; the settings menu then showed USD while the wizard,
    // reading the profile, showed UZS. The profile wins either way.
    useStore.setState({ currency: 'usd' });

    useStore.getState().applyServerSettings({ language: 'ru' });

    expect(useStore.getState().currency).toBe('uzs');
  });

  it('a profile with a currency puts it into the field', () => {
    useStore.getState().applyServerSettings({ currency: 'kzt' });

    expect(useStore.getState().currency).toBe('kzt');
  });
});

describe('useStore — onboarding', () => {
  beforeEach(() => {
    updateUserSettings.mockReset();
    track.mockReset();
    reset();
  });

  it('remembers once that onboarding is behind the person', () => {
    useStore.setState({ currentUser: { ...mkUser(4), settings: { language: 'uz' } } });

    useStore.getState().completeOnboarding();
    useStore.getState().completeOnboarding();

    expect(useStore.getState().currentUser?.settings).toEqual({ language: 'uz', onboarding_completed: true });
    expect(updateUserSettings).toHaveBeenCalledTimes(1);
    expect(updateUserSettings).toHaveBeenCalledWith(4, { onboarding_completed: true });
  });
});
