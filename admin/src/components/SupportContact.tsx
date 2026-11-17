'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

/** Whom «Contact support» in the app opens a Telegram chat with. Until one is
 *  set here, and after the field is emptied, it is @splitt_support. */
export default function SupportContact() {
  const [saved, setSaved] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setSaved(settings.support_username);
        setDraft(settings.support_username);
      })
      .catch(console.error);
  }, []);

  const typed = draft.trim().replace(/^@/, '');
  const changed = saved !== undefined && typed !== saved;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const settings = await api.saveSettings({ support_username: typed });
      setSaved(settings.support_username);
      setDraft(settings.support_username);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не сохранилось');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 font-bold">Связаться с поддержкой</h2>
      <p className="mb-3 text-sm text-muted">
        Пункт в настройках приложения открывает чат с этим аккаунтом в Telegram. Если очистить поле, будет @splitt_support.
      </p>
      <form
        className="flex flex-wrap items-center gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (changed) void save();
        }}
      >
        <label htmlFor="support-username" className="text-sm font-medium">
          Username
        </label>
        <div className="flex items-center rounded-md border border-border bg-background">
          <span className="pl-3 text-sm text-muted">@</span>
          <input
            id="support-username"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="split_bill_support"
            spellCheck={false}
            className="w-56 bg-transparent px-1.5 py-1.5 font-mono text-sm outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={!changed || busy}
          className="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-background disabled:opacity-50"
        >
          {busy ? 'Сохраняем…' : 'Сохранить'}
        </button>
        {saved && (
          <a href={`https://t.me/${saved}`} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">
            Открыть чат
          </a>
        )}
      </form>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </section>
  );
}
