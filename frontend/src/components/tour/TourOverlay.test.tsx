import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), pathname: '/' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigation.push, replace: navigation.replace }),
  usePathname: () => navigation.pathname,
}));
const api = vi.hoisted(() => ({
  createDemoBill: vi.fn(),
  seatDemoFriends: vi.fn(),
  eraseDemoBill: vi.fn(() => Promise.resolve()),
}));
vi.mock('@/lib/api/demoBills', () => api);
const telegram = vi.hoisted(() => ({ release: vi.fn(), holdBackButton: vi.fn() }));
vi.mock('@/lib/telegram/init', () => ({ holdBackButton: telegram.holdBackButton }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/toast', () => toast);
vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: {} }));
const store = vi.hoisted(() => ({ completeOnboarding: vi.fn(), completeGuestTour: vi.fn() }));
vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector: (state: typeof store) => unknown) => selector(store),
}));
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    language: 'en',
    t: (key: string, params?: Record<string, string>) => (params?.first ? `${key}(${params.first})` : key),
  }),
}));

import { TOUR_STEPS, type Tour, type TourStepId } from '@/lib/tour/script';
import { useTour } from '@/lib/tour/useTour';
import TourOverlay from './TourOverlay';

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
    unobserve() {}
  } as unknown as typeof ResizeObserver;
  // Anything the tour points at is on screen; everything else is not laid out.
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    return (this.dataset.tour
      ? { top: 120, left: 40, width: 120, height: 44 }
      : { top: 0, left: 0, width: 0, height: 0 }) as DOMRect;
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  telegram.holdBackButton.mockReturnValue(telegram.release);
  navigation.pathname = '/';
});

afterEach(() => act(() => useTour.getState().stop()));

const goTo = (id: TourStepId, extra: Partial<ReturnType<typeof useTour.getState>> = {}) =>
  act(() => {
    useTour.getState().start('first_run');
    useTour.setState({ stepIndex: TOUR_STEPS.findIndex((step) => step.id === id), ...extra });
  });

describe('TourOverlay', () => {
  it('lights the create button and follows a real press on it', async () => {
    const create = vi.fn();
    render(
      <>
        <button data-tour="create-bill" onClick={create}>+</button>
        <TourOverlay />
      </>,
    );
    goTo('createBill');

    expect(await screen.findByText('tour.createBill.title')).toBeInTheDocument();
    fireEvent.click(screen.getByText('+'));

    expect(create).toHaveBeenCalledOnce();
    expect(useTour.getState().stepIndex).toBe(1);
  });

  it('moves on from a look-only step by its own button', async () => {
    render(
      <>
        <div data-tour="bill-tabs" />
        <TourOverlay />
      </>,
    );
    goTo('billReady');

    fireEvent.click(await screen.findByRole('button', { name: 'tour.gotIt' }));

    expect(TOUR_STEPS[useTour.getState().stepIndex].id).toBe('openSeat');
  });

  it('opens the guest’s card itself, so the name and the face on the row are not hit', async () => {
    const open = vi.fn();
    const rename = vi.fn();
    render(
      <>
        <div>
          <button data-tour="open-seat" data-tour-key="1" aria-expanded="false" onClick={open}>Guest 1</button>
          <button onClick={rename}>rename</button>
        </div>
        <TourOverlay />
      </>,
    );
    goTo('openSeat');

    fireEvent.click(await screen.findByRole('button', { name: 'tour.openSeat.title' }));

    expect(open).toHaveBeenCalledOnce();
    expect(rename).not.toHaveBeenCalled();
    expect(TOUR_STEPS[useTour.getState().stepIndex].id).toBe('assign');
  });

  it('leaves a card that is already open as it is', async () => {
    const toggle = vi.fn();
    render(
      <>
        <button data-tour="open-seat" data-tour-key="1" aria-expanded="true" onClick={toggle}>Guest 1</button>
        <TourOverlay />
      </>,
    );
    goTo('openSeat');

    fireEvent.click(await screen.findByRole('button', { name: 'tour.openSeat.title' }));

    expect(toggle).not.toHaveBeenCalled();
    expect(TOUR_STEPS[useTour.getState().stepIndex].id).toBe('assign');
  });

  it('plays the invite instead of sending it', async () => {
    const share = vi.fn();
    api.seatDemoFriends.mockResolvedValue({
      participants: [
        { seat_index: 2, is_guest: true, guest_name: 'Madina' },
        { seat_index: 0, is_guest: false, guest_name: null },
        { seat_index: 1, is_guest: true, guest_name: 'Alisher' },
      ],
    });
    render(
      <>
        <button data-tour="invite" onClick={share}>invite</button>
        <ul data-tour="participants" />
        <TourOverlay />
      </>,
    );
    goTo('invite', { demoBillId: 42 });

    fireEvent.click(await screen.findByRole('button', { name: 'tour.invite.title' }));

    await waitFor(() => expect(TOUR_STEPS[useTour.getState().stepIndex].id).toBe('friends'));
    expect(api.seatDemoFriends).toHaveBeenCalledWith(42, 'en');
    expect(share).not.toHaveBeenCalled();
    expect(toast.showToast).not.toHaveBeenCalled();
    expect(useTour.getState().friends).toEqual(['Alisher', 'Madina']);
    expect(await screen.findByText('tour.friends.text(Alisher)')).toBeInTheDocument();
  });

  it('skipping erases the demo bill and leaves it', async () => {
    navigation.pathname = '/bill/42';
    render(
      <>
        <div data-tour="participants" />
        <TourOverlay />
      </>,
    );
    goTo('friends', { demoBillId: 42 });

    fireEvent.click(await screen.findByRole('button', { name: 'tour.skip' }));

    expect(api.eraseDemoBill).toHaveBeenCalledWith(42);
    expect(store.completeOnboarding).toHaveBeenCalledOnce();
    expect(navigation.replace).toHaveBeenCalledWith('/');
    expect(useTour.getState().active).toBe(false);
    expect(screen.queryByTestId('tour')).toBeNull();
  });

  it('keeps a way out until the last words are actually up', async () => {
    render(<TourOverlay />);
    goTo('finale');

    expect(await screen.findByRole('button', { name: 'tour.skip' })).toBeInTheDocument();
  });

  it('offers a press again when it led nowhere', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      render(
        <>
          <button data-tour="assign-confirm">confirm</button>
          <TourOverlay />
        </>,
      );
      goTo('receiptTab');

      await act(() => vi.advanceTimersByTimeAsync(6500));

      expect(TOUR_STEPS[useTour.getState().stepIndex].id).toBe('confirmDishes');
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps Escape from closing the sheet a step points into', () => {
    const closeSheet = vi.fn();
    document.addEventListener('keydown', closeSheet);
    render(<TourOverlay />);
    goTo('createBill');

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.keyDown(document, { key: 'Enter' });

    expect(closeSheet).toHaveBeenCalledTimes(1);
    document.removeEventListener('keydown', closeSheet);
  });

  it('holds Telegram’s back button for as long as the tour runs', () => {
    render(<TourOverlay />);
    expect(telegram.holdBackButton).not.toHaveBeenCalled();

    goTo('createBill');
    expect(telegram.holdBackButton).toHaveBeenCalledOnce();

    act(() => useTour.getState().stop());
    expect(telegram.release).toHaveBeenCalledOnce();
  });
});

describe('TourOverlay staging the card', () => {
  it('types the tour’s card over the field without touching the real one', async () => {
    render(
      <>
        <div data-tour="payment-chooser">
          <div data-tour="card-field"><input aria-label="card" defaultValue="" /></div>
        </div>
        <button data-tour="wizard-next">next</button>
        <TourOverlay />
      </>,
    );
    goTo('card');

    fireEvent.click(await screen.findByRole('button', { name: 'tour.card.title' }));

    expect(TOUR_STEPS[useTour.getState().stepIndex].id).toBe('paymentNext');
    expect(useTour.getState().cardStaged).toBe(true);
    expect(await screen.findByText('8600 1234 5678 9010', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByLabelText('card')).toHaveValue('');
  });
});

describe('TourOverlay on a tour of its own', () => {
  const tour: Tour = {
    name: 'guest',
    steps: [
      { id: 'guestSeat', kind: 'look', target: { anchor: 'participants' } },
      { id: 'guestDishes', kind: 'use', target: { anchor: 'bill-tabs' } },
      { id: 'guestShare', kind: 'look', target: { anchor: 'invite' }, optional: true },
    ],
  };
  const run = (stepIndex = 0) =>
    act(() => {
      useTour.getState().start('invite', tour);
      useTour.setState({ stepIndex });
    });

  it('counts its own steps', async () => {
    render(
      <>
        <ul data-tour="participants" />
        <TourOverlay />
      </>,
    );
    run();

    expect(await screen.findByText('01 / 03')).toBeInTheDocument();
  });

  it('leaves a sheet to be used as long as it is open, and carries on once it closes', async () => {
    const Screen = ({ open }: { open: boolean }) => (
      <>
        {open && <div data-tour="bill-tabs"><button>tick</button></div>}
        <div data-tour="invite" />
        <TourOverlay />
      </>
    );
    const { rerender } = render(<Screen open />);
    run(1);
    expect(await screen.findByText('tour.guestDishes.title')).toBeInTheDocument();

    fireEvent.click(screen.getByText('tick'));
    expect(useTour.getState().stepIndex).toBe(1);

    rerender(<Screen open={false} />);
    await waitFor(() => expect(useTour.getState().stepIndex).toBe(2));
  });

  it('passes over an optional step with nothing to light at once, and ends the tour there', () => {
    render(<TourOverlay />);
    run(2);

    expect(useTour.getState().active).toBe(false);
    expect(store.completeGuestTour).toHaveBeenCalledOnce();
    expect(store.completeOnboarding).not.toHaveBeenCalled();
  });

  it('ends with its last «Got it» and remembers it as the guest tour', async () => {
    render(
      <>
        <div data-tour="invite" />
        <TourOverlay />
      </>,
    );
    run(2);

    fireEvent.click(await screen.findByRole('button', { name: 'tour.gotIt' }));

    expect(useTour.getState().active).toBe(false);
    expect(store.completeGuestTour).toHaveBeenCalledOnce();
  });

  it('skipped, is remembered as the guest tour and leaves the screen it is on', async () => {
    render(
      <>
        <ul data-tour="participants" />
        <TourOverlay />
      </>,
    );
    run();

    fireEvent.click(await screen.findByText('tour.skip'));

    expect(store.completeGuestTour).toHaveBeenCalledOnce();
    expect(store.completeOnboarding).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
  });
});
