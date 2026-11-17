import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { DishRow } from '@/lib/api';
import Dishes from './Dishes';

vi.mock('@/lib/api', () => ({
  api: { dishes: vi.fn(), dishKinds: vi.fn(), correctDish: vi.fn(), createDishKind: vi.fn() },
}));

const { api } = await import('@/lib/api');

const dish = (overrides: Partial<DishRow>): DishRow => ({
  name_key: 'пиво',
  group: 'drink',
  kind: null,
  kind_name: null,
  model: 'gpt-5-mini',
  lines: 12,
  updated_at: '2026-10-01T10:00:00',
  ...overrides,
});

describe('dishes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.dishes).mockResolvedValue({ items: [dish({})], total: 1, limit: 50, offset: 0 });
    vi.mocked(api.dishKinds).mockResolvedValue([{ key: 'beer', ru: 'Пиво', uz: 'Pivo', en: 'Beer' }]);
  });

  it('corrects what a wording is and shows it was done by hand', async () => {
    vi.mocked(api.correctDish).mockResolvedValue(dish({ group: 'alcohol', kind: 'beer', kind_name: 'Пиво', model: 'admin' }));
    render(<Dishes />);

    const row = (await screen.findByText('пиво')).closest('tr') as HTMLElement;
    await waitFor(() => expect(within(row).getByRole('option', { name: 'Пиво' })).toBeInTheDocument());
    fireEvent.change(within(row).getByRole('combobox', { name: 'Группа: пиво' }), { target: { value: 'alcohol' } });

    await waitFor(() => expect(api.correctDish).toHaveBeenCalledWith('пиво', 'alcohol', null));
    expect(await within(row).findByText('вручную')).toBeInTheDocument();
    expect(within(row).getByRole('combobox', { name: 'Тип: пиво' })).toHaveValue('beer');
  });

  it('filters by group and adds a kind the model did not name', async () => {
    vi.mocked(api.createDishKind).mockResolvedValue({ key: 'lagman', ru: 'Лагман', uz: 'Lag‘mon', en: 'Lagman' });
    render(<Dishes />);
    await screen.findByText('пиво');

    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'food' } });
    await waitFor(() => expect(api.dishes).toHaveBeenLastCalledWith({ q: '', group: 'food', kind: '' }, 1, 50));

    for (const [label, value] of [['Ключ', 'lagman'], ['По-русски', 'Лагман'], ['По-узбекски', 'Lag‘mon'], ['По-английски', 'Lagman']]) {
      fireEvent.change(screen.getByRole('textbox', { name: label }), { target: { value } });
    }
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));

    await waitFor(() => expect(api.createDishKind).toHaveBeenCalledWith({ key: 'lagman', ru: 'Лагман', uz: 'Lag‘mon', en: 'Lagman' }));
    expect(await screen.findByText('Добавлен тип «Лагман»')).toBeInTheDocument();
    expect(api.dishKinds).toHaveBeenCalledTimes(2);
  });
});
