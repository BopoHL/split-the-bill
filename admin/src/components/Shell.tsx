'use client';

import { useEffect, useState } from 'react';
import { api, Unauthorized } from '@/lib/api';
import LoginForm from './LoginForm';

const TABS = [
  { key: 'dashboard', label: 'Дашборд' },
  { key: 'bills', label: 'Счета' },
  { key: 'users', label: 'Пользователи' },
  { key: 'scans', label: 'Сканы' },
  { key: 'broadcasts', label: 'Рассылки' },
  { key: 'scan-modes', label: 'Распознавание' },
  { key: 'catalog', label: 'Места и блюда' },
  { key: 'reminders', label: 'Напоминания' },
  { key: 'pro', label: 'Pro' },
  { key: 'subscriptions', label: 'Подписки' },
  { key: 'senders', label: 'Рассыльщики' },
  { key: 'bot-queue', label: 'Очередь бота' },
  { key: 'support', label: 'Поддержка' },
] as const;

export type Tab = (typeof TABS)[number]['key'];

interface ShellProps {
  tab: Tab;
  onTabChange: (tab: Tab) => void;
  children: React.ReactNode;
}

/**
 * Auth gate plus navigation.
 *
 * The panel is a static export, so there is no server to redirect on an expired
 * session — the shell asks the API who it is and shows the login form when the
 * answer is 401.
 */
export default function Shell({ tab, onTabChange, children }: ShellProps) {
  const [email, setEmail] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  const check = () =>
    api
      .me()
      .then((me) => setEmail(me.email))
      .catch((err) => {
        if (!(err instanceof Unauthorized)) console.error(err);
        setEmail(null);
      })
      .finally(() => setChecking(false));

  useEffect(() => {
    void check();
    const signedOut = () => setEmail(null);
    window.addEventListener('admin:unauthorized', signedOut);
    return () => window.removeEventListener('admin:unauthorized', signedOut);
  }, []);

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted">Загрузка…</div>
    );
  }

  if (!email) return <LoginForm onSuccess={check} />;

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <header className="mb-6 flex items-center gap-4 border-b border-border pb-4">
        <span className="text-lg font-bold tracking-tight">
          SPLIT<span className="text-accent">·</span>BILL
        </span>
        <nav className="flex min-w-0 flex-wrap gap-1">
          {TABS.map((item) => (
            <button
              key={item.key}
              onClick={() => onTabChange(item.key)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === item.key
                  ? 'bg-foreground text-background'
                  : 'text-muted hover:bg-surface hover:text-foreground'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm text-muted">
          <span className="whitespace-nowrap">{email}</span>
          <button
            onClick={() => api.logout().then(check)}
            className="rounded-md border border-border px-2.5 py-1 transition-colors hover:border-danger hover:text-danger"
          >
            Выйти
          </button>
        </div>
      </header>
      {children}
    </div>
  );
}
