import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { SenderAccount } from '@/lib/api';
import SenderAccounts from './SenderAccounts';

vi.mock('@/lib/api', () => ({
  api: {
    senders: vi.fn(),
    startSenderLogin: vi.fn(),
    submitSenderCode: vi.fn(),
    senderLoginCode: vi.fn(),
    submitSenderPassword: vi.fn(),
    setSenderEnabled: vi.fn(),
    removeSender: vi.fn(),
  },
}));

const { api } = await import('@/lib/api');

const account = (overrides: Partial<SenderAccount> = {}): SenderAccount => ({
  id: 1,
  phone: '+998901234567',
  telegram_id: null,
  username: null,
  display_name: null,
  status: 'awaiting_code',
  rest_until: null,
  last_error: null,
  last_used_at: null,
  sent_count: 0,
  created_at: '2026-10-01T10:00:00',
  ...overrides,
});

const loggedIn = (overrides: Partial<SenderAccount> = {}) =>
  account({ telegram_id: 777, username: 'sender_one', display_name: 'Sender One', status: 'active', ...overrides });

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.useRealTimers());

describe('sender accounts', () => {
  it('logs an account in with the code and then the two-step password', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [] });
    vi.mocked(api.startSenderLogin).mockResolvedValue(account());
    vi.mocked(api.submitSenderCode).mockResolvedValue(account({ status: 'awaiting_password' }));
    vi.mocked(api.submitSenderPassword).mockResolvedValue(loggedIn());
    render(<SenderAccounts />);

    fireEvent.change(await screen.findByLabelText('Номер'), { target: { value: '+998 90 123 45 67' } });
    fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
    await waitFor(() => expect(api.startSenderLogin).toHaveBeenCalledWith('+998 90 123 45 67'));

    fireEvent.change(await screen.findByLabelText('Код из Telegram'), { target: { value: '12345' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
    await waitFor(() => expect(api.submitSenderCode).toHaveBeenCalledWith(1, '12345'));

    fireEvent.change(await screen.findByLabelText('Пароль двухэтапной проверки'), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByText('в работе')).toBeInTheDocument();
    expect(screen.getByText('Sender One')).toBeInTheDocument();
    expect(api.submitSenderPassword).toHaveBeenCalledWith(1, 'pw');
  });

  it('says why a step was refused', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [account()] });
    vi.mocked(api.submitSenderCode).mockRejectedValue(new Error('Wrong code'));
    render(<SenderAccounts />);

    fireEvent.change(await screen.findByLabelText('Код из Telegram'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByText('Wrong code')).toBeInTheDocument();
  });

  it('shows how each account is doing and turns one off', async () => {
    vi.mocked(api.senders).mockResolvedValue({
      configured: true,
      accounts: [
        loggedIn({ sent_count: 12 }),
        loggedIn({ id: 2, phone: '+998900000002', status: 'banned', last_error: 'UserDeactivatedBanError' }),
      ],
    });
    vi.mocked(api.setSenderEnabled).mockResolvedValue(loggedIn({ status: 'disabled' }));
    render(<SenderAccounts />);

    expect(await screen.findByText('забанен')).toBeInTheDocument();
    expect(screen.getByText('UserDeactivatedBanError')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Выключить' })).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Выключить' }));

    await waitFor(() => expect(api.setSenderEnabled).toHaveBeenCalledWith(1, false));
    expect(await screen.findByRole('button', { name: 'Включить' })).toBeInTheDocument();
  });

  it('warns that nothing can log in without the Telegram app credentials', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: false, accounts: [] });
    render(<SenderAccounts />);

    expect(await screen.findByText(/Не заданы TG_API_ID и TG_API_HASH/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Номер')).toBeNull();
  });

  it('shows a fresh code only on request and hides it after a minute', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [loggedIn()] });
    vi.mocked(api.senderLoginCode).mockResolvedValue({ code: '54321', received_at: new Date().toISOString() });
    render(<SenderAccounts />);
    fireEvent.click(await screen.findByRole('button', { name: 'Код для входа' }));
    expect(api.senderLoginCode).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Проверить код' }));
    expect(await screen.findByText('54321')).toBeInTheDocument();
    expect(api.senderLoginCode).toHaveBeenCalledWith(1);

    vi.useFakeTimers();
    // A second fetch installs its automatic hide timer under the fake clock.
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Проверить код' })));
    act(() => vi.advanceTimersByTime(60_000));
    expect(screen.queryByText('54321')).toBeNull();
  });

  it('handles an absent code and lets the operator check again', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [loggedIn({ status: 'disabled' })] });
    vi.mocked(api.senderLoginCode)
      .mockResolvedValueOnce({ code: null, received_at: null })
      .mockResolvedValueOnce({ code: '54321', received_at: new Date().toISOString() });
    render(<SenderAccounts />);
    fireEvent.click(await screen.findByRole('button', { name: 'Код для входа' }));
    fireEvent.click(screen.getByRole('button', { name: 'Проверить код' }));
    expect(await screen.findByText(/Свежего кода пока нет/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Проверить код' }));
    expect(await screen.findByText('54321')).toBeInTheDocument();
  });

  it('reports a revoked session without changing or removing the account', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [loggedIn()] });
    vi.mocked(api.senderLoginCode).mockRejectedValue(new Error('Сессия Telegram больше не действительна'));
    render(<SenderAccounts />);
    fireEvent.click(await screen.findByRole('button', { name: 'Код для входа' }));
    fireEvent.click(screen.getByRole('button', { name: 'Проверить код' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Сессия Telegram больше не действительна');
    expect(screen.getByText('в работе')).toBeInTheDocument();
    expect(api.removeSender).not.toHaveBeenCalled();
  });

  it('discards a request completed after the code panel was closed', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [loggedIn()] });
    let resolve!: (value: { code: string; received_at: string }) => void;
    vi.mocked(api.senderLoginCode).mockImplementation(() => new Promise((done) => { resolve = done; }));
    render(<SenderAccounts />);
    fireEvent.click(await screen.findByRole('button', { name: 'Код для входа' }));
    fireEvent.click(screen.getByRole('button', { name: 'Проверить код' }));
    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }));
    await act(async () => resolve({ code: '54321', received_at: new Date().toISOString() }));
    fireEvent.click(screen.getByRole('button', { name: 'Код для входа' }));
    expect(screen.queryByText('54321')).toBeNull();
  });

  it('clears a displayed code when leaving the page', async () => {
    vi.mocked(api.senders).mockResolvedValue({ configured: true, accounts: [loggedIn()] });
    vi.mocked(api.senderLoginCode).mockResolvedValue({ code: '54321', received_at: new Date().toISOString() });
    render(<SenderAccounts />);
    fireEvent.click(await screen.findByRole('button', { name: 'Код для входа' }));
    fireEvent.click(screen.getByRole('button', { name: 'Проверить код' }));
    expect(await screen.findByText('54321')).toBeInTheDocument();
    fireEvent(window, new Event('pagehide'));
    expect(screen.queryByText('54321')).toBeNull();
  });
});
