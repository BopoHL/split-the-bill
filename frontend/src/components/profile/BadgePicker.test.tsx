import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const store = vi.hoisted(() => ({
  language: 'ru',
  currentUser: { id: 7, settings: { language: 'ru' } } as { id: number; settings: Record<string, unknown> },
  setCurrentUser: vi.fn(),
}));
vi.mock('@/lib/store/useStore', () => ({ useStore: () => store }));
const api = vi.hoisted(() => ({ getBadges: vi.fn(), chooseBadge: vi.fn() }));
vi.mock('@/lib/api/badges', () => api);

import BadgePicker from './BadgePicker';

describe('BadgePicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
    api.getBadges.mockResolvedValue({
      chosen: null,
      shown: 'pro',
      available: [{ key: 'pro', value: null, subject: null }, { key: 'regular', value: 6, subject: 'Caffeine' }],
    });
  });

  it('offers none, Pro and the earned titles, the shown one checked', async () => {
    render(<BadgePicker isOpen onClose={vi.fn()} />);

    const options = await screen.findAllByRole('radio');
    expect(options.map((option) => option.textContent)).toEqual([
      'Без бейджау имени ничего',
      'Proпока есть Pro',
      'ЗавсегдатайCaffeine: 6 визитов',
    ]);
    expect(options[1]).toHaveAttribute('aria-checked', 'true');
  });

  it('keeps the shown title checked once the numbers have moved on from it', async () => {
    api.getBadges.mockResolvedValue({ chosen: 'regular', shown: 'regular', available: [{ key: 'regular', value: null, subject: null }] });
    render(<BadgePicker isOpen onClose={vi.fn()} />);

    const kept = await screen.findByRole('radio', { name: /Завсегдатай/ });
    expect(kept).toHaveAttribute('aria-checked', 'true');
    expect(kept).toHaveTextContent('заработан раньше — ваш, пока он выбран');
  });

  it('keeps the pick and shows it by the name at once', async () => {
    api.chooseBadge.mockResolvedValue({ chosen: 'regular', shown: 'regular', available: [] });
    render(<BadgePicker isOpen onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('radio', { name: /Завсегдатай/ }));

    await waitFor(() => expect(api.chooseBadge).toHaveBeenCalledWith(7, 'regular'));
    expect(store.setCurrentUser).toHaveBeenCalledWith({ id: 7, settings: { language: 'ru', badge: 'regular' } });
  });
});
