import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const store = vi.hoisted(() => ({
  theme: 'light' as string,
  selectTheme: vi.fn(),
  language: 'ru',
  setLanguage: vi.fn(),
}));
vi.mock('@/lib/store/useStore', () => ({ useStore: () => store }));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/hooks/useHomeScreenShortcut', () => ({
  useHomeScreenShortcut: () => ({ showInSettings: false, isPending: false, add: vi.fn() }),
}));
const telegram = vi.hoisted(() => ({ openTelegramLink: vi.fn() }));
const support = vi.hoisted(() => ({ username: null as string | null }));
vi.mock('@/hooks/useSupportUsername', () => ({ useSupportUsername: () => support.username }));
vi.mock('@/lib/telegram/init', () => telegram);
const navigation = vi.hoisted(() => ({ push: vi.fn(), pathname: '/' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigation.push }),
  usePathname: () => navigation.pathname,
}));
const tour = vi.hoisted(() => ({ start: vi.fn() }));
vi.mock('@/lib/tour/useTour', () => ({
  useTour: (selector: (state: typeof tour) => unknown) => selector(tour),
}));

import SettingsMenu from './SettingsMenu';

const openMenu = () => fireEvent.click(screen.getByRole('button', { name: 'settings.title' }));

beforeEach(() => {
  vi.clearAllMocks();
  store.theme = 'light';
  Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
});

describe('SettingsMenu', () => {
  it('leaves the look of the app and Pro to the header', () => {
    render(<SettingsMenu />);
    openMenu();

    expect(screen.queryByText('settings.theme')).toBeNull();
    expect(screen.queryByText('settings.badge')).toBeNull();
    expect(screen.queryByText('pro.title')).toBeNull();
  });

  it('leaves the currency to the bill it belongs to', () => {
    render(<SettingsMenu />);
    openMenu();

    expect(screen.queryByText('settings.currency')).toBeNull();
  });

  it('opens a chat with support in Telegram', () => {
    support.username = 'split_support';
    render(<SettingsMenu />);
    openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'settings.support' }));

    expect(telegram.openTelegramLink).toHaveBeenCalledWith('https://t.me/split_support');
  });

  it('replays the guided tour from the home screen', () => {
    navigation.pathname = '/bill/7';
    render(<SettingsMenu />);
    openMenu();

    fireEvent.click(screen.getByRole('button', { name: 'settings.tutorial' }));

    expect(tour.start).toHaveBeenCalledWith('settings');
    expect(navigation.push).toHaveBeenCalledWith('/');
  });

  it('offers no support item when nobody is set to answer', () => {
    support.username = null;
    render(<SettingsMenu />);
    openMenu();

    expect(screen.queryByRole('button', { name: 'settings.support' })).toBeNull();
  });
});
