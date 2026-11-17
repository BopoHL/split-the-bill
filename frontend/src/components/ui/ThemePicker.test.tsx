import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProOverview } from '@/types/pro';
import { usePro } from '@/lib/store/usePro';

const store = vi.hoisted(() => ({ theme: 'light' as string, selectTheme: vi.fn(), language: 'ru' }));
vi.mock('@/lib/store/useStore', () => ({ useStore: () => store }));

import ThemePicker from './ThemePicker';

const status = (active: boolean): ProOverview => ({
  active, until: null, trial: false, subscription: false, plans: [], free_scans_per_day: 3, scans_left_today: null, free_reminders_per_month: 3, reminders_left_this_month: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  store.theme = 'light';
  usePro.setState({ overview: null, paywall: null });
  Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
});

describe('ThemePicker', () => {
  const chip = (name: string) => screen.getByRole('radio', { name: new RegExp(`^${name}(?! Frost)`) });
  const preview = () => screen.getByTestId('theme-preview');

  it('shows a theme tried on as a bill and as a chat post, in its own colours', () => {
    render(<ThemePicker isOpen onClose={vi.fn()} />);
    expect(preview()).toHaveAttribute('data-previewed', 'light');

    fireEvent.click(chip('Nord'));
    expect(preview()).toHaveAttribute('data-previewed', 'nord');
    expect(preview().querySelector('[data-theme="nord"]')).not.toBeNull();
    expect(within(preview()).getAllByText('Ужин с друзьями').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('tab', { name: 'В чате' }));
    expect(within(preview()).getAllByText('Открыть счёт').length).toBeGreaterThan(0);
    expect(preview().querySelector('[data-theme="nord"]')).not.toBeNull();
  });

  it('lets a Pro theme be tried on without Pro, and taking it opens the paywall', () => {
    usePro.setState({ overview: status(false) });
    const onClose = vi.fn();
    render(<ThemePicker isOpen onClose={onClose} />);

    fireEvent.click(chip('Сакура'));
    expect(within(chip('Сакура')).getByText('Pro')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть с Pro' }));
    expect(usePro.getState().paywall).toBe('themes');
    expect(store.selectTheme).not.toHaveBeenCalled();

    fireEvent.click(chip('Тёмная'));
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать тему' }));
    expect(store.selectTheme).toHaveBeenCalledWith('dark');
    expect(onClose).toHaveBeenCalled();
  });

  it('with Pro takes any theme, and says which one is in use', () => {
    usePro.setState({ overview: status(true) });
    store.theme = 'nord';
    render(<ThemePicker isOpen onClose={vi.fn()} />);

    expect(chip('Nord')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: 'Эта тема выбрана' })).toBeDisabled();
    fireEvent.click(chip('Полночь'));
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать тему' }));

    expect(store.selectTheme).toHaveBeenCalledWith('midnight');
    expect(within(screen.getByRole('radiogroup')).queryByText('Pro')).toBeNull();
  });

  it('starts on the free theme in use when the chosen one waits for Pro', () => {
    usePro.setState({ overview: status(false) });
    store.theme = 'nord_frost';
    render(<ThemePicker isOpen onClose={vi.fn()} />);

    expect(chip('Светлая')).toHaveAttribute('aria-checked', 'true');
    expect(preview()).toHaveAttribute('data-previewed', 'light');
  });
});
