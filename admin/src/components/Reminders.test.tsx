import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReminderRow, RemindersPage } from '@/lib/api';
import Reminders from './Reminders';

vi.mock('@/lib/api', () => ({ api: { reminders: vi.fn() } }));

const { api } = await import('@/lib/api');

function page(items: Partial<ReminderRow>[]): RemindersPage {
  return {
    items: items.map((item, index) => ({
      id: index + 1,
      bill_id: 5,
      bill_title: 'Ужин',
      bill_status: 'open',
      currency: 'uzs',
      participant_id: 9,
      user_id: 3,
      username: 'bob',
      telegram_id: 42,
      amount: 120000,
      is_paid: false,
      state: 'scheduled',
      sent_count: 0,
      last_sent_at: null,
      next_due_at: null,
      muted_at: null,
      created_at: '2026-08-19T10:00:00',
      ...item,
    })) as ReminderRow[],
    total: items.length,
    limit: 50,
    offset: 0,
    sent_total: items.reduce((sum, item) => sum + (item.sent_count ?? 0), 0),
  };
}

describe('reminders tab', () => {
  it('says plainly when nothing has been sent yet', async () => {
    vi.mocked(api.reminders).mockResolvedValue(page([{ sent_count: 0 }]));

    render(<Reminders onOpenBill={() => {}} onOpenUser={() => {}} />);

    expect(await screen.findByText('ещё ни разу')).toBeInTheDocument();
    expect(screen.getByText('ждёт отправки')).toBeInTheDocument();
  });

  it('shows how many messages actually went out', async () => {
    vi.mocked(api.reminders).mockResolvedValue(
      page([{ sent_count: 2, last_sent_at: '2026-08-19T10:00:00', state: 'muted' }]),
    );

    render(<Reminders onOpenBill={() => {}} onOpenUser={() => {}} />);

    await waitFor(() => expect(screen.getByText(/Сообщений отправлено/)).toBeInTheDocument());
    expect(screen.getByText('бот заблокирован')).toBeInTheDocument();
    expect(screen.getByText('19.08, 15:00')).toBeInTheDocument();
  });
});
