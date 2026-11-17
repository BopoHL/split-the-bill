import { act, renderHook, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { HomeScreenStatus } from '@/types/telegram';

const canAddToHomeScreen = vi.fn();
const checkHomeScreenStatus = vi.fn();
const addToHomeScreen = vi.fn();
const offHomeScreenAdded = vi.fn();
const onHomeScreenAdded = vi.fn();
const hapticFeedback = vi.fn();
const telegramOnEvent = vi.fn();
const telegramOffEvent = vi.fn();

vi.mock('@/lib/telegram/init', () => ({
  canAddToHomeScreen: () => canAddToHomeScreen(),
  checkHomeScreenStatus: (cb: (status: HomeScreenStatus) => void) =>
    checkHomeScreenStatus(cb),
  addToHomeScreen: () => addToHomeScreen(),
  getTelegramWebApp: () => ({
    platform: 'android',
    onEvent: telegramOnEvent,
    offEvent: telegramOffEvent,
  }),
  onHomeScreenAdded: (cb: () => void) => onHomeScreenAdded(cb),
  hapticFeedback: (...args: unknown[]) => hapticFeedback(...args),
}));

const storageGet = vi.fn();
const storageSet = vi.fn();
vi.mock('@/lib/telegram/deviceStorage', () => ({
  storageGet: (key: string) => storageGet(key),
  storageSet: (key: string, value: string) => storageSet(key, value),
}));

import {
  HomeScreenShortcutProvider,
  useHomeScreenShortcut,
} from './useHomeScreenShortcut';

const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(HomeScreenShortcutProvider, null, children);

const renderShortcut = () =>
  renderHook(() => useHomeScreenShortcut(), { wrapper });

const withStatus = (status: HomeScreenStatus) =>
  checkHomeScreenStatus.mockImplementation(
    (cb: (next: HomeScreenStatus) => void) => {
      cb(status);
      return true;
    },
  );

describe('useHomeScreenShortcut', () => {
  beforeEach(() => {
    canAddToHomeScreen.mockReset().mockReturnValue(true);
    checkHomeScreenStatus.mockReset();
    addToHomeScreen.mockReset().mockReturnValue(true);
    offHomeScreenAdded.mockReset();
    onHomeScreenAdded
      .mockReset()
      .mockImplementation(() => offHomeScreenAdded);
    hapticFeedback.mockReset();
    telegramOnEvent.mockReset();
    telegramOffEvent.mockReset();
    storageGet.mockReset().mockResolvedValue(null);
    storageSet.mockReset().mockResolvedValue(undefined);
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stays hidden when the client does not support shortcuts', () => {
    canAddToHomeScreen.mockReturnValue(false);
    const { result } = renderShortcut();

    expect(result.current.status).toBeNull();
    expect(result.current.showBanner).toBe(false);
    expect(result.current.showInSettings).toBe(false);
  });

  it('shows a missed shortcut after the dismissal flag has loaded', async () => {
    withStatus('missed');
    const { result } = renderShortcut();

    await waitFor(() => expect(result.current.showBanner).toBe(true));
    expect(result.current.showInSettings).toBe(true);
    expect(result.current.platform).toBe('android');
  });

  it('does not flash the banner before the dismissal flag resolves', async () => {
    withStatus('missed');
    let resolveGet: (value: string | null) => void = () => {};
    storageGet.mockReturnValue(
      new Promise<string | null>((resolve) => {
        resolveGet = resolve;
      }),
    );
    const { result } = renderShortcut();

    expect(result.current.showBanner).toBe(false);
    await act(async () => resolveGet(null));
    expect(result.current.showBanner).toBe(true);
  });

  it('keeps an unknown status actionable without showing the banner', async () => {
    withStatus('unknown');
    const { result } = renderShortcut();

    await waitFor(() => expect(result.current.showInSettings).toBe(true));
    expect(result.current.showBanner).toBe(false);
  });

  it('falls back to unknown when a supported client never returns status', async () => {
    vi.useFakeTimers();
    checkHomeScreenStatus.mockReturnValue(true);
    const { result } = renderShortcut();

    await act(async () => {});
    expect(result.current.showInSettings).toBe(false);
    await act(() => vi.advanceTimersByTime(1200));

    expect(result.current.status).toBe('unknown');
    expect(result.current.showInSettings).toBe(true);
  });

  it('also recovers when the status method is absent or throws synchronously', async () => {
    vi.useFakeTimers();
    checkHomeScreenStatus.mockReturnValue(false);
    const { result } = renderShortcut();

    await act(async () => {});
    await act(() => vi.advanceTimersByTime(1200));

    expect(result.current.status).toBe('unknown');
    expect(result.current.showInSettings).toBe(true);
  });

  it('shows recovery help when Telegram rejects the native invocation', async () => {
    withStatus('missed');
    addToHomeScreen.mockReturnValue(false);
    const { result } = renderShortcut();
    await waitFor(() => expect(result.current.showBanner).toBe(true));

    act(() => result.current.add());

    expect(addToHomeScreen).toHaveBeenCalledTimes(1);
    expect(hapticFeedback).toHaveBeenCalledWith('light');
    expect(result.current.isAdded).toBe(false);
    expect(result.current.showHelp).toBe(true);
    expect(result.current.showBanner).toBe(false);
  });

  it('prevents duplicate native calls while pending and permits a retry afterward', async () => {
    vi.useFakeTimers();
    withStatus('missed');
    const { result } = renderShortcut();
    await act(async () => {});

    act(() => {
      result.current.add();
      result.current.add();
    });
    expect(addToHomeScreen).toHaveBeenCalledTimes(1);
    expect(result.current.isPending).toBe(true);

    await act(() => vi.advanceTimersByTime(700));
    expect(result.current.showHelp).toBe(true);

    act(() => result.current.retry());
    expect(addToHomeScreen).toHaveBeenCalledTimes(2);
  });

  it('shares one request and one help dialog between two consumers', async () => {
    withStatus('missed');
    addToHomeScreen.mockReturnValue(false);
    const { result } = renderHook(
      () => ({
        banner: useHomeScreenShortcut(),
        settings: useHomeScreenShortcut(),
      }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.banner.showBanner).toBe(true));

    act(() => {
      result.current.banner.add();
      result.current.settings.add();
    });

    expect(addToHomeScreen).toHaveBeenCalledTimes(1);
    expect(result.current.banner).toBe(result.current.settings);
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  it('accepts a late added event and ignores an older missed callback', async () => {
    let initialStatus: ((status: HomeScreenStatus) => void) | undefined;
    let added: (() => void) | undefined;
    checkHomeScreenStatus.mockImplementation((cb) => {
      initialStatus = cb;
      return true;
    });
    onHomeScreenAdded.mockImplementation((cb) => {
      added = cb;
      return offHomeScreenAdded;
    });
    const { result } = renderShortcut();

    act(() => initialStatus?.('missed'));
    await waitFor(() => expect(result.current.showBanner).toBe(true));
    act(() => result.current.add());
    act(() => added?.());
    act(() => initialStatus?.('missed'));

    expect(result.current.status).toBe('added');
    expect(result.current.isAdded).toBe(true);
    expect(result.current.showHelp).toBe(false);
    expect(result.current.showInSettings).toBe(false);
  });

  it('rechecks a confirmed shortcut after activation so removal is detected', async () => {
    withStatus('added');
    const { result } = renderShortcut();
    await waitFor(() => expect(result.current.isAdded).toBe(true));

    withStatus('missed');
    const activated = telegramOnEvent.mock.calls.find(
      ([event]) => event === 'activated',
    )?.[1] as (() => void) | undefined;
    act(() => activated?.());

    expect(result.current.status).toBe('missed');
    expect(result.current.isAdded).toBe(false);
    expect(result.current.showInSettings).toBe(true);
  });

  it('does not schedule a recheck when confirmation fires during invocation', async () => {
    vi.useFakeTimers();
    let added: (() => void) | undefined;
    withStatus('missed');
    onHomeScreenAdded.mockImplementation((cb) => {
      added = cb;
      return offHomeScreenAdded;
    });
    addToHomeScreen.mockImplementation(() => {
      added?.();
      return true;
    });
    const { result } = renderShortcut();
    await act(async () => {});

    act(() => result.current.add());
    await act(() => vi.advanceTimersByTime(3000));

    expect(result.current.isAdded).toBe(true);
    expect(checkHomeScreenStatus).toHaveBeenCalledTimes(1);
  });

  it('rechecks on return to the app and confirms the shortcut', async () => {
    vi.useFakeTimers();
    withStatus('missed');
    const { result } = renderShortcut();
    await act(async () => {});
    act(() => result.current.add());

    withStatus('added');
    const activated = telegramOnEvent.mock.calls.find(
      ([event]) => event === 'activated',
    )?.[1] as (() => void) | undefined;
    act(() => activated?.());

    expect(result.current.isAdded).toBe(true);
    await act(() => vi.advanceTimersByTime(3000));
    expect(checkHomeScreenStatus).toHaveBeenCalledTimes(2);
  });

  it('removes event listeners and ignores callbacks after unmount', () => {
    let statusCallback: ((status: HomeScreenStatus) => void) | undefined;
    checkHomeScreenStatus.mockImplementation((cb) => {
      statusCallback = cb;
      return true;
    });
    const { unmount } = renderShortcut();
    const activated = telegramOnEvent.mock.calls.find(
      ([event]) => event === 'activated',
    )?.[1];

    unmount();
    statusCallback?.('added');

    expect(offHomeScreenAdded).toHaveBeenCalledTimes(1);
    expect(telegramOffEvent).toHaveBeenCalledWith('activated', activated);
  });

  it('persists a banner dismissal while keeping Settings actionable', async () => {
    withStatus('missed');
    const { result } = renderShortcut();
    await waitFor(() => expect(result.current.showBanner).toBe(true));

    act(() => result.current.dismiss());

    expect(storageSet).toHaveBeenCalledWith('home_screen_prompt_dismissed', 'true');
    expect(result.current.showBanner).toBe(false);
    expect(result.current.showInSettings).toBe(true);
  });
});
