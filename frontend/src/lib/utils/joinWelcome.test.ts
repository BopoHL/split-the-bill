import { describe, expect, it } from 'vitest';

import {
  shouldRequestTelegramWriteAccess,
  shouldSendJoinWelcome,
} from './joinWelcome';

describe('shouldSendJoinWelcome', () => {
  it('sends on the first invite join before the welcome DM was sent', () => {
    expect(shouldSendJoinWelcome({})).toBe(true);
    expect(shouldSendJoinWelcome({ welcome_sent: false })).toBe(true);
  });

  it('does not send again after the welcome DM', () => {
    expect(shouldSendJoinWelcome({ welcome_sent: true })).toBe(false);
    expect(
      shouldSendJoinWelcome({ welcome_sent: true, bot_blocked: false })
    ).toBe(false);
    expect(
      shouldSendJoinWelcome({ welcome_sent: true, bot_blocked: true })
    ).toBe(false);
  });
});

describe('shouldRequestTelegramWriteAccess', () => {
  it('skips the native prompt only when Telegram says write access is allowed', () => {
    expect(shouldRequestTelegramWriteAccess(true)).toBe(false);
    expect(shouldRequestTelegramWriteAccess(false)).toBe(true);
  });
});
