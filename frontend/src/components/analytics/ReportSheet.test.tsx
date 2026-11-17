import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const api = vi.hoisted(() => ({ getAnalyticsPictures: vi.fn(), prepareAnalyticsShare: vi.fn() }));
const share = vi.hoisted(() => ({ canShareMessage: vi.fn(() => true), shareMessage: vi.fn(() => true) }));
const media = vi.hoisted(() => ({ canDownloadFile: vi.fn(() => true), downloadFile: vi.fn(() => true) }));
const analytics = vi.hoisted(() => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: { ShareAnalytics: 'share_analytics' } }));
vi.mock('@/lib/api/analytics', () => api);
vi.mock('@/lib/telegram/share', () => share);
vi.mock('@/lib/telegram/media', () => media);
vi.mock('@/lib/analytics', () => analytics);
vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'ru', currentUser: { id: 1 } };
  const useStore = Object.assign(
    (selector?: (s: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useStore };
});

import ReportSheet from './ReportSheet';

const SEPTEMBER = { kind: 'month' as const, year: 2026, month: 9 };
const RECEIPT = 'https://split.example/api/public/analytics/1/receipt.jpg?period=month&sig=abc';

beforeEach(() => {
  vi.clearAllMocks();
  api.getAnalyticsPictures.mockResolvedValue({ receipt: RECEIPT, stories: [], story_text: null });
  api.prepareAnalyticsShare.mockResolvedValue('prepared-1');
});

describe('ReportSheet', () => {
  it('asks for the receipt only once it is opened', async () => {
    const { rerender } = render(<ReportSheet userId={1} period={SEPTEMBER} open={false} onClose={() => {}} />);
    expect(api.getAnalyticsPictures).not.toHaveBeenCalled();

    rerender(<ReportSheet userId={1} period={SEPTEMBER} open onClose={() => {}} />);

    expect(await screen.findByRole('img', { name: 'Отчёт-чек: сент 2026' })).toHaveAttribute('src', RECEIPT);
    expect(api.getAnalyticsPictures).toHaveBeenCalledWith(1, SEPTEMBER);
  });

  it('sends the receipt to a chat as a photo', async () => {
    const user = userEvent.setup();
    render(<ReportSheet userId={1} period={SEPTEMBER} open onClose={() => {}} />);
    await screen.findByRole('img');

    await user.click(screen.getByRole('button', { name: 'Отправить в чат' }));

    await waitFor(() => expect(share.shareMessage).toHaveBeenCalledWith('prepared-1'));
    expect(api.prepareAnalyticsShare).toHaveBeenCalledWith(1, SEPTEMBER);
    expect(analytics.track).toHaveBeenCalledWith('share_analytics', { picture: 'receipt', method: 'message' });
  });

  it('saves the receipt as a file', async () => {
    const user = userEvent.setup();
    render(<ReportSheet userId={1} period={SEPTEMBER} open onClose={() => {}} />);
    await screen.findByRole('img');

    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    expect(media.downloadFile).toHaveBeenCalledWith(`${RECEIPT}&download=true`, 'split-bill-report.jpg');
  });

  it('offers the picture itself where Telegram can do neither', async () => {
    share.canShareMessage.mockReturnValue(false);
    media.canDownloadFile.mockReturnValue(false);
    render(<ReportSheet userId={1} period={SEPTEMBER} open onClose={() => {}} />);

    expect(await screen.findByRole('link', { name: 'Открыть картинку' })).toHaveAttribute('href', RECEIPT);
    expect(screen.queryByRole('button', { name: 'Отправить в чат' })).not.toBeInTheDocument();
  });
});
