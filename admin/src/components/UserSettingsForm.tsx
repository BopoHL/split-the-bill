'use client';

import { useState } from 'react';
import { api, type UserDetail, type UserSettingsChange } from '@/lib/api';
import Select from './Select';

const UNSET = '';

const LANGUAGES = [
  { value: UNSET, label: 'не выбран' },
  { value: 'ru', label: 'Русский' },
  { value: 'uz', label: "O'zbekcha" },
  { value: 'en', label: 'English' },
];

const THEMES = [
  { value: UNSET, label: 'как в Telegram' },
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Тёмная' },
  { value: 'nord', label: 'Nord (Pro)' },
  { value: 'nord_frost', label: 'Nord Frost (Pro)' },
  { value: 'sakura', label: 'Сакура (Pro)' },
  { value: 'midnight', label: 'Полночь (Pro)' },
];

// Mirrors the currencies a bill can be in (backend/app/utils/currency.py).
const CURRENCIES = ['uzs', 'usd', 'eur', 'rub', 'byn', 'kzt', 'kgs', 'tjs', 'tmt', 'gbp', 'try', 'aed', 'uah', 'gel', 'azn', 'cny'];
const CURRENCY_OPTIONS = [
  { value: UNSET, label: 'по умолчанию' },
  ...CURRENCIES.map((code) => ({ value: code, label: code.toUpperCase() })),
];

const FLAGS = [
  { key: 'onboarding_completed', label: 'Онбординг пройден', hint: 'Снять — и при следующем входе он снова увидит выбор языка и тур.' },
  { key: 'welcome_sent', label: 'Приветствие от бота отправлено', hint: 'Снять — и бот пришлёт приветствие ещё раз.' },
  { key: 'bot_blocked', label: 'Бот заблокирован', hint: 'Рассылки его пропускают. Снимается само, когда бот снова может писать.' },
  { key: 'internal', label: 'Свой аккаунт', hint: 'Команда или тест: продуктовая аналитика его не считает.' },
] as const;

type Flag = (typeof FLAGS)[number]['key'];

interface Draft {
  language: string;
  theme: string;
  currency: string;
  flags: Record<Flag, boolean>;
}

const text = (value: unknown) => (typeof value === 'string' ? value : UNSET);

function draftOf(settings: Record<string, unknown>): Draft {
  return {
    language: text(settings.language),
    theme: text(settings.theme),
    currency: text(settings.currency),
    flags: {
      onboarding_completed: settings.onboarding_completed === true,
      welcome_sent: settings.welcome_sent === true,
      bot_blocked: settings.bot_blocked === true,
      internal: settings.internal === true,
    },
  };
}

/** Only what differs from what is stored goes out; an emptied field takes the key out. */
function changeOf(stored: Draft, draft: Draft): UserSettingsChange {
  const change: UserSettingsChange = {};
  if (draft.language !== stored.language) change.language = (draft.language || null) as UserSettingsChange['language'];
  if (draft.theme !== stored.theme) change.theme = (draft.theme || null) as UserSettingsChange['theme'];
  if (draft.currency !== stored.currency) change.currency = draft.currency || null;
  for (const { key } of FLAGS) {
    if (draft.flags[key] !== stored.flags[key]) change[key] = draft.flags[key];
  }
  return change;
}

/** Someone's settings, changed by hand — for replaying the tour for them or
 *  putting a language right. The raw JSON stays one click away. */
export default function UserSettingsForm({ user, onSaved }: { user: UserDetail; onSaved: (user: UserDetail) => void }) {
  const stored = draftOf(user.settings);
  const [draft, setDraft] = useState(stored);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const change = changeOf(stored, draft);
  const dirty = Object.keys(change).length > 0;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveUserSettings(user.id, change);
      setDraft(draftOf(saved.settings));
      onSaved(saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не сохранилось');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Настройки</h3>
      <div className="space-y-3 text-sm">
        <Row label="Язык">
          <Select options={LANGUAGES} value={draft.language} onChange={(language) => setDraft({ ...draft, language })} />
        </Row>
        <Row label="Тема">
          <Select options={THEMES} value={draft.theme} onChange={(theme) => setDraft({ ...draft, theme })} />
        </Row>
        <Row label="Валюта">
          <Select options={CURRENCY_OPTIONS} value={draft.currency} onChange={(currency) => setDraft({ ...draft, currency })} />
        </Row>
        {FLAGS.map(({ key, label, hint }) => (
          <label key={key} className="flex items-start gap-2.5">
            <input
              type="checkbox"
              checked={draft.flags[key]}
              onChange={(event) => setDraft({ ...draft, flags: { ...draft.flags, [key]: event.target.checked } })}
              className="mt-0.5 h-4 w-4 shrink-0"
            />
            <span>
              {label}
              <span className="block text-xs text-muted-2">{hint}</span>
            </span>
          </label>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!dirty || busy}
          className="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-background disabled:opacity-50"
        >
          {busy ? 'Сохраняем…' : 'Сохранить'}
        </button>
        {dirty && !busy && (
          <button type="button" onClick={() => setDraft(stored)} className="text-sm text-muted hover:text-foreground">
            Отменить
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-muted">Как хранится</summary>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
          {JSON.stringify(user.settings, null, 2)}
        </pre>
      </details>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted">{label}</span>
      {children}
    </div>
  );
}
