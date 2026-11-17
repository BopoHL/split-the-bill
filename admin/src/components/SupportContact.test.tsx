import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SupportContact from './SupportContact';

vi.mock('@/lib/api', () => ({ api: { settings: vi.fn(), saveSettings: vi.fn() } }));

const { api } = await import('@/lib/api');

const settings = (support_username: string) => ({
  scan_mode: 'ocr_llm' as const,
  receipt_model: 'gpt-6-luna',
  label_model: 'gpt-6-luna',
  support_username,
});

describe('support contact', () => {
  it('saves the username without its @', async () => {
    vi.mocked(api.settings).mockResolvedValue(settings('splitt_support'));
    vi.mocked(api.saveSettings).mockResolvedValue(settings('split_help'));
    render(<SupportContact />);

    const field = await screen.findByLabelText('Username');
    await waitFor(() => expect(field).toHaveValue('splitt_support'));
    fireEvent.change(field, { target: { value: '@split_help' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ support_username: 'split_help' }));
    expect(await screen.findByRole('link', { name: 'Открыть чат' })).toHaveAttribute('href', 'https://t.me/split_help');
  });

  it('shows why a username was refused', async () => {
    vi.mocked(api.settings).mockResolvedValue(settings('split_help'));
    vi.mocked(api.saveSettings).mockRejectedValue(new Error('Not a Telegram username'));
    render(<SupportContact />);

    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'no spaces' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    expect(await screen.findByText('Not a Telegram username')).toBeInTheDocument();
  });
});
