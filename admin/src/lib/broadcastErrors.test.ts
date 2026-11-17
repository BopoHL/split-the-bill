import { describe, expect, it } from 'vitest';

import { describeBroadcastError } from './broadcastErrors';

const refusal = (detail: unknown) => new Error(JSON.stringify({ detail }));

describe('describeBroadcastError', () => {
  it('names the language Telegram refused and what already went out', () => {
    const err = refusal({
      code: 'TELEGRAM_REFUSED',
      language: 'en',
      sent: ['ru'],
      message: "Telegram error: Bad Request: can't parse rich message",
    });

    expect(describeBroadcastError(err)).toBe(
      "Telegram не принял (en): Telegram error: Bad Request: can't parse rich message. Уже ушло: ru.",
    );
  });

  it('spells out a rich text over its limit', () => {
    const err = refusal({ code: 'TEXT_TOO_LONG', language: 'uz', limit: 32768, length: 40000 });

    expect(describeBroadcastError(err)).toBe('Текст (uz) длиннее 32768 символов: 40000');
  });

  it('passes the API sentence through', () => {
    expect(describeBroadcastError(new Error('No recipients selected'))).toBe('No recipients selected');
    expect(describeBroadcastError(refusal({ code: 'NO_PUBLIC_BASE_URL', message: 'PUBLIC_BASE_URL не задан' }))).toBe(
      'PUBLIC_BASE_URL не задан',
    );
  });
});
