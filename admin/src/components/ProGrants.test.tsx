import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ProGrant } from '@/lib/api';
import ProGrants from './ProGrants';

vi.mock('@/lib/api', () => ({
  api: { proGrants: vi.fn(), revokeProGrant: vi.fn(), refundProGrant: vi.fn(), setProRenewal: vi.fn() },
}));

const { api } = await import('@/lib/api');

const grant = (overrides: Partial<ProGrant>): ProGrant => ({
  id: 1,
  user: { id: 7, telegram_id: 11, username: 'leo', name: 'Leo' },
  source: 'purchase',
  plan: 'year',
  days: 365,
  stars: 900,
  promo_code: null,
  starts_at: '2026-10-04T10:00:00',
  ends_at: '2027-10-04T10:00:00',
  created_at: '2026-10-04T10:00:00',
  revoked_at: null,
  refunded_at: null,
  subscription_id: null,
  renewal_canceled_at: null,
  state: 'active',
  actions: ['revoke', 'refund'],
  ...overrides,
});

const page = (items: ProGrant[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const row = (text: string) => screen.getByText(text).closest('tr') as HTMLElement;

describe('Pro grants', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.proGrants).mockResolvedValue(
      page([
        grant({ id: 1 }),
        grant({
          id: 2,
          user: { id: 8, telegram_id: 22, username: 'ann', name: 'Ann' },
          source: 'subscription',
          plan: 'month',
          days: 30,
          stars: 100,
          subscription_id: 5,
          actions: ['revoke', 'refund', 'stop_renewal'],
        }),
        grant({
          id: 3,
          user: { id: 9, telegram_id: 33, username: null, name: 'Dana' },
          source: 'promo',
          plan: null,
          days: 14,
          stars: null,
          promo_code: 'LAUNCH',
          state: 'revoked',
          actions: [],
        }),
      ]),
    );
  });

  afterEach(() => vi.restoreAllMocks());

  it('says whose each grant is, what it is, where it stands and only what can be done', async () => {
    render(<ProGrants onOpenUser={vi.fn()} />);

    expect(await screen.findByText('@leo')).toBeInTheDocument();
    expect(row('@leo')).toHaveTextContent('Покупка: год365 дн.');
    expect(within(row('@ann')).getByText('продлевается')).toBeInTheDocument();
    expect(within(row('@ann')).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '@ann',
      'Остановить продление',
      'Забрать Pro',
      'Вернуть звёзды',
    ]);
    expect(within(row('Dana')).getByText('забран')).toBeInTheDocument();
    expect(row('Dana')).toHaveTextContent('Промокод LAUNCH');
    expect(within(row('Dana')).getAllByRole('button')).toHaveLength(1);
  });

  it('takes Pro back only once the admin agrees, and asks for the list again', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.mocked(api.revokeProGrant).mockResolvedValue(grant({ state: 'revoked', actions: [] }));
    render(<ProGrants onOpenUser={vi.fn()} />);
    await screen.findByText('@leo');
    const revoke = within(row('@leo')).getByText('Забрать Pro');

    fireEvent.click(revoke);
    expect(api.revokeProGrant).not.toHaveBeenCalled();

    fireEvent.click(revoke);
    await waitFor(() => expect(api.revokeProGrant).toHaveBeenCalledWith(1));
    expect(confirm.mock.calls[1][0]).toContain('Звёзды не вернутся');
    await waitFor(() => expect(api.proGrants).toHaveBeenCalledTimes(2));
  });

  it('stops a subscription renewing, and says why when Telegram refuses a refund', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.setProRenewal).mockResolvedValue(grant({ id: 2 }));
    vi.mocked(api.refundProGrant).mockRejectedValue(new Error('Telegram error: CHARGE_ALREADY_REFUNDED'));
    render(<ProGrants onOpenUser={vi.fn()} />);
    await screen.findByText('@ann');

    fireEvent.click(within(row('@ann')).getByText('Остановить продление'));
    await waitFor(() => expect(api.setProRenewal).toHaveBeenCalledWith(5, true));

    fireEvent.click(within(row('@leo')).getByText('Вернуть звёзды'));
    expect(await screen.findByText('Telegram error: CHARGE_ALREADY_REFUNDED')).toBeInTheDocument();
  });

  it('in a person’s card, lists only theirs, without the search', async () => {
    render(<ProGrants userId={7} />);

    await screen.findAllByText('Забрать Pro');
    expect(api.proGrants).toHaveBeenCalledWith({ user_id: 7 }, 1, 50);
    expect(screen.queryByPlaceholderText('@username или telegram id')).toBeNull();
    expect(screen.queryByText('Кто')).toBeNull();
  });
});
