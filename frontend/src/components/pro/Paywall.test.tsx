import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { User } from '@/types/api';
import type { ProOverview } from '@/types/pro';
import { useStore } from '@/lib/store/useStore';
import { usePro } from '@/lib/store/usePro';
import Paywall from './Paywall';

const createProInvoice = vi.fn();
const getPro = vi.fn();
const redeemPromo = vi.fn();
const openInvoice = vi.fn();
const startProOffer = vi.fn();
const getOwed = vi.fn();

vi.mock('@/lib/api/pro', () => ({
  createProInvoice: (...args: unknown[]) => createProInvoice(...args),
  getPro: (...args: unknown[]) => getPro(...args),
  redeemPromo: (...args: unknown[]) => redeemPromo(...args),
  startProOffer: (...args: unknown[]) => startProOffer(...args),
}));

vi.mock('@/lib/api/reminders', () => ({
  getOwed: (...args: unknown[]) => getOwed(...args),
}));

vi.mock('@/lib/telegram/invoice', () => ({
  canOpenInvoice: () => true,
  openInvoice: (...args: unknown[]) => openInvoice(...args),
}));

const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
  setPersonProperties: vi.fn(),
}));

const telegramBack = vi.hoisted(() => ({ handler: null as (() => void) | null, release: vi.fn() }));
vi.mock('@/lib/telegram/init', () => ({
  showBackButton: (onClick: () => void) => {
    telegramBack.handler = onClick;
    return telegramBack.release;
  },
}));

const FREE: ProOverview = {
  active: false,
  until: null,
  trial: false,
  subscription: false,
  plans: [
    { plan: 'month', stars: 100, months: 1, recurring: true },
    { plan: 'half_year', stars: 500, months: 6, recurring: false },
    { plan: 'year', stars: 900, months: 12, recurring: false },
  ],
  free_scans_per_day: 3,
  scans_left_today: 0,
  free_reminders_per_month: 3,
  reminders_left_this_month: 0,
};

type Reason = Parameters<ReturnType<typeof usePro.getState>['openPaywall']>[0];

const open = (reason: Reason, overview: ProOverview = FREE, resume?: () => void) => {
  usePro.setState({ overview, paywall: null });
  render(<Paywall />);
  act(() => usePro.getState().openPaywall(reason, resume));
};

const inHours = (hours: number) => new Date(Date.now() + hours * 3600_000).toISOString();

const WITH_OFFER: ProOverview = {
  ...FREE,
  plans: FREE.plans.map((offer) => (offer.recurring ? offer : { ...offer, was_stars: offer.stars, stars: Math.round(offer.stars * 0.6) })),
  offer: { percent: 40, ends_at: inHours(2) },
};

describe('Paywall', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
    Element.prototype.scrollIntoView = vi.fn();
    useStore.setState({ language: 'ru', currentUser: { id: 1 } as User });
    [createProInvoice, getPro, redeemPromo, openInvoice, track, startProOffer, getOwed].forEach((mock) => mock.mockReset());
    // No offer to be had unless a test makes one.
    startProOffer.mockReturnValue(new Promise(() => {}));
    getOwed.mockReturnValue(new Promise(() => {}));
  });

  it('says what was asked for, starts on the month and marks the year as the better deal', () => {
    open('scans');

    expect(screen.getByRole('heading', { name: 'Бесплатные сканы на сегодня закончились' })).toBeInTheDocument();
    expect(screen.getByText('С Pro — сканируйте без лимита.')).toBeInTheDocument();
    // What it was opened over leads the table, lit.
    const [, first] = screen.getAllByRole('row');
    expect(first).toHaveAccessibleName(/Сканы чеков и QR/);
    expect(first).toHaveClass('bg-accent-weak');

    const month = screen.getByRole('radio', { name: /Месяц/ });
    expect(month).toHaveAttribute('aria-checked', 'true');
    expect(month).toHaveTextContent(/^Месяц100≈3 в день$/);
    const year = screen.getByRole('radio', { name: /Год/ });
    expect(year).toHaveAttribute('aria-checked', 'false');
    expect(year).toHaveTextContent('≈75 / мес');
    expect(year).toHaveTextContent('−25%');
    expect(year).toHaveTextContent('Выгоднее');
    expect(screen.getByRole('button', { name: /Подписаться за 100/ })).toBeEnabled();
  });

  it('strikes out the old price and says what is off it', () => {
    open('general', { ...FREE, plans: FREE.plans.map((offer) => (offer.plan === 'month' ? { ...offer, was_stars: 200 } : offer)) });

    const month = screen.getByRole('radio', { name: /Месяц/ });
    expect(month.querySelector('s')).toHaveTextContent('200');
    expect(month).toHaveTextContent('−50%');
  });

  it('tells Pro previews take the theme, and the price follows the plan chosen', async () => {
    open('themes');

    expect(screen.getByRole('row', { name: /Превью счёта в чатах/ })).toHaveTextContent('в цвет темы');
    fireEvent.click(screen.getByRole('radio', { name: /Месяц/ }));

    expect(screen.getByRole('radio', { name: /Месяц/ })).toHaveAttribute('aria-checked', 'true');
    expect(await screen.findByRole('button', { name: /Подписаться за 100/ })).toBeEnabled();
  });

  it('pays for the chosen plan and waits for the server to grant it', async () => {
    createProInvoice.mockResolvedValue('https://t.me/$invoice');
    openInvoice.mockResolvedValue('paid');
    getPro.mockResolvedValue({ ...FREE, active: true, until: '2027-10-04T10:00:00', scans_left_today: null });
    open('general');

    fireEvent.click(screen.getByRole('radio', { name: /6 месяцев/ }));
    fireEvent.click(screen.getByRole('button', { name: /Оформить за 500/ }));

    expect(await screen.findByText(/Готово! Pro до 4 октября 2027/)).toBeInTheDocument();
    expect(createProInvoice).toHaveBeenCalledWith(1, 'half_year');
    expect(openInvoice).toHaveBeenCalledWith('https://t.me/$invoice');
    expect(usePro.getState().overview?.active).toBe(true);
    expect(track.mock.calls).toEqual([
      ['paywall_opened', { reason: 'general' }],
      ['paywall_plan_selected', { plan: 'half_year' }],
      ['pro_checkout_started', { plan: 'half_year', stars: 500, reason: 'general' }],
      ['pro_checkout_result', { plan: 'half_year', status: 'paid' }],
      ['pro_activated', { via: 'stars', plan: 'half_year' }],
    ]);
    // Leaving with Pro in hand is no drop-off.
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(track).not.toHaveBeenCalledWith('paywall_closed', expect.anything());
  });

  it('a check lost to the network after paying is not a failed payment', async () => {
    createProInvoice.mockResolvedValue('https://t.me/$invoice');
    openInvoice.mockResolvedValue('paid');
    getPro
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ ...FREE, active: true, until: '2027-10-04T10:00:00', scans_left_today: null });
    open('general');

    fireEvent.click(screen.getByRole('button', { name: /Подписаться за 100/ }));

    expect(await screen.findByText(/Готово! Pro до 4 октября 2027/, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(track).not.toHaveBeenCalledWith('pro_checkout_result', expect.objectContaining({ status: 'error' }));
  });

  it('counts the plan on screen when a subscriber leaves, not the month they cannot take', () => {
    open('general', { ...FREE, active: true, subscription: true, until: '2026-11-01T00:00:00', scans_left_today: null });
    expect(screen.getByRole('radio', { name: /6 месяцев/ })).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

    expect(track).toHaveBeenCalledWith('paywall_closed', { reason: 'general', via: 'close', plan: 'half_year', seconds: 0 });
  });

  it('leaves the plan out when none was on screen yet', () => {
    open('voice', { ...FREE, plans: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Не сейчас' }));

    expect(track).toHaveBeenCalledWith('paywall_closed', { reason: 'voice', via: 'not_now', seconds: 0 });
  });

  it('lets them go with «Not now» and counts how they left', () => {
    open('voice');

    fireEvent.click(screen.getByRole('button', { name: 'Не сейчас' }));

    expect(usePro.getState().paywall).toBeNull();
    expect(track).toHaveBeenCalledWith('paywall_closed', { reason: 'voice', via: 'not_now', plan: 'month', seconds: 0 });
  });

  it('stays put when the invoice is closed unpaid', async () => {
    createProInvoice.mockResolvedValue('https://t.me/$invoice');
    openInvoice.mockResolvedValue('cancelled');
    open('analytics');

    fireEvent.click(screen.getByRole('button', { name: /Подписаться за 100/ }));

    await waitFor(() => expect(screen.getByRole('button', { name: /Подписаться за 100/ })).toBeEnabled());
    expect(getPro).not.toHaveBeenCalled();
    expect(usePro.getState().paywall).toBe('analytics');
    expect(track).toHaveBeenCalledWith('pro_checkout_result', { plan: 'month', status: 'cancelled' });
    expect(track).not.toHaveBeenCalledWith('pro_activated', expect.anything());
  });

  it('counts a failed invoice once, before the sheet opens', async () => {
    createProInvoice.mockRejectedValue(new Error('down'));
    open('scans');

    fireEvent.click(screen.getByRole('button', { name: /Подписаться за 100/ }));

    await waitFor(() => expect(track).toHaveBeenCalledWith('pro_checkout_result', { plan: 'month', status: 'error' }));
    expect(track.mock.calls.filter(([event]) => event === 'pro_checkout_result')).toHaveLength(1);
  });

  it('explains a promo code that did not work', async () => {
    redeemPromo.mockRejectedValue({ response: { data: { detail: { code: 'PROMO_EXPIRED' } } } });
    open('general');

    fireEvent.click(screen.getByRole('button', { name: 'Есть промокод?' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Промокод' }), { target: { value: 'old' } });
    fireEvent.click(screen.getByRole('button', { name: 'Применить' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Срок промокода истёк');
    expect(screen.getByRole('textbox', { name: 'Промокод' })).toHaveAttribute('aria-invalid', 'true');
    expect(redeemPromo).toHaveBeenCalledWith(1, 'old');
    expect(track).toHaveBeenCalledWith('promo_redeemed', { ok: false, error: 'PROMO_EXPIRED' });

    fireEvent.change(screen.getByRole('textbox', { name: 'Промокод' }), { target: { value: 'oldx' } });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('opens the promo code roomy and focused, and folds it away again', () => {
    open('general');

    fireEvent.click(screen.getByRole('button', { name: 'Есть промокод?' }));

    expect(screen.getByRole('textbox', { name: 'Промокод' })).toHaveFocus();
    expect(screen.getByText('Pro добавится к тому, что у вас уже есть.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(screen.queryByRole('textbox', { name: 'Промокод' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Есть промокод?' })).toBeInTheDocument();
  });

  it('keeps the plans and the button out of the way of a promo code', () => {
    open('general');

    fireEvent.click(screen.getByRole('button', { name: 'Есть промокод?' }));
    expect(screen.queryByRole('radiogroup')).toBeNull();
    expect(screen.queryByRole('button', { name: /Подписаться/ })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
  });

  it('says only Pro still reminds a debtor who blocked the bot', () => {
    open('reminders');

    const [free, pro] = within(screen.getByRole('row', { name: /Напоминания должникам/ })).getAllByRole('cell');
    expect(pro).toHaveTextContent('даже если бот заблокирован');
    expect(free).not.toHaveTextContent('даже если бот заблокирован');
  });

  it('says reminding everyone is free three times a month and unlimited with Pro', () => {
    open('reminders');

    const row = screen.getByRole('row', { name: /Напоминания должникам/ });
    expect(row).toHaveTextContent('3 в месяц');
    expect(row).toHaveTextContent('без ограничений');
  });

  it('does not sell a second subscription to someone who has one', () => {
    open('general', { ...FREE, active: true, subscription: true, until: '2026-11-01T00:00:00', scans_left_today: null });

    const month = screen.getByRole('radio', { name: /Месяц/ });
    expect(month).toBeDisabled();
    expect(month).toHaveTextContent('уже оформлена');
    expect(screen.getByRole('radio', { name: /6 месяцев/ })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: /Продлить за 500/ })).toBeEnabled();
  });

  it('counts down the one-off offer the server made and sells at its price', async () => {
    startProOffer.mockResolvedValue(WITH_OFFER);
    createProInvoice.mockReturnValue(new Promise(() => {}));
    open('general');

    expect(await screen.findByText('Первая покупка: −40% на полгода и год')).toBeInTheDocument();
    expect(startProOffer).toHaveBeenCalledWith(1);
    expect(screen.getByRole('timer')).toHaveTextContent(/^(1:59:\d\d|2:00:00)$/);
    const year = screen.getByRole('radio', { name: /Год/ });
    expect(year).toHaveTextContent('540');
    expect(year.querySelector('s')).toHaveTextContent('900');

    fireEvent.click(year);
    fireEvent.click(screen.getByRole('button', { name: /Оформить за 540/ }));
    expect(track).toHaveBeenCalledWith('pro_checkout_started', { plan: 'year', stars: 540, reason: 'general', offer_percent: 40 });
  });

  it('puts the prices back once the offer is over', async () => {
    startProOffer.mockResolvedValue({ ...WITH_OFFER, offer: { percent: 40, ends_at: inHours(-0.001) } });
    getPro.mockResolvedValue(FREE);
    open('general');

    await waitFor(() => expect(getPro).toHaveBeenCalledWith(1));
    expect(screen.queryByRole('timer')).toBeNull();
    await waitFor(() => expect(screen.getByRole('radio', { name: /Год/ })).toHaveTextContent('Год900≈75 / мес'));
  });

  it('carries on with what it stopped once Pro is there', async () => {
    const resume = vi.fn();
    redeemPromo.mockResolvedValue({ ...FREE, active: true, until: '2027-01-01T00:00:00', scans_left_today: null });
    open('reminders', FREE, resume);

    fireEvent.click(screen.getByRole('button', { name: 'Есть промокод?' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Промокод' }), { target: { value: 'gift' } });
    fireEvent.click(screen.getByRole('button', { name: 'Применить' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Продолжить' }));

    expect(resume).toHaveBeenCalledOnce();
    expect(usePro.getState().paywall).toBeNull();
  });

  it('says how much the reminders are there to bring back', async () => {
    getOwed.mockResolvedValue({ totals: [{ currency: 'uzs', amount: 450000 }], people: 3, bills: 2, remindable: 3 });
    open('reminders');

    expect(await screen.findByText('Вам должны')).toBeInTheDocument();
    expect(getOwed).toHaveBeenCalledWith(1);
    expect(screen.getByText('3 человека')).toBeInTheDocument();
  });

  it('closes on Escape', () => {
    open('reminders');

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(usePro.getState().paywall).toBeNull();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('goes back to what it was opened over with Telegram’s back button', () => {
    open('reminders');

    act(() => telegramBack.handler?.());

    expect(usePro.getState().paywall).toBeNull();
    expect(telegramBack.release).toHaveBeenCalled();
  });

  it('goes back with a swipe from the left edge, like a screen', () => {
    open('reminders');
    const sheet = screen.getByRole('dialog');
    const touch = (x: number) => ({ identifier: 1, clientX: x, clientY: 300 });

    fireEvent.touchStart(sheet, { touches: [touch(8)], changedTouches: [touch(8)] });
    fireEvent.touchMove(sheet, { touches: [touch(30)], changedTouches: [touch(30)] });
    fireEvent.touchMove(sheet, { touches: [touch(600)], changedTouches: [touch(600)] });
    fireEvent.touchEnd(sheet, { touches: [], changedTouches: [touch(600)] });

    expect(usePro.getState().paywall).toBeNull();
  });
});
