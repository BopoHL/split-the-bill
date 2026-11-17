import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Labeling as LabelingStatus } from '@/lib/api';
import Labeling from './Labeling';

vi.mock('@/lib/api', () => ({
  api: {
    labeling: vi.fn(),
    saveSettings: vi.fn(),
    startLabelingHistory: vi.fn(),
    pauseLabelingHistory: vi.fn(),
  },
}));

const { api } = await import('@/lib/api');

const status = (overrides: Partial<LabelingStatus> = {}): LabelingStatus => ({
  key_set: true,
  model: 'gpt-6-luna',
  since: '2026-10-05T10:00:00',
  last_labeled_at: null,
  last_error: null,
  last_error_at: null,
  history: null,
  ...overrides,
});

describe('Labeling', () => {
  beforeEach(() => vi.clearAllMocks());

  it('starts the history only when asked, and shows how far it got', async () => {
    vi.mocked(api.labeling).mockResolvedValueOnce(status()).mockResolvedValue(
      status({
        history: {
          state: 'running',
          started_at: '2026-10-05T10:01:00',
          finished_at: null,
          lines_done: 1200,
          lines_total: 5000,
          bills_done: 30,
          bills_total: 300,
        },
      }),
    );
    vi.mocked(api.startLabelingHistory).mockResolvedValue(status());
    render(<Labeling />);

    fireEvent.click(await screen.findByText('Разметить историю'));

    await waitFor(() => expect(api.startLabelingHistory).toHaveBeenCalled());
    expect(await screen.findByText('Остановить')).toBeInTheDocument();
    expect(screen.getByText('1 200 / 5 000')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Счета' })).toHaveAttribute('aria-valuenow', '30');
  });

  it('says why nothing is labeled, and does not offer the history then', async () => {
    vi.mocked(api.labeling).mockResolvedValue(status({ key_set: false }));
    render(<Labeling />);

    expect(await screen.findByText('OPENAI_API_KEY не задан — разметка стоит.')).toBeInTheDocument();
    expect(screen.getByText('Разметить историю')).toBeDisabled();
  });

  it('shows the last error and resumes a paused run', async () => {
    vi.mocked(api.labeling).mockResolvedValue(
      status({
        last_error: 'The model `gpt-x` does not exist',
        last_error_at: '2026-10-05T10:02:00',
        history: {
          state: 'paused',
          started_at: '2026-10-05T10:01:00',
          finished_at: null,
          lines_done: 10,
          lines_total: 20,
          bills_done: 0,
          bills_total: 5,
        },
      }),
    );
    vi.mocked(api.startLabelingHistory).mockResolvedValue(status());
    render(<Labeling />);

    expect(await screen.findByText(/The model `gpt-x` does not exist/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Продолжить'));
    await waitFor(() => expect(api.startLabelingHistory).toHaveBeenCalled());
  });

  it('saves another model for labeling', async () => {
    vi.mocked(api.labeling).mockResolvedValue(status());
    vi.mocked(api.saveSettings).mockResolvedValue({
      scan_mode: 'ocr_llm',
      receipt_model: 'gpt-6-luna',
      label_model: 'gpt-5.6-luna',
      support_username: 'splitt_support',
    });
    render(<Labeling />);

    fireEvent.change(await screen.findByLabelText('Модель'), { target: { value: 'gpt-5.6-luna' } });
    fireEvent.click(screen.getByText('Сохранить'));

    await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ label_model: 'gpt-5.6-luna' }));
  });
});
