import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const api = vi.hoisted(() => ({ getAnalyticsPictures: vi.fn() }));
const media = vi.hoisted(() => ({
  canShareToStory: vi.fn(() => true),
  shareToStory: vi.fn(() => true),
  canDownloadFile: vi.fn(() => false),
  downloadFile: vi.fn(() => true),
}));
const analytics = vi.hoisted(() => ({ track: vi.fn(), setAnalyticsContext: vi.fn(), setPersonProperties: vi.fn(), AnalyticsEvent: { ShareAnalytics: 'share_analytics' } }));
vi.mock('@/lib/api/analytics', () => api);
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

import YearStories from './YearStories';

const url = (story: string) => `https://split.example/api/public/analytics/1/${story}.jpg?sig=${story}`;

beforeEach(() => {
  vi.clearAllMocks();
  api.getAnalyticsPictures.mockResolvedValue({
    receipt: url('receipt'),
    stories: ['bills', 'dish', 'person'].map((story) => ({ story, url: url(story) })),
    story_text: 'Мои итоги 2026 в Split·Bill https://t.me/bot/app',
  });
});

describe('YearStories', () => {
  it('asks for the year only once it is opened', async () => {
    const { rerender } = render(<YearStories userId={1} year={2026} open={false} onClose={() => {}} />);
    expect(api.getAnalyticsPictures).not.toHaveBeenCalled();

    rerender(<YearStories userId={1} year={2026} open onClose={() => {}} />);

    expect(await screen.findByRole('img', { name: 'Счета за год' })).toBeInTheDocument();
    expect(api.getAnalyticsPictures).toHaveBeenCalledWith(1, { kind: 'year', year: 2026 });
  });

  it('goes from story to story and shares the one on screen', async () => {
    const user = userEvent.setup();
    render(<YearStories userId={1} year={2026} open onClose={() => {}} />);
    await screen.findByRole('img', { name: 'Счета за год' });

    await user.click(screen.getByRole('button', { name: 'Следующая история' }));
    expect(screen.getByRole('img', { name: 'Блюдо года' })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Счета за год' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Поделиться в истории' }));

    expect(media.shareToStory).toHaveBeenCalledWith(url('dish'), { text: 'Мои итоги 2026 в Split·Bill https://t.me/bot/app' });
    expect(analytics.track).toHaveBeenCalledWith('share_analytics', { picture: 'dish', method: 'story' });
  });

  it('closes on Escape', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<YearStories userId={1} year={2026} open onClose={onClose} />);
    await screen.findByRole('img', { name: 'Счета за год' });

    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalled();
  });
});
