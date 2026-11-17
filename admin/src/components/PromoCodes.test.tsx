import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { PromoCode } from '@/lib/api';
import PromoCodes from './PromoCodes';

vi.mock('@/lib/api', () => ({
  api: { promoCodes: vi.fn(), createPromoCode: vi.fn(), setPromoCodeActive: vi.fn() },
}));

const { api } = await import('@/lib/api');

const promo = (overrides: Partial<PromoCode>): PromoCode => ({
  id: 1,
  code: 'FRIENDS',
  days: 30,
  max_uses: null,
  uses: 0,
  expires_at: null,
  is_active: true,
  note: null,
  created_at: '2026-10-01T10:00:00',
  ...overrides,
});

describe('promo codes', () => {
  it('lists the codes with what stops each', async () => {
    vi.mocked(api.promoCodes).mockResolvedValue([
      promo({ id: 1, code: 'FRIENDS', max_uses: 10, uses: 3 }),
      promo({ id: 2, code: 'ONCE', max_uses: 1, uses: 1, days: 365 }),
      promo({ id: 3, code: 'OLD', expires_at: '2020-01-01T00:00:00' }),
      promo({ id: 4, code: 'OFF', is_active: false, days: 45 }),
    ]);
    render(<PromoCodes />);

    const row = (code: string) => screen.getByText(code).closest('tr') as HTMLElement;
    expect(await screen.findByText('FRIENDS')).toBeInTheDocument();
    expect(within(row('FRIENDS')).getByText('действует')).toBeInTheDocument();
    expect(row('FRIENDS')).toHaveTextContent('3 / 10');
    expect(within(row('ONCE')).getByText('израсходован')).toBeInTheDocument();
    expect(within(row('ONCE')).getByText('1 год')).toBeInTheDocument();
    expect(within(row('OLD')).getByText('истёк')).toBeInTheDocument();
    expect(within(row('OFF')).getByText('45 дн.')).toBeInTheDocument();
    expect(within(row('OFF')).getByRole('button', { name: 'Включить' })).toBeInTheDocument();
  });

  it('creates a code for the chosen term, limited and dated in Tashkent time', async () => {
    vi.mocked(api.promoCodes).mockResolvedValue([]);
    vi.mocked(api.createPromoCode).mockResolvedValue(promo({ id: 5, code: 'SUMMER', days: 182, max_uses: 50 }));
    render(<PromoCodes />);

    fireEvent.change(await screen.findByRole('textbox', { name: 'Код' }), { target: { value: 'summer' } });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '182' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Сколько человек' }), { target: { value: '50' } });
    fireEvent.change(screen.getByLabelText('Ввести до (Ташкент)'), { target: { value: '2026-12-31T23:59' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Заметка' }), { target: { value: ' блогер ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    await waitFor(() => expect(api.createPromoCode).toHaveBeenCalledWith({
      code: 'SUMMER',
      days: 182,
      max_uses: 50,
      expires_at: '2026-12-31T18:59:00.000Z',
      note: 'блогер',
    }));
    expect(await screen.findByText(/Создан код/)).toHaveTextContent('Создан код SUMMER');
    expect(screen.getByRole('textbox', { name: 'Код' })).toHaveValue('');
  });

  it('leaves the code to the server and takes a number of days of its own', async () => {
    vi.mocked(api.promoCodes).mockResolvedValue([]);
    vi.mocked(api.createPromoCode).mockResolvedValue(promo({ id: 6, code: 'K7M2PQ9X', days: 10 }));
    render(<PromoCodes />);

    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'custom' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Дней' }), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    await waitFor(() => expect(api.createPromoCode).toHaveBeenCalledWith({ days: 10 }));
    expect(await screen.findAllByText('K7M2PQ9X')).toHaveLength(2);
  });

  it('switches a code off', async () => {
    vi.mocked(api.promoCodes).mockResolvedValue([promo({ id: 1 })]);
    vi.mocked(api.setPromoCodeActive).mockResolvedValue(promo({ id: 1, is_active: false }));
    render(<PromoCodes />);

    fireEvent.click(await screen.findByRole('button', { name: 'Выключить' }));

    await waitFor(() => expect(api.setPromoCodeActive).toHaveBeenCalledWith(1, false));
    expect(await screen.findByText('выключен')).toBeInTheDocument();
  });
});
