import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => '/' }));
const api = vi.hoisted(() => ({ eraseDemoBill: vi.fn(() => Promise.resolve()) }));
vi.mock('@/lib/api/demoBills', () => api);
const analytics = vi.hoisted(() => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: { TourCompleted: 'tour_completed' } }));
vi.mock('@/lib/analytics', () => analytics);
const store = vi.hoisted(() => ({ completeOnboarding: vi.fn(), completeGuestTour: vi.fn() }));
vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector: (state: typeof store) => unknown) => selector(store),
}));
vi.mock('@/lib/i18n/useTranslation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import { useTour } from '@/lib/tour/useTour';
import TourFinale from './TourFinale';

describe('TourFinale', () => {
  it('settles the tour as soon as it shows, then lets the person go', () => {
    useTour.setState({ active: true, demoBillId: 42 });
    render(<TourFinale />);

    expect(api.eraseDemoBill).toHaveBeenCalledWith(42);
    expect(store.completeOnboarding).toHaveBeenCalledOnce();
    expect(analytics.track).toHaveBeenCalledWith('tour_completed', { tour: 'host' });
    expect(useTour.getState().demoBillId).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'tour.finale.button' }));
    expect(useTour.getState().active).toBe(false);
  });
});
