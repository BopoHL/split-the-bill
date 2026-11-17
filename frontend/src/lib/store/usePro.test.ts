import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import type { ProOverview } from '@/types/pro';
import { usePro, useProGate } from './usePro';

const analytics = vi.hoisted(() => ({ track: vi.fn(), setPersonProperties: vi.fn() }));
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  ...analytics,
}));

const overview = (active: boolean, scansLeft: number | null): ProOverview => ({
  active,
  until: null,
  trial: false,
  subscription: false,
  plans: [],
  free_scans_per_day: 3,
  scans_left_today: scansLeft,
  free_reminders_per_month: 3,
  reminders_left_this_month: scansLeft === null ? null : 3,
});

describe('usePro', () => {
  beforeEach(() => {
    usePro.setState({ overview: null, paywall: null });
    analytics.track.mockReset();
    analytics.setPersonProperties.mockReset();
  });

  it('counts the paywall opening once for what it is opened over', () => {
    usePro.getState().openPaywall('themes');
    usePro.getState().openPaywall('themes');
    usePro.setState({ overview: overview(false, 0) });
    usePro.getState().allowScan();

    expect(analytics.track.mock.calls).toEqual([
      ['paywall_opened', { reason: 'themes' }],
      ['paywall_opened', { reason: 'scans' }],
    ]);
  });

  it('keeps the person\'s Pro on their analytics profile', () => {
    usePro.getState().set({ ...overview(true, null), subscription: true });

    expect(analytics.setPersonProperties).toHaveBeenCalledWith({ pro: true, pro_trial: false, pro_subscription: true });
  });

  it('lets a gated action through with Pro and opens the paywall without it', () => {
    let ran = 0;
    usePro.setState({ overview: overview(true, null) });
    const withPro = renderHook(() => useProGate('reminders'));
    act(() => withPro.result.current.gated(() => { ran += 1; })());
    expect(ran).toBe(1);
    expect(usePro.getState().paywall).toBeNull();

    usePro.setState({ overview: overview(false, 3) });
    const without = renderHook(() => useProGate('reminders'));
    expect(without.result.current.locked).toBe(true);
    act(() => without.result.current.gated(() => { ran += 1; })());
    expect(ran).toBe(1);
    expect(usePro.getState().paywall).toBe('reminders');
  });

  it('keeps what a gated action was about to do, to carry on with after the purchase', () => {
    let ran = 0;
    usePro.setState({ overview: overview(false, 3) });
    const gate = renderHook(() => useProGate('reminders'));

    act(() => gate.result.current.gated((times: number) => { ran += times; })(2));
    expect(ran).toBe(0);
    usePro.getState().resume?.();
    expect(ran).toBe(2);

    usePro.getState().closePaywall();
    expect(usePro.getState().resume).toBeNull();
  });

  it('locks nothing before the status is known', () => {
    const gate = renderHook(() => useProGate('reminders'));

    expect(gate.result.current.locked).toBe(false);
  });

  it('stops a scan only once the free ones are spent', () => {
    expect(usePro.getState().allowScan()).toBe(true);

    usePro.setState({ overview: overview(false, 1) });
    expect(usePro.getState().allowScan()).toBe(true);

    usePro.setState({ overview: overview(false, 0) });
    expect(usePro.getState().allowScan()).toBe(false);
    expect(usePro.getState().paywall).toBe('scans');
  });
});
