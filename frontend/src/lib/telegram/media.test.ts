import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from '@/types/telegram';

/** A fresh module per case: init caches the WebApp it saw first. */
async function setup({ supported = true, story = vi.fn(), download = vi.fn() } = {}) {
  const wa = {
    platform: 'ios',
    initData: 'user=test',
    isVersionAtLeast: vi.fn(() => supported),
    shareToStory: story,
    downloadFile: download,
    ready: vi.fn(),
    expand: vi.fn(),
    themeParams: {},
  };
  window.Telegram = { WebApp: wa as unknown as TelegramWebApp };
  vi.resetModules();
  return { media: await import('./media'), wa };
}

afterEach(() => {
  delete (window as { Telegram?: unknown }).Telegram;
});

describe('pictures out of the app', () => {
  it('opens the story editor and saves a file on a client that has both', async () => {
    const { media, wa } = await setup();

    expect(media.shareToStory('https://x.test/a.jpg', { text: 'My 2026' })).toBe(true);
    expect(media.downloadFile('https://x.test/a.jpg?download=true', 'a.jpg')).toBe(true);

    expect(wa.shareToStory).toHaveBeenCalledWith('https://x.test/a.jpg', { text: 'My 2026' });
    expect(wa.downloadFile).toHaveBeenCalledWith({ url: 'https://x.test/a.jpg?download=true', file_name: 'a.jpg' });
  });

  it('calls neither on a client too old for them', async () => {
    const { media, wa } = await setup({ supported: false });

    expect(media.canShareToStory()).toBe(false);
    expect(media.shareToStory('https://x.test/a.jpg')).toBe(false);
    expect(media.downloadFile('https://x.test/a.jpg', 'a.jpg')).toBe(false);
    expect(wa.shareToStory).not.toHaveBeenCalled();
    expect(wa.downloadFile).not.toHaveBeenCalled();
  });

  it('says so when the client refuses', async () => {
    const refuse = () => {
      throw new Error('WebAppMethodUnsupported');
    };
    const { media } = await setup({ story: vi.fn(refuse), download: vi.fn(refuse) });

    expect(media.shareToStory('https://x.test/a.jpg')).toBe(false);
    expect(media.downloadFile('https://x.test/a.jpg', 'a.jpg')).toBe(false);
  });
});
