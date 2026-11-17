import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const copy: Record<string, string> = {
  'homeScreen.helpTitle': 'Check your home screen',
  'homeScreen.helpText': 'Telegram did not confirm whether the shortcut was added.',
  'homeScreen.androidHelp': 'On Xiaomi and Redmi, allow Home screen shortcuts.',
  'homeScreen.iosHelp': 'Check your Home Screen and App Library.',
  'homeScreen.genericHelp': 'Check your device home screen.',
  'homeScreen.telegramHelp': 'Update Telegram and try its menu.',
  'homeScreen.retry': 'Try again',
  'homeScreen.helpDone': 'Got it',
};

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => copy[key] ?? key }),
}));

import HomeScreenShortcutHelp from './HomeScreenShortcutHelp';

describe('HomeScreenShortcutHelp', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('explains the Android permission fallback without claiming failure', () => {
    render(
      <HomeScreenShortcutHelp
        isOpen
        isPending={false}
        platform="android"
        onClose={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Check your home screen' })).toBeInTheDocument();
    expect(screen.getByText(/did not confirm whether/i)).toBeInTheDocument();
    expect(screen.getByText(/Xiaomi and Redmi/i)).toBeInTheDocument();
    expect(screen.queryByText(/App Library/i)).not.toBeInTheDocument();
  });

  it('retries and dismisses from explicit accessible buttons', async () => {
    const onRetry = vi.fn();
    const onClose = vi.fn();
    render(
      <HomeScreenShortcutHelp
        isOpen
        isPending={false}
        platform="ios"
        onClose={onClose}
        onRetry={onRetry}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await userEvent.click(screen.getByRole('button', { name: 'Got it' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/App Library/i)).toBeInTheDocument();
  });
});
