'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

export default function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.login(email, password);
      onSuccess();
    } catch {
      // Deliberately vague: it must not reveal whether the address exists.
      setError('Не удалось войти');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-border bg-surface p-6"
      >
        <h1 className="mb-1 text-lg font-bold">Split The Bill — админка</h1>
        <p className="mb-5 text-sm text-muted">Вход только для оператора.</p>

        <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted">
          Email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
          className="mb-4 w-full rounded-md border border-border bg-background px-3 py-2 outline-none focus:border-accent"
        />

        <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted">
          Пароль
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          className="mb-4 w-full rounded-md border border-border bg-background px-3 py-2 outline-none focus:border-accent"
        />

        {error && <p className="mb-3 text-sm text-danger">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-foreground py-2 font-semibold text-background disabled:opacity-50"
        >
          {busy ? 'Проверяем…' : 'Войти'}
        </button>
      </form>
    </div>
  );
}
