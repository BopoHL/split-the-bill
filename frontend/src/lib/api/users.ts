import apiClient from './client';
import type { User, UserSettings } from '@/types/api';
import type { StartKind } from '@/lib/utils/startParam';

/** How this open came in; the server keeps it as the person's first touch
 *  when the call is what makes the account. */
export interface FirstTouch {
  start: StartKind;
  source: string | null;
}

/**
 * Merge the given preferences into the user's stored settings (autosave).
 */
export async function updateUserSettings(
  userId: number,
  settings: UserSettings,
): Promise<User> {
  const response = await apiClient.patch<User>(
    `/users/${userId}/settings`,
    settings,
  );
  return response.data;
}

/**
 * Server-owned reachability sync from Telegram's write-access signal.
 */
export async function syncTelegramWriteAccess(
  userId: number,
  allowsWriteToPm: boolean,
): Promise<User> {
  const response = await apiClient.patch<User>(
    `/users/${userId}/write-access`,
    { allows_write_to_pm: allowsWriteToPm },
  );
  return response.data;
}

/**
 * Get user by Telegram ID (creates/updates if not exists)
 */
export async function getUserByTelegramId(
  telegramId: number,
  username?: string,
  avatarUrl?: string,
  initData?: string,
  /** Who brought them, when this call is what creates the account. */
  inviteCode?: string | null,
  allowsWriteToPm?: boolean,
  firstTouch?: FirstTouch,
): Promise<User | null> {
  try {
    const response = await apiClient.post<User>('/users/', {
      telegram_id: telegramId,
      username: username,
      avatar_url: avatarUrl,
      init_data: initData,
      invite_code: inviteCode ?? null,
      allows_write_to_pm: allowsWriteToPm,
      start: firstTouch?.start,
      source: firstTouch?.source,
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching/syncing user by Telegram ID:', error);
    return null;
  }
}
