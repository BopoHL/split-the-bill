import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { BroadcastRow } from '@/lib/api';
import Broadcasts from './Broadcasts';

vi.mock('@/lib/api', () => ({
  api: {
    broadcasts: vi.fn(),
    createBroadcast: vi.fn(),
    attachBroadcastPhoto: vi.fn(),
    sendBroadcast: vi.fn(),
    cancelBroadcast: vi.fn(),
    deleteBroadcast: vi.fn(),
    testBroadcast: vi.fn(),
    uploadBroadcastMedia: vi.fn(),
  },
}));

const { api } = await import('@/lib/api');

const PICTURE = 'https://split-the-bill.uz/api/broadcasts/media/0123456789abcdef0123456789abcdef.jpg';

const row = (overrides: Partial<BroadcastRow> = {}): BroadcastRow => ({
  id: 1,
  title: '1.0',
  format: 'rich',
  body: { ru: '<p>x</p>' },
  parse_mode: 'HTML',
  button_text: 'Открыть',
  button_url: 'https://t.me/bot/app',
  audience: 'all',
  target_user_ids: [],
  scheduled_at: null,
  has_photo: false,
  status: 'draft',
  total_count: 0,
  sent_count: 0,
  failed_count: 0,
  created_at: '2026-10-05T10:00:00',
  ...overrides,
});

const text = (lang: string) => screen.getByLabelText(`Текст · ${lang}`) as HTMLTextAreaElement;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.broadcasts).mockResolvedValue([]);
});

describe('broadcasts', () => {
  it('writes a rich message: no attached photo, pictures go into the text', async () => {
    vi.mocked(api.uploadBroadcastMedia).mockResolvedValue({ url: PICTURE });
    render(<Broadcasts />);

    fireEvent.click(screen.getByRole('radio', { name: 'Rich' }));
    expect(screen.queryByLabelText('Фотография')).not.toBeInTheDocument();

    fireEvent.change(text('uz'), { target: { value: '<p>Salom</p><p>Pro</p>' } });
    fireEvent.focus(text('uz'));
    text('uz').setSelectionRange('<p>Salom</p>'.length, '<p>Salom</p>'.length);

    const file = new File(['png'], 'compare.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Картинки в тексте'), { target: { files: [file] } });
    await waitFor(() => expect(api.uploadBroadcastMedia).toHaveBeenCalledWith(file));
    fireEvent.click(await screen.findByRole('button', { name: 'Вставить' }));

    expect(text('uz').value).toBe(`<p>Salom</p><img src="${PICTURE}"/><p>Pro</p>`);
  });

  it('creates a rich broadcast as rich and attaches nothing', async () => {
    vi.mocked(api.createBroadcast).mockResolvedValue(row());
    vi.mocked(api.sendBroadcast).mockResolvedValue(row({ status: 'queued' }));
    render(<Broadcasts />);

    fireEvent.change(screen.getByPlaceholderText('Заголовок (для себя)'), { target: { value: '1.0' } });
    fireEvent.click(screen.getByRole('radio', { name: 'Rich' }));
    fireEvent.change(text('ru'), { target: { value: '<h2>1.0</h2><p>Новое</p>' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    await waitFor(() => expect(api.sendBroadcast).toHaveBeenCalledWith(1));
    expect(vi.mocked(api.createBroadcast).mock.calls[0][0]).toMatchObject({
      format: 'rich',
      body: { ru: '<h2>1.0</h2><p>Новое</p>', en: '', uz: '' },
    });
    expect(api.attachBroadcastPhoto).not.toHaveBeenCalled();
  });

  it('previews the language picked', async () => {
    render(<Broadcasts />);
    await waitFor(() => expect(api.broadcasts).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('radio', { name: 'Rich' }));
    fireEvent.change(text('ru'), { target: { value: '<p>Привет</p>' } });
    fireEvent.change(text('en'), { target: { value: '<p>Hello</p>' } });
    fireEvent.click(screen.getByRole('tab', { name: 'en' }));

    const preview = screen.getByTitle('Превью рассылки');
    expect(preview.getAttribute('srcdoc')).toContain('<div class="rich"><p>Hello</p></div>');
    expect(preview.getAttribute('sandbox')).toBe('allow-same-origin');
  });

  it('sends the draft to the operator and remembers who that is', async () => {
    vi.mocked(api.testBroadcast).mockResolvedValue({ sent: ['ru'] });
    render(<Broadcasts />);

    fireEvent.click(screen.getByRole('radio', { name: 'Rich' }));
    fireEvent.change(text('ru'), { target: { value: '<p>Привет</p>' } });
    fireEvent.change(screen.getByLabelText('Проверить на себе'), { target: { value: '@boss' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить себе' }));

    expect(await screen.findByText('Отправлено: ru')).toBeInTheDocument();
    expect(api.testBroadcast).toHaveBeenCalledWith(
      expect.objectContaining({ format: 'rich', body: { ru: '<p>Привет</p>', en: '', uz: '' }, with_button: true }),
      '@boss',
      null,
    );
    expect(localStorage.getItem('broadcast-test-target')).toBe('@boss');
  });

  it('shows what Telegram refused in a test send', async () => {
    vi.mocked(api.testBroadcast).mockRejectedValue(
      new Error(
        JSON.stringify({
          detail: { code: 'TELEGRAM_REFUSED', language: 'ru', sent: [], message: 'Bad Request: unsupported tag' },
        }),
      ),
    );
    localStorage.setItem('broadcast-test-target', '@boss');
    render(<Broadcasts />);

    fireEvent.change(text('ru'), { target: { value: 'Привет' } });
    expect(screen.getByLabelText('Проверить на себе')).toHaveValue('@boss');
    fireEvent.click(screen.getByRole('button', { name: 'Отправить себе' }));

    expect(await screen.findByText('Telegram не принял (ru): Bad Request: unsupported tag.')).toBeInTheDocument();
  });
});
