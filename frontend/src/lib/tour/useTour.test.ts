import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/analytics', () => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: {} }));

import { setAnalyticsContext } from '@/lib/analytics';
import { useTour } from './useTour';

beforeEach(() => useTour.getState().stop());

describe('useTour', () => {
  it('marks events as the tour\'s for as long as it runs', () => {
    useTour.getState().start('first_run');
    expect(setAnalyticsContext).toHaveBeenLastCalledWith({ in_tour: 'host' });

    useTour.getState().stop();
    expect(setAnalyticsContext).toHaveBeenLastCalledWith({});
  });

  it('starts from the first step with nothing left over', () => {
    useTour.setState({ demoBillId: 9, friends: ['A'] });

    useTour.getState().start('settings');

    expect(useTour.getState()).toMatchObject({ active: true, stepIndex: 0, demoBillId: null, friends: [] });
  });

  it('moves on once per step, however many times it is told to', () => {
    const { start, advance } = useTour.getState();
    start('first_run');

    advance('createBill');
    advance('createBill');

    expect(useTour.getState().stepIndex).toBe(1);
  });

  it('ignores a step it is not on', () => {
    useTour.getState().start('first_run');

    useTour.getState().advance('people');

    expect(useTour.getState().stepIndex).toBe(0);
  });

  it('steps back to a press that led nowhere, once', () => {
    const { start, advance, rewind } = useTour.getState();
    start('first_run');
    advance('createBill');

    rewind('peopleMore');
    rewind('peopleMore');

    expect(useTour.getState().stepIndex).toBe(0);
  });

  it('runs the tour it is given, by that tour’s own steps', () => {
    const { start, advance } = useTour.getState();
    start('invite', {
      name: 'guest',
      steps: [
        { id: 'guestSeat', kind: 'look', target: { anchor: 'participants' } },
        { id: 'guestShare', kind: 'look', target: { anchor: 'invite' } },
      ],
    });

    advance('guestSeat');

    expect(useTour.getState().tour.name).toBe('guest');
    expect(useTour.getState().stepIndex).toBe(1);
  });

  it('runs the host tour when none is named', () => {
    useTour.getState().start('settings');

    expect(useTour.getState().tour.name).toBe('host');
  });

  it('does nothing while no tour runs', () => {
    useTour.getState().advance('createBill');

    expect(useTour.getState()).toMatchObject({ active: false, stepIndex: 0 });
  });
});
