import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { UserDetail } from '@/lib/api';
import UserSettingsForm from './UserSettingsForm';

vi.mock('@/lib/api', () => ({ api: { saveUserSettings: vi.fn() } }));

const { api } = await import('@/lib/api');

const user = (settings: Record<string, unknown>): UserDetail => ({
  id: 7,
  telegram_id: 77,
  username: 'lea',
  name: 'Лея',
  surname: null,
  avatar_url: null,
  language: (settings.language as string) ?? null,
  currency: null,
  onboarding_completed: settings.onboarding_completed === true,
  bot_blocked: false,
  bills_count: 0,
  participant_bills_count: 0,
  created_at: '2026-09-26T10:00:00',
  settings,
  owned_bills: [],
  participant_bills: [],
});

describe('user settings form', () => {
  it('sends only what changed, and a cleared field as null', async () => {
    const saved = user({ language: 'uz' });
    vi.mocked(api.saveUserSettings).mockResolvedValue(saved);
    const onSaved = vi.fn();
    render(<UserSettingsForm user={user({ language: 'ru', theme: 'dark', onboarding_completed: true })} onSaved={onSaved} />);

    const [language, theme] = screen.getAllByRole('combobox');
    fireEvent.change(language, { target: { value: 'uz' } });
    fireEvent.change(theme, { target: { value: '' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /Онбординг пройден/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(api.saveUserSettings).toHaveBeenCalledWith(7, { language: 'uz', theme: null, onboarding_completed: false });
  });

  it('marks one of the team as internal', async () => {
    vi.mocked(api.saveUserSettings).mockResolvedValue(user({ internal: true }));
    render(<UserSettingsForm user={user({})} onSaved={vi.fn()} />);

    fireEvent.click(screen.getByRole('checkbox', { name: /Свой аккаунт/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(api.saveUserSettings).toHaveBeenCalledWith(7, { internal: true }));
  });

  it('has nothing to save until something changes', () => {
    render(<UserSettingsForm user={user({ language: 'ru' })} onSaved={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
  });
});
