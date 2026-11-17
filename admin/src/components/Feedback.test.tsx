import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { FeedbackRow } from '@/lib/api';
import Feedback from './Feedback';

vi.mock('@/lib/api', () => ({ api: { feedback: vi.fn() } }));

const { api } = await import('@/lib/api');

const row = (overrides: Partial<FeedbackRow>): FeedbackRow => ({
  id: 1,
  message: 'Кнопок слишком много',
  name: null,
  created_at: '2026-09-26T10:00:00',
  user_id: null,
  user: null,
  telegram_id: null,
  ...overrides,
});

describe('feedback tab', () => {
  it('shows each message with who sent it and opens the sender', async () => {
    vi.mocked(api.feedback).mockResolvedValue({
      items: [
        row({ id: 2, message: 'Не понял, куда жать' }),
        row({ id: 1, user_id: 7, user: 'lea', telegram_id: 77, name: 'Лея' }),
      ],
      total: 2,
      limit: 50,
      offset: 0,
    });
    const onOpenUser = vi.fn();

    render(<Feedback onOpenUser={onOpenUser} />);

    expect(await screen.findByText('Не понял, куда жать')).toBeInTheDocument();
    expect(screen.getByText('аноним')).toBeInTheDocument();
    expect(screen.getByText('подписался «Лея»')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'lea' }));
    expect(onOpenUser).toHaveBeenCalledWith(7);
  });
});
