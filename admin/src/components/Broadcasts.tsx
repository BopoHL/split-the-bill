'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type BroadcastFormat, type BroadcastMessage, type BroadcastRow } from '@/lib/api';
import { describeBroadcastError } from '@/lib/broadcastErrors';
import { formatTashkent, tashkentNowInputValue, tashkentToUtcIso } from '@/lib/time';
import BroadcastDetail from './BroadcastDetail';
import BroadcastMediaPicker from './BroadcastMediaPicker';
import BroadcastPreview from './BroadcastPreview';
import BroadcastTestSend from './BroadcastTestSend';
import { richLength, visibleLength } from '@/lib/telegramText';

const LANGS = ['ru', 'en', 'uz'] as const;
type Lang = (typeof LANGS)[number];
// Telegram counts a caption against a quarter of the plain-message allowance,
// so attaching a picture can invalidate a text that was fine on its own.
const CAPTION_LIMIT = 1024;
const TEXT_LIMIT = 4096;
const RICH_TEXT_LIMIT = 32768;
const FORMATS: { value: BroadcastFormat; label: string }[] = [
  { value: 'message', label: 'Обычное' },
  { value: 'rich', label: 'Rich' },
];
const BUTTON_EMOJI = ['\u{1F9FE}', '\u{1F389}', '\u{1F680}', '\u{1F44B}', '\u{2728}', '\u{1F4B8}'];

export default function Broadcasts() {
  const [rows, setRows] = useState<BroadcastRow[]>([]);
  const [title, setTitle] = useState('');
  const [format, setFormat] = useState<BroadcastFormat>('message');
  const [body, setBody] = useState<Record<string, string>>({ ru: '', en: '', uz: '' });
  const [withButton, setWithButton] = useState(true);
  const [buttonText, setButtonText] = useState('');
  const [buttonUrl, setButtonUrl] = useState('');
  const [audience, setAudience] = useState('all');
  const [targets, setTargets] = useState('');
  const [scheduled, setScheduled] = useState(false);
  const [sendAt, setSendAt] = useState('');
  const [tashkentNow, setTashkentNow] = useState(tashkentNowInputValue);
  const [photo, setPhoto] = useState<File | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const editors = useRef<Partial<Record<Lang, HTMLTextAreaElement | null>>>({});
  const lastEdited = useRef<Lang>('ru');

  const rich = format === 'rich';
  const longest = Math.max(0, ...Object.values(body).map(rich ? richLength : visibleLength));
  const limit = rich ? RICH_TEXT_LIMIT : photo ? CAPTION_LIMIT : TEXT_LIMIT;
  const overLimit = longest > limit;
  const empty = !Object.values(body).some((text) => text.trim());

  const message = (): BroadcastMessage => ({
    format,
    body,
    with_button: withButton,
    button_text: buttonText || undefined,
    button_url: buttonUrl || undefined,
  });

  const chooseFormat = (next: BroadcastFormat) => {
    setFormat(next);
    // A rich message carries its pictures inside the text.
    if (next === 'rich') setPhoto(null);
  };

  /** Puts a picture where the cursor was in the text last written in. */
  const insertIntoText = (tag: string) => {
    const lang = lastEdited.current;
    const editor = editors.current[lang];
    const text = body[lang];
    const at = editor ? editor.selectionStart : text.length;
    const before = text.slice(0, at);
    const after = text.slice(editor ? editor.selectionEnd : at);
    setBody({ ...body, [lang]: `${before}${tag}${after}` });
  };

  const load = useCallback(() => {
    api.broadcasts().then(setRows).catch(console.error);
  }, []);

  useEffect(load, [load]);

  // The operator schedules in Tashkent time but may well be sitting in another
  // one, so the current local hour is spelled out instead of assumed.
  useEffect(() => {
    const timer = setInterval(() => setTashkentNow(tashkentNowInputValue()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const create = async (andSend: boolean) => {
    setBusy(true);
    setError('');
    try {
      const created = await api.createBroadcast({
        ...message(),
        title,
        audience,
        targets: audience === 'selected'
          ? targets.split(/[\s,]+/).filter(Boolean)
          : undefined,
        scheduled_at: scheduled && sendAt ? tashkentToUtcIso(sendAt) : undefined,
      });
      try {
        if (photo && !rich) await api.attachBroadcastPhoto(created.id, photo);
        if (andSend) await api.sendBroadcast(created.id);
      } catch (err) {
        // The draft is already saved; leaving it would pile up half-made copies
        // every time the operator fixes the photo and presses again.
        await api.deleteBroadcast(created.id).catch(() => {});
        throw err;
      }
      setTitle('');
      setFormat('message');
      setBody({ ru: '', en: '', uz: '' });
      setButtonText('');
      setButtonUrl('');
      setTargets('');
      setScheduled(false);
      setSendAt('');
      setPhoto(null);
      load();
    } catch (err) {
      setError(describeBroadcastError(err));
    } finally {
      setBusy(false);
    }
  };

  if (openId !== null) {
    return <BroadcastDetail id={openId} onClose={() => setOpenId(null)} />;
  }

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_360px]">
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Рассылка</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2 text-right">Доставлено</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-border">
                <td className="px-3 py-2">
                  <button
                    onClick={() => setOpenId(row.id)}
                    className="text-left transition-colors hover:text-accent"
                  >
                    <div className="font-medium">
                      {row.title}
                      {row.has_photo && <span className="ml-1.5 text-muted-2">фото</span>}
                      {row.format === 'rich' && <span className="ml-1.5 text-muted-2">rich</span>}
                    </div>
                    <div className="truncate text-xs text-muted-2">{row.body.ru}</div>
                  </button>
                </td>
                <td className="px-3 py-2">
                  {row.status}
                  {row.scheduled_at && row.status !== 'done' && (
                    <div className="text-xs text-muted-2">
                      {formatTashkent(row.scheduled_at)}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {row.sent_count}/{row.total_count}
                  {row.failed_count > 0 && (
                    <span className="ml-1 text-danger">·{row.failed_count}</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  {row.status === 'draft' && (
                    <span className="flex justify-end gap-1">
                      <button
                        onClick={() => api.sendBroadcast(row.id).then(load)}
                        className="rounded border border-border px-2 py-1 text-xs hover:border-accent hover:text-accent"
                      >
                        Отправить
                      </button>
                      <button
                        onClick={() => api.deleteBroadcast(row.id).then(load)}
                        className="rounded border border-border px-2 py-1 text-xs hover:border-danger hover:text-danger"
                      >
                        Удалить
                      </button>
                    </span>
                  )}
                  {(row.status === 'queued' || row.status === 'sending') && (
                    <button
                      onClick={() => api.cancelBroadcast(row.id).then(load)}
                      className="rounded border border-border px-2 py-1 text-xs hover:border-danger hover:text-danger"
                    >
                      Отменить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="px-3 py-6 text-center text-muted">Пока пусто</p>}
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 font-bold">Новая рассылка</h2>

        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Заголовок (для себя)"
          className="mb-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
        />

        <div className="mb-1 flex gap-1 rounded-md border border-border p-0.5" role="radiogroup" aria-label="Формат">
          {FORMATS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={format === value}
              onClick={() => chooseFormat(value)}
              className={`flex-1 rounded px-2 py-1 text-sm transition-colors ${
                format === value ? 'bg-foreground text-background' : 'text-muted hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mb-3 text-xs text-muted-2">
          {rich
            ? 'Заголовки, списки, таблицы и картинки посреди текста. Telegram Web, приложение для macOS и версии старше середины 2026 покажут «сообщение не поддерживается».'
            : 'Текст или фото с подписью — видно везде.'}
        </p>

        {LANGS.map((lang) => (
          <div key={lang} className="mb-3">
            <label
              htmlFor={`broadcast-body-${lang}`}
              className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted"
            >
              Текст · {lang}
            </label>
            <textarea
              id={`broadcast-body-${lang}`}
              ref={(element) => {
                editors.current[lang] = element;
              }}
              value={body[lang]}
              onChange={(e) => setBody({ ...body, [lang]: e.target.value })}
              onFocus={() => {
                lastEdited.current = lang;
              }}
              rows={rich ? 8 : 3}
              placeholder={rich ? '<h2>Заголовок</h2>\n<p>Абзац</p>' : undefined}
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm outline-none focus:border-accent"
            />
          </div>
        ))}

        {rich ? (
          <BroadcastMediaPicker onInsert={insertIntoText} />
        ) : (
          <>
            <label
              htmlFor="broadcast-photo"
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
            >
              Фотография
            </label>
            <input
              id="broadcast-photo"
              type="file"
              accept="image/*"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
              className="mb-1 w-full text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-sm"
            />
          </>
        )}
        <p className={`mb-3 text-xs ${overLimit ? 'text-danger' : 'text-muted-2'}`}>
          {longest}/{limit} символов
          {photo && overLimit && ' — с фотографией столько не отправить'}
        </p>

        {!empty && (
          <BroadcastPreview
            format={format}
            body={body}
            languages={LANGS}
            photo={photo}
            buttonText={withButton ? buttonText || 'Открыть' : null}
          />
        )}

        {/* The button is what the message is for: something to tap. */}
        <label className="mb-2 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={withButton}
            onChange={(e) => setWithButton(e.target.checked)}
          />
          Кнопка под сообщением
        </label>
        {withButton && (
          <div className="mb-3 grid grid-cols-2 gap-2">
            <div>
              <input
                value={buttonText}
                onChange={(e) => setButtonText(e.target.value)}
                placeholder="Открыть"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <div className="mt-1 flex gap-1">
                {BUTTON_EMOJI.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    onClick={() => setButtonText((text) => `${emoji} ${text || 'Открыть'}`)}
                    className="rounded border border-border px-1.5 py-0.5 text-sm leading-none transition-colors hover:border-accent"
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
            <input
              value={buttonUrl}
              onChange={(e) => setButtonUrl(e.target.value)}
              placeholder="ссылка на бота"
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </div>
        )}

        <select
          value={audience}
          onChange={(e) => setAudience(e.target.value)}
          className="mb-4 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="all">Все, кому бот может писать</option>
          <option value="active_30d">Активные за 30 дней</option>
          <option value="selected">Выбранным</option>
        </select>

        {audience === 'selected' && (
          <textarea
            value={targets}
            onChange={(e) => setTargets(e.target.value)}
            rows={2}
            placeholder="@username или telegram id, через запятую"
            className="mb-4 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
          />
        )}

        <label className="mb-2 flex items-center gap-2 text-sm">
          <input
            type="radio"
            checked={!scheduled}
            onChange={() => setScheduled(false)}
          />
          Отправить как можно скорее
        </label>
        <label className="mb-2 flex items-center gap-2 text-sm">
          <input type="radio" checked={scheduled} onChange={() => setScheduled(true)} />
          В назначенное время
        </label>
        {scheduled && (
          <div className="mb-4">
            <input
              type="datetime-local"
              value={sendAt}
              min={tashkentNow}
              onChange={(e) => setSendAt(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <p className="mt-1 text-xs text-muted-2">
              Время ташкентское. Сейчас там {tashkentNow.slice(11)}.
            </p>
          </div>
        )}

        <BroadcastTestSend message={message} photo={rich ? null : photo} disabled={empty || overLimit} />

        {error && <p className="mb-3 text-sm text-danger">{error}</p>}

        <div className="flex gap-2">
          <button
            disabled={busy || !title.trim() || overLimit}
            onClick={() => create(false)}
            className="flex-1 rounded-md border border-border py-2 text-sm font-semibold disabled:opacity-50"
          >
            Сохранить
          </button>
          <button
            disabled={busy || !title.trim() || overLimit || (scheduled && !sendAt)}
            onClick={() => create(true)}
            className="flex-1 rounded-md bg-foreground py-2 text-sm font-semibold text-background disabled:opacity-50"
          >
            {scheduled ? 'Запланировать' : 'Отправить'}
          </button>
        </div>
      </div>
    </div>
  );
}
