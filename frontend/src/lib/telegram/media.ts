import type { TelegramStoryParams } from '@/types/telegram';
import { getTelegramWebApp, supportsApi } from './init';

/**
 * Pictures out of the app: into Telegram's story editor, or saved to the
 * device. Both take the picture by its HTTPS address — the client fetches it.
 */

export function canShareToStory(): boolean {
  const wa = getTelegramWebApp();
  return !!wa && typeof wa.shareToStory === 'function' && supportsApi('7.8');
}

/** Open the story editor on the picture. Returns false when the client can't. */
export function shareToStory(url: string, params?: TelegramStoryParams): boolean {
  const wa = getTelegramWebApp();
  if (!wa?.shareToStory || !canShareToStory()) return false;
  try {
    wa.shareToStory(url, params);
    return true;
  } catch (error) {
    console.warn('shareToStory failed', error);
    return false;
  }
}

export function canDownloadFile(): boolean {
  const wa = getTelegramWebApp();
  return !!wa && typeof wa.downloadFile === 'function' && supportsApi('8.0');
}

/**
 * Ask Telegram to save the file; it asks the person first. Returns false when
 * the client can't.
 */
export function downloadFile(url: string, fileName: string): boolean {
  const wa = getTelegramWebApp();
  if (!wa?.downloadFile || !canDownloadFile()) return false;
  try {
    wa.downloadFile({ url, file_name: fileName });
    return true;
  } catch (error) {
    console.warn('downloadFile failed', error);
    return false;
  }
}
