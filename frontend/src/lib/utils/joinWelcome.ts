import type { UserSettings } from '@/types/api';

/**
 * The welcome DM is one-time; write-access prompts are handled globally on app
 * open because reachability matters outside invite joins too.
 */
export function shouldSendJoinWelcome(settings?: UserSettings | null): boolean {
  return settings?.welcome_sent !== true;
}

export function shouldRequestTelegramWriteAccess(allowsWriteToPm: boolean): boolean {
  return !allowsWriteToPm;
}
