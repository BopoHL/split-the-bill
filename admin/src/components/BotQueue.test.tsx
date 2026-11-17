import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { BotQueue as Queue, BotUpdate } from '@/lib/api';
import BotQueue from './BotQueue';

vi.mock('@/lib/api', () => ({
  api: { botQueue: vi.fn(), botUpdates: vi.fn(), retryBotUpdate: vi.fn(), settleBotUpdate: vi.fn() },
}));

const { api } = await import('@/lib/api');

const queue: Queue = {
  slots: 4,
  waiting: 2,
  in_hand: 1,
  retrying: 0,
  oldest_waiting_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  handled_last_hour: 37,
  failed_last_day: 1,
  unsettled_payments: 1,
};

const update = (overrides: Partial<BotUpdate>): BotUpdate => ({
  update_id: 101,
  lane: 'chat:42',
  kind: 'command',
  who: '@lea',
  what: '/start',
  received_at: '2026-10-05T10:00:00',
  attempts: 0,
  state: 'waiting',
  not_before: null,
  claimed_until: null,
  done_at: null,
  settled_at: null,
  error: null,
  payload: { update_id: 101, message: { text: '/start' } },
  actions: [],
  ...overrides,
});

const page = (items: BotUpdate[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const row = (text: string) => screen.getByText(text).closest('tr') as HTMLElement;

describe('Bot queue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.botQueue).mockResolvedValue(queue);
    vi.mocked(api.botUpdates).mockResolvedValue(
      page([
        update({}),
        update({ update_id: 102, lane: 'post:abc', kind: 'post_button', who: 'Ann (7)', what: 'share_paid:abc', state: 'in_hand', attempts: 1 }),
        update({
          update_id: 103,
          lane: 'payment:9',
          kind: 'payment',
          who: '@dan',
          what: '100 XTR · pro:month:3',
          state: 'failed',
          attempts: 10,
          done_at: '2026-10-05T10:40:00',
          error: "RuntimeError('db gone')",
          actions: ['retry', 'settle'],
        }),
      ]),
    );
  });

  afterEach(() => vi.restoreAllMocks());

  it('says how the queue stands and what each update is, where it stands and what can be done', async () => {
    render(<BotQueue />);

    expect(await screen.findByText('/start')).toBeInTheDocument();
    expect(screen.getByText('самый старый — 4 мин')).toBeInTheDocument();
    expect(screen.getByText('из 4 слотов')).toBeInTheDocument();
    expect(row('/start')).toHaveTextContent('Команда@lea');
    expect(within(row('/start')).getByText('ждёт')).toBeInTheDocument();
    expect(within(row('share_paid:abc')).getByText('в работе')).toBeInTheDocument();
    expect(within(row('100 XTR · pro:month:3')).getByText("RuntimeError('db gone')")).toBeInTheDocument();
    expect(within(row('100 XTR · pro:month:3')).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Повторить',
      'Разобрано',
      'JSON',
    ]);
    expect(within(row('/start')).getAllByRole('button').map((button) => button.textContent)).toEqual(['JSON']);
  });

  it('shows another view and searches by id', async () => {
    render(<BotQueue />);
    await screen.findByText('/start');

    fireEvent.click(screen.getByRole('button', { name: 'Оплаты без Pro' }));
    await waitFor(() => expect(api.botUpdates).toHaveBeenLastCalledWith('payments', '', 1, 50));

    fireEvent.change(screen.getByPlaceholderText('id чата или человека'), { target: { value: ' 42 ' } });
    await waitFor(() => expect(api.botUpdates).toHaveBeenLastCalledWith('payments', '42', 1, 50));
  });

  it('runs a failed payment again or settles it only once the admin agrees', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true);
    vi.mocked(api.retryBotUpdate).mockResolvedValue(update({ update_id: 103 }));
    vi.mocked(api.settleBotUpdate).mockRejectedValue(new Error('Only a payment given up on can be settled'));
    render(<BotQueue />);
    await screen.findByText('/start');
    const payment = row('100 XTR · pro:month:3');

    fireEvent.click(within(payment).getByText('Повторить'));
    expect(api.retryBotUpdate).not.toHaveBeenCalled();

    fireEvent.click(within(payment).getByText('Повторить'));
    await waitFor(() => expect(api.retryBotUpdate).toHaveBeenCalledWith(103));
    expect(confirm.mock.calls[1][0]).toContain('повтор безопасен');

    fireEvent.click(within(row('100 XTR · pro:month:3')).getByText('Разобрано'));
    expect(await screen.findByText('Only a payment given up on can be settled')).toBeInTheDocument();
  });

  it('opens what Telegram sent', async () => {
    render(<BotQueue />);
    await screen.findByText('/start');

    fireEvent.click(within(row('/start')).getByText('JSON'));

    expect(screen.getByText(/"text": "\/start"/)).toBeInTheDocument();
  });
});
