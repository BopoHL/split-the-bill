import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => navigation }));
const api = vi.hoisted(() => ({ createDemoBill: vi.fn(), eraseDemoBill: vi.fn(() => Promise.resolve()) }));
vi.mock('@/lib/api/demoBills', () => api);
vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: {} }));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ language: 'uz', t: (key: string) => key }),
}));

import { TOUR_STEPS } from '@/lib/tour/script';
import { useTour } from '@/lib/tour/useTour';
import DemoScanScene from './DemoScanScene';

const scanning = TOUR_STEPS.findIndex((step) => step.id === 'scanning');

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  useTour.getState().start('first_run');
  useTour.setState({ stepIndex: scanning });
});

afterEach(() => {
  vi.useRealTimers();
  useTour.getState().stop();
});

describe('DemoScanScene', () => {
  it('opens the demo bill once the show is over, not before', async () => {
    api.createDemoBill.mockResolvedValue({ id: 42 });
    render(<DemoScanScene onSkip={vi.fn()} />);

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(api.createDemoBill).toHaveBeenCalledWith('uz', undefined);
    expect(navigation.push).not.toHaveBeenCalled();

    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(navigation.push).toHaveBeenCalledWith('/bill/42');
    expect(useTour.getState()).toMatchObject({ demoBillId: 42, stepIndex: scanning + 1 });
  });

  it('carries the card the tour typed in over to the demo bill', async () => {
    api.createDemoBill.mockResolvedValue({ id: 8 });
    useTour.getState().stageCard();
    render(<DemoScanScene onSkip={vi.fn()} />);

    await act(() => vi.advanceTimersByTimeAsync(4000));

    expect(api.createDemoBill).toHaveBeenCalledWith('uz', '8600 1234 5678 9010');
  });

  it('erases a bill that arrives after the tour was left', async () => {
    api.createDemoBill.mockResolvedValue({ id: 7 });
    const { unmount } = render(<DemoScanScene onSkip={vi.fn()} />);

    useTour.getState().stop();
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(4000));

    expect(api.eraseDemoBill).toHaveBeenCalledWith(7);
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it('offers another go or a way out when the example fails', async () => {
    const onSkip = vi.fn();
    api.createDemoBill.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ id: 3 });
    render(<DemoScanScene onSkip={onSkip} />);

    await act(() => vi.advanceTimersByTimeAsync(4000));
    fireEvent.click(screen.getByRole('button', { name: 'tour.skip' }));
    expect(onSkip).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole('button', { name: 'receipt.tryAgain' }));
    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(navigation.push).toHaveBeenCalledWith('/bill/3');
  });
});

describe('DemoScanScene under StrictMode', () => {
  it('asks for one demo bill however often its effect runs', async () => {
    const { StrictMode } = await import('react');
    api.createDemoBill.mockResolvedValue({ id: 5 });
    render(<StrictMode><DemoScanScene onSkip={vi.fn()} /></StrictMode>);

    await act(() => vi.advanceTimersByTimeAsync(4000));

    expect(api.createDemoBill).toHaveBeenCalledTimes(1);
    expect(api.eraseDemoBill).not.toHaveBeenCalled();
    expect(navigation.push).toHaveBeenCalledTimes(1);
    expect(navigation.push).toHaveBeenCalledWith('/bill/5');
  });
});
