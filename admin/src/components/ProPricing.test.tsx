import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ProSettings } from '@/lib/api';
import ProPricing from './ProPricing';

vi.mock('@/lib/api', () => ({ api: { pro: vi.fn(), savePro: vi.fn() } }));

const { api } = await import('@/lib/api');

const settings = (year: number, scans = 3, wasYear: number | null = null): ProSettings => ({
  prices: { month: 100, half_year: 500, year },
  was_prices: { month: null, half_year: null, year: wasYear },
  free_scans_per_day: scans,
  offer_percent: 40,
  offer_hours: 48,
  stats: { active: 12, paying: 4, trial: 8, stars_last_30_days: 1500, stars_total: 4200 },
});

describe('Pro pricing', () => {
  it('shows who has Pro and saves new prices and the free scans', async () => {
    vi.mocked(api.pro).mockResolvedValue(settings(900));
    vi.mocked(api.savePro).mockResolvedValue(settings(800, 5));
    render(<ProPricing />);

    expect(await screen.findByText('4 200')).toBeInTheDocument();
    expect(screen.getByText('≈75 ★ в месяц · выгода 25%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled();

    fireEvent.change(screen.getByRole('spinbutton', { name: /^Год/ }), { target: { value: '800' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: /Бесплатных сканов/ }), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(api.savePro).toHaveBeenCalledWith({
      prices: { month: 100, half_year: 500, year: 800 },
      was_prices: { month: null, half_year: null, year: null },
      free_scans_per_day: 5,
      offer_percent: 40,
      offer_hours: 48,
    }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled());
  });

  it('sets the first-purchase offer', async () => {
    vi.mocked(api.pro).mockResolvedValue(settings(900));
    vi.mocked(api.savePro).mockResolvedValue(settings(900));
    render(<ProPricing />);

    fireEvent.change(await screen.findByRole('spinbutton', { name: /Скидка/ }), { target: { value: '30' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: /Действует/ }), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(api.savePro).toHaveBeenCalledWith(expect.objectContaining({ offer_percent: 30, offer_hours: 24 })));
  });

  it('shows why the prices were refused', async () => {
    vi.mocked(api.pro).mockResolvedValue(settings(900));
    vi.mocked(api.savePro).mockRejectedValue(new Error('A price is 1 to 10000 Stars'));
    render(<ProPricing />);

    fireEvent.change(await screen.findByRole('spinbutton', { name: /^Год/ }), { target: { value: '20000' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Сохранить' }).closest('form')!);

    expect(await screen.findByText('A price is 1 to 10000 Stars')).toBeInTheDocument();
  });

  it('sets a struck-out old price and shows what is off', async () => {
    vi.mocked(api.pro).mockResolvedValue(settings(900));
    vi.mocked(api.savePro).mockResolvedValue(settings(900, 3, 1200));
    render(<ProPricing />);

    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Старая цена: Год' }), { target: { value: '1200' } });
    expect(screen.getByText('−25%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(api.savePro).toHaveBeenCalledWith(expect.objectContaining({
      was_prices: { month: null, half_year: null, year: 1200 },
    })));
  });
});
