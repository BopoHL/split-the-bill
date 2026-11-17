import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { analyticsFixture } from '@/test/analyticsFixtures';
import { usePro } from '@/lib/store/usePro';

const getAnalytics = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api/analytics', () => ({ getAnalytics }));
vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'ru', currentUser: { id: 1 } };
  const useStore = Object.assign(
    (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});

import AnalyticsPanel from './AnalyticsPanel';

beforeEach(() => {
  getAnalytics.mockReset();
  getAnalytics.mockResolvedValue(analyticsFixture());
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 3, 12));
});

describe('AnalyticsPanel', () => {
  it('asks for nothing until the tab is opened', async () => {
    const { rerender } = render(<AnalyticsPanel userId={1} active={false} />);
    expect(getAnalytics).not.toHaveBeenCalled();

    rerender(<AnalyticsPanel userId={1} active />);

    await waitFor(() => expect(getAnalytics).toHaveBeenCalledWith(1, { kind: 'month', year: 2026, month: 10 }));
  });

  it('opens on the overview of this month', async () => {
    render(<AnalyticsPanel userId={1} active />);

    expect(await screen.findByText('Вы потратили')).toBeInTheDocument();
    expect(screen.getByText('145 000 сум')).toBeInTheDocument();
    expect(screen.getByText('+45% к прошлому месяцу')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ваш день — суббота' })).toBeInTheDocument();
    expect(screen.getByText('Завсегдатай')).toBeInTheDocument();
  });

  it('moves between sections without asking again', async () => {
    const user = userEvent.setup();
    render(<AnalyticsPanel userId={1} active />);
    await screen.findByText('Вы потратили');

    await user.click(screen.getByRole('button', { name: 'Еда' }));
    expect(screen.getByText('Burger Black Angus')).toBeInTheDocument();
    expect(screen.getByText('Куда уходят ваши деньги')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Люди' }));
    expect(screen.getByText('Вы и Alice')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Места' }));
    expect(screen.getAllByText('Caffeine').length).toBeGreaterThan(0);
    expect(getAnalytics).toHaveBeenCalledTimes(1);
  });

  it('steps back a month, and switches to a year', async () => {
    const user = userEvent.setup();
    render(<AnalyticsPanel userId={1} active />);
    await screen.findByText('Вы потратили');

    await user.click(screen.getByRole('button', { name: 'Предыдущий период' }));
    await waitFor(() => expect(getAnalytics).toHaveBeenLastCalledWith(1, { kind: 'month', year: 2026, month: 9 }));
    expect(screen.getByRole('button', { name: 'Следующий период' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Год' }));
    await waitFor(() => expect(getAnalytics).toHaveBeenLastCalledWith(1, { kind: 'year', year: 2026 }));
  });

  it('offers the report for any period and the stories for a year', async () => {
    const user = userEvent.setup();
    render(<AnalyticsPanel userId={1} active />);
    await screen.findByText('Вы потратили');

    expect(screen.getByRole('button', { name: 'Отчёт-чек' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Итоги года' })).not.toBeInTheDocument();

    getAnalytics.mockResolvedValue(analyticsFixture({ period: { ...analyticsFixture().period, kind: 'year', month: null } }));
    await user.click(screen.getByRole('button', { name: 'Год' }));

    expect(await screen.findByRole('button', { name: 'Итоги года' })).toBeInTheDocument();
  });

  it('says so when the period has no bills', async () => {
    getAnalytics.mockResolvedValue(analyticsFixture({ overview: { ...analyticsFixture().overview, bills: 0 } }));
    render(<AnalyticsPanel userId={1} active />);

    expect(await screen.findByText('За этот период счетов нет')).toBeInTheDocument();
  });

  it('without Pro keeps the top of the overview and offers the rest', async () => {
    const user = userEvent.setup();
    usePro.setState({ paywall: null });
    getAnalytics.mockResolvedValue(analyticsFixture({ locked: true }));
    render(<AnalyticsPanel userId={1} active />);

    expect(await screen.findByText('145 000 сум')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Ваш день — суббота' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ещё больше — с Pro' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Отчёт-чек' }));
    expect(usePro.getState().paywall).toBe('analytics');

    usePro.setState({ paywall: null });
    await user.click(screen.getByRole('button', { name: 'Еда' }));
    expect(screen.queryByText('Burger Black Angus')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Открыть с Pro' }));
    expect(usePro.getState().paywall).toBe('analytics');
  });

  it('shows a period seen before at once and asks for it again quietly', async () => {
    const user = userEvent.setup();
    getAnalytics.mockImplementation((_userId: number, period: { month?: number }) =>
      Promise.resolve(analyticsFixture({ overview: { ...analyticsFixture().overview, spent: period.month === 9 ? 50_000 : 145_000 } })));
    render(<AnalyticsPanel userId={1} active />);
    expect(await screen.findByText('145 000 сум')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Предыдущий период' }));
    expect(await screen.findByText('50 000 сум')).toBeInTheDocument();
    let release: (value: unknown) => void = () => {};
    getAnalytics.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    await user.click(screen.getByRole('button', { name: 'Следующий период' }));

    expect(screen.getByText('145 000 сум')).toBeInTheDocument();
    expect(screen.getByText('145 000 сум').closest('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
    expect(getAnalytics).toHaveBeenCalledTimes(3);
    release(analyticsFixture());
  });
});
