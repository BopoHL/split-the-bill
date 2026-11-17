import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const store = vi.hoisted(() => ({
  theme: 'dark' as string,
  selectTheme: vi.fn(),
  language: 'ru',
  currentUser: { id: 7, username: 'leo', avatar_url: null, settings: { badge: 'night_owl' } },
  setCurrentUser: vi.fn(),
}));
vi.mock('@/lib/store/useStore', () => ({ useStore: () => store }));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/lib/api/badges', () => ({ getBadges: vi.fn(() => new Promise(() => {})), chooseBadge: vi.fn() }));

import ProfileChip from './ProfileChip';

const chip = () => screen.getByRole('button', { name: 'settings.appearance' });

beforeEach(() => {
  Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
});

describe('ProfileChip', () => {
  it('is the person’s picture beside the theme they use — no name, no badge', () => {
    render(<ProfileChip />);

    expect(chip()).not.toHaveTextContent('leo');
    expect(chip()).not.toHaveTextContent('analytics.badge.night_owl.title');
    expect(chip().querySelector('[data-theme="dark"]')).not.toBeNull();
  });

  it('opens the theme and the badge, each showing what is chosen', () => {
    render(<ProfileChip />);
    fireEvent.click(chip());

    fireEvent.click(screen.getByRole('button', { name: 'settings.themes.dark' }));

    expect(screen.getAllByRole('radio')).toHaveLength(6);
    expect(screen.getByRole('radio', { name: /settings.themes.dark/ })).toHaveAttribute('aria-checked', 'true');
  });

  it('opens the badges from the same menu', () => {
    render(<ProfileChip />);
    fireEvent.click(chip());

    fireEvent.click(screen.getByRole('button', { name: 'analytics.badge.night_owl.title' }));

    expect(screen.getByText('settings.badgeHint')).toBeInTheDocument();
  });
});
