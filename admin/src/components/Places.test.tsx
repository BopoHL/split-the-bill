import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import Places from './Places';

vi.mock('@/lib/api', () => ({ api: { places: vi.fn() } }));

const { api } = await import('@/lib/api');

describe('places', () => {
  it('lists places with their bills and people', async () => {
    vi.mocked(api.places).mockResolvedValue({
      items: [{ id: 1, name: 'Caffeine', bills: 12, people: 5, first_bill_at: '2026-01-02T10:00:00', last_bill_at: null }],
      total: 1,
      limit: 50,
      offset: 0,
    });
    render(<Places />);

    const row = (await screen.findByText('Caffeine')).closest('tr') as HTMLElement;
    expect(within(row).getByText('12')).toBeInTheDocument();
    expect(within(row).getByText('5')).toBeInTheDocument();
    expect(within(row).getByText('—')).toBeInTheDocument();
    expect(api.places).toHaveBeenCalledWith('', 1, 50);
  });
});
