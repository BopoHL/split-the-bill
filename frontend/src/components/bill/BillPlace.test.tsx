import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { billFixture } from '@/test/billFixtures';

const api = vi.hoisted(() => ({ getPlaces: vi.fn(), setBillPlace: vi.fn() }));
vi.mock('@/lib/api/analytics', () => api);
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));
vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', currentUser: { id: 10 } };
  const useStore = Object.assign(
    (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});

import BillPlace from './BillPlace';

beforeEach(() => {
  api.getPlaces.mockResolvedValue(['Caffeine', 'Evos']);
  api.setBillPlace.mockReset();
});

describe('BillPlace', () => {
  it('lets the owner name the place, offering the ones they have been', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    api.setBillPlace.mockResolvedValue('Evos');
    render(<BillPlace bill={billFixture({ place: null })} ownerId={10} canEdit onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: 'Add the place' }));
    await waitFor(() => expect(api.getPlaces).toHaveBeenCalledWith(10));
    await user.type(screen.getByRole('combobox', { name: 'Place' }), 'Evos{Enter}');

    expect(api.setBillPlace).toHaveBeenCalledWith(1, 'Evos');
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('Evos'));
  });

  it('shows the place to everyone else and nothing when there is none', () => {
    const { rerender, container } = render(<BillPlace bill={billFixture({ place: 'Caffeine' })} ownerId={10} canEdit={false} onChange={vi.fn()} />);
    expect(screen.getByText('Caffeine')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();

    rerender(<BillPlace bill={billFixture({ place: null })} ownerId={10} canEdit={false} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
