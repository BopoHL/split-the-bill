/**
 * The panel's words for what the API refused in a broadcast.
 *
 * A refusal with a code arrives as the whole JSON body (see `request`), the
 * rest as the API's own sentence.
 */
export function describeBroadcastError(err: unknown): string {
  const raw = err instanceof Error ? err.message : '';
  let detail: Record<string, unknown> | undefined;
  try {
    detail = JSON.parse(raw)?.detail;
  } catch {
    return raw || 'Ошибка';
  }
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return 'Ошибка';

  switch (detail.code) {
    case 'UNKNOWN_RECIPIENTS':
      return `Не нашлись: ${(detail.targets as string[]).join(', ')}`;
    case 'BAD_HTML':
      return `Разметка (${detail.language}): ${detail.message}`;
    case 'CAPTION_TOO_LONG':
      return `С фотографией подпись не длиннее ${detail.limit} символов, а сейчас ${detail.length}`;
    case 'TEXT_TOO_LONG':
      return `Текст (${detail.language}) длиннее ${detail.limit} символов: ${detail.length}`;
    case 'TELEGRAM_REFUSED': {
      const sent = detail.sent as string[];
      const already = sent.length ? ` Уже ушло: ${sent.join(', ')}.` : '';
      return `Telegram не принял (${detail.language}): ${detail.message}.${already}`;
    }
    default:
      return typeof detail.message === 'string' ? detail.message : 'Ошибка';
  }
}
