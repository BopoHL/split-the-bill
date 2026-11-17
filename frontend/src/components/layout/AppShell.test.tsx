import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const nav = vi.hoisted(() => {
  const push = vi.fn();
  return { pathname: '/', push, router: { push, replace: vi.fn() } };
});
const user = vi.hoisted(() => ({
  id: 5, telegram_id: 500, username: 'lea', name: 'Lea', surname: null, avatar_url: null,
  settings: { guest_tour_completed: true },
}));

vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useRouter: () => nav.router,
}));
vi.mock('next/dynamic', () => ({ default: () => () => null }));
vi.mock('@/lib/telegram/init', () => ({
  initTelegramSDK: () => ({ platform: 'ios' }),
  getTelegramUser: () => ({ id: 500, first_name: 'Lea', allows_write_to_pm: true }),
  getTelegramTheme: () => 'light',
  waitForTelegramWebApp: () => Promise.resolve(true),
  getStartParam: () => 'inv_CODE',
  isDevMockEnabled: () => false,
  requestWriteAccess: () => Promise.resolve(true),
}));
vi.mock('@/lib/api/users', () => ({
  getUserByTelegramId: vi.fn(),
  syncTelegramWriteAccess: vi.fn(),
}));
vi.mock('@/lib/api/invites', () => ({
  resolveInvite: () => Promise.resolve({
    code: 'CODE', bill_id: 1, public_token: 'tok', seat_participant_id: null, channel: 'link',
  }),
}));
vi.mock('@/lib/api/bills', () => ({
  claimSeat: vi.fn(),
  getSeatsByToken: vi.fn(),
  joinByToken: () => Promise.resolve({ bill_id: 1 }),
  joinWelcome: () => Promise.resolve(),
  updatePaymentStatus: vi.fn(),
}));
vi.mock('@/lib/analytics', () => ({
  initAnalytics: vi.fn(), identifyUser: vi.fn(), track: vi.fn(), setAnalyticsContext: vi.fn(),
  setPersonProperties: vi.fn(),
  AnalyticsEvent: { AppOpen: 'app_open', ParticipantJoined: 'joined' },
}));
vi.mock('@/lib/tour/arrival', () => ({ arriveAsGuest: vi.fn() }));
vi.mock('@/components/tour/TourOverlay', () => ({ default: () => null }));
vi.mock('@/components/pro/Paywall', () => ({ default: () => null }));
vi.mock('@/components/ui/OfflineGate', () => ({ default: () => null }));
vi.mock('@/components/ui/Toaster', () => ({ default: () => null }));
vi.mock('@/components/layout/SafeAreaProvider', () => ({ default: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('@/hooks/useHomeScreenShortcut', () => ({ HomeScreenShortcutProvider: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('@/lib/store/usePro', () => ({
  usePro: Object.assign(() => ({}), { getState: () => ({ load: vi.fn(), openPaywall: vi.fn() }) }),
  useProGate: () => ({ shown: 'light' }),
}));

import { getUserByTelegramId } from '@/lib/api/users';
import { useTour } from '@/lib/tour/useTour';
import AppShell from './AppShell';

/** What home would see the first time it is drawn. */
function Home({ seen }: { seen: boolean[] }) {
  seen.push(useTour.getState().arriving);
  return null;
}

describe('opening the app from an invite', () => {
  beforeEach(() => {
    nav.pathname = '/';
    nav.push.mockReset();
    useTour.getState().setArriving(false);
  });

  it('holds home’s welcome back from its first frame until the bill is up', async () => {
    vi.mocked(getUserByTelegramId).mockResolvedValue(user as never);
    const seen: boolean[] = [];
    const view = render(<AppShell><Home seen={seen} /></AppShell>);

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/bill/1'));
    // Home was never drawn without the flag, and still is not on the way out.
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every(Boolean)).toBe(true);
    expect(useTour.getState().arriving).toBe(true);

    nav.pathname = '/bill/1';
    act(() => view.rerender(<AppShell><Home seen={seen} /></AppShell>));
    expect(useTour.getState().arriving).toBe(false);
  });

  it('signs in with how it came in, for the server to keep as the first touch', async () => {
    vi.mocked(getUserByTelegramId).mockResolvedValue(user as never);
    render(<AppShell><Home seen={[]} /></AppShell>);

    await waitFor(() => expect(getUserByTelegramId).toHaveBeenCalled());
    expect(vi.mocked(getUserByTelegramId).mock.calls[0][6]).toEqual({ start: 'invite', source: null });
  });
});
