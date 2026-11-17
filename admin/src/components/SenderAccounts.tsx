'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { api, type SenderAccount, type SenderAccounts as SenderAccountsData, type SenderLoginCode } from '@/lib/api';
import { formatTashkent, parseUtc } from '@/lib/time';

const STATUS_LABELS: Record<SenderAccount['status'], string> = {
  awaiting_code: 'ждёт код',
  awaiting_password: 'ждёт пароль',
  active: 'в работе',
  resting: 'отдыхает',
  banned: 'забанен',
  disabled: 'выключен',
};

const STATUS_STYLES: Record<SenderAccount['status'], string> = {
  awaiting_code: 'text-muted',
  awaiting_password: 'text-muted',
  active: 'text-success',
  resting: 'text-foreground',
  banned: 'text-danger',
  disabled: 'text-muted',
};

const FIELD = 'rounded-md border border-border bg-background px-2.5 py-1.5 font-mono text-sm outline-none focus:border-accent';
const BUTTON = 'rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-background disabled:opacity-50';

const message = (error: unknown) => (error instanceof Error ? error.message : 'Не получилось');

/**
 * The Telegram accounts that deliver an owner's reminder when the person has
 * blocked the bot. Telegram limits and bans accounts that write to strangers,
 * so they are spent over time; a new one is logged in right here — the number,
 * then the code Telegram sends to it, then the two-step password if it has one.
 */
export default function SenderAccounts() {
  const [data, setData] = useState<SenderAccountsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.senders().then(setData).catch((e) => setError(message(e)));
  }, []);

  useEffect(load, [load]);

  const replace = (account: SenderAccount) =>
    setData((current) => current && {
      ...current,
      accounts: current.accounts.some((row) => row.id === account.id)
        ? current.accounts.map((row) => (row.id === account.id ? account : row))
        : [...current.accounts, account],
    });

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-1 font-bold">Рассыльщики</h2>
        <p className="text-sm text-muted">
          Аккаунты Telegram, которые доставляют напоминание организатора, когда человек заблокировал бота. Он получит
          тот же пост с кнопками — от аккаунта, «через» бота. Telegram быстро ограничивает аккаунты, которые пишут
          незнакомым: такой аккаунт отдыхает или попадает в бан, и его место занимает следующий. Держите в запасе
          несколько.
        </p>
        {data && !data.configured && (
          <p className="mt-3 rounded-md border border-danger px-3 py-2 text-sm text-danger">
            Не заданы TG_API_ID и TG_API_HASH — без приложения с my.telegram.org ни один аккаунт не войдёт.
          </p>
        )}
        {data?.configured && <StartLogin onStarted={replace} />}
      </section>

      {error && <p className="text-sm text-danger">{error}</p>}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2">Аккаунт</th>
                <th className="px-3 py-2">Состояние</th>
                <th className="px-3 py-2 text-right">Отправил</th>
                <th className="px-3 py-2">Последний раз</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {data.accounts.map((account) => (
                <Row key={account.id} account={account} onChange={replace} onRemoved={load} />
              ))}
            </tbody>
          </table>
          {data.accounts.length === 0 && <p className="px-3 py-6 text-center text-muted">Ни одного аккаунта</p>}
        </div>
      )}
    </div>
  );
}

function StartLogin({ onStarted }: { onStarted: (account: SenderAccount) => void }) {
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onStarted(await api.startSenderLogin(phone));
      setPhone('');
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="mt-3 flex flex-wrap items-center gap-3">
      <label htmlFor="sender-phone" className="text-sm font-medium">Номер</label>
      <input
        id="sender-phone"
        value={phone}
        onChange={(event) => setPhone(event.target.value)}
        placeholder="+998 90 123 45 67"
        inputMode="tel"
        className={`${FIELD} w-48`}
      />
      <button type="submit" disabled={busy || phone.trim().length < 7} className={BUTTON}>
        {busy ? 'Отправляем…' : 'Получить код'}
      </button>
      {error && <p className="w-full text-sm text-danger">{error}</p>}
    </form>
  );
}

function Row({ account, onChange, onRemoved }: {
  account: SenderAccount;
  onChange: (account: SenderAccount) => void;
  onRemoved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loggedIn = account.telegram_id !== null;

  const act = async (action: () => Promise<SenderAccount | void>) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await action();
      if (updated) onChange(updated);
      else onRemoved();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = () => {
    if (window.confirm(`Выйти из ${account.phone} и удалить его из списка?`)) {
      void act(() => api.removeSender(account.id));
    }
  };

  return (
    <tr className="border-t border-border align-top">
      <td className="px-3 py-2">
        <div className="font-medium">{account.display_name ?? account.phone}</div>
        {account.display_name && (
          <div className="text-xs text-muted">
            {account.username ? `@${account.username} · ` : ''}
            {account.phone}
          </div>
        )}
      </td>
      <td className="px-3 py-2">
        <div className={STATUS_STYLES[account.status]}>
          {STATUS_LABELS[account.status]}
          {account.status === 'resting' && account.rest_until && ` до ${formatTashkent(account.rest_until)}`}
        </div>
        {account.last_error && <div className="max-w-xs text-xs text-muted-2">{account.last_error}</div>}
        {account.status === 'awaiting_code' && (
          <Step
            label="Код из Telegram"
            submitLabel="Войти"
            busy={busy}
            inputMode="numeric"
            onSubmit={(code) => act(() => api.submitSenderCode(account.id, code))}
          />
        )}
        {account.status === 'awaiting_password' && (
          <Step
            label="Пароль двухэтапной проверки"
            submitLabel="Войти"
            busy={busy}
            secret
            onSubmit={(password) => act(() => api.submitSenderPassword(account.id, password))}
          />
        )}
        {loggedIn && ['active', 'resting', 'disabled'].includes(account.status) && (
          <LoginCode accountId={account.id} />
        )}
        {error && <div className="mt-1 text-xs text-danger">{error}</div>}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{account.sent_count}</td>
      <td className="px-3 py-2 text-muted-2">
        {account.last_used_at ? formatTashkent(account.last_used_at) : '—'}
      </td>
      <td className="px-3 py-2">
        <div className="flex justify-end gap-2">
          {loggedIn && account.status !== 'banned' && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(() => api.setSenderEnabled(account.id, account.status === 'disabled'))}
              className={BUTTON}
            >
              {account.status === 'disabled' ? 'Включить' : 'Выключить'}
            </button>
          )}
          <button type="button" disabled={busy} onClick={remove} className={`${BUTTON} text-danger`}>
            Удалить
          </button>
        </div>
      </td>
    </tr>
  );
}

function LoginCode({ accountId }: { accountId: number }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SenderLoginCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  const trigger = useRef<HTMLButtonElement>(null);

  // Closing the panel or leaving the tab also discards an in-flight result.
  const close = useCallback(() => {
    requestId.current += 1;
    setOpen(false);
    setResult(null);
    setError(null);
    setBusy(false);
  }, []);

  useEffect(() => {
    const hide = () => { if (document.hidden) close(); };
    document.addEventListener('visibilitychange', hide);
    window.addEventListener('pagehide', close);
    return () => {
      requestId.current += 1;
      document.removeEventListener('visibilitychange', hide);
      window.removeEventListener('pagehide', close);
    };
  }, [close]);

  useEffect(() => {
    if (!result?.code || !result.received_at) return;
    const remaining = parseUtc(result.received_at).getTime() + 5 * 60_000 - Date.now();
    const timer = window.setTimeout(() => setResult(null), Math.max(0, Math.min(60_000, remaining)));
    return () => window.clearTimeout(timer);
  }, [result]);

  const check = async () => {
    const id = ++requestId.current;
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const code = await api.senderLoginCode(accountId);
      if (requestId.current === id) setResult(code);
    } catch (e) {
      if (requestId.current === id) setError(message(e));
    } finally {
      if (requestId.current === id) setBusy(false);
    }
  };

  return (
    <div className="mt-2">
      <button
        ref={trigger}
        type="button"
        className={BUTTON}
        aria-expanded={open}
        aria-controls={`sender-login-code-${accountId}`}
        onClick={() => open ? close() : setOpen(true)}
      >
        Код для входа
      </button>
      {open && (
        <div id={`sender-login-code-${accountId}`} className="mt-2 max-w-sm space-y-2 rounded-md border border-border bg-background p-3">
          <p className="text-xs text-muted">
            Запросите вход по этому номеру в приложении Telegram, затем проверьте код здесь.
            Показываем только код из служебного чата за последние 5 минут.
          </p>
          <div role="status" aria-live="polite">
            {busy && <p className="text-xs text-muted">Проверяем Telegram…</p>}
            {result?.code && result.received_at && (
              <>
                <p className="font-mono text-2xl tracking-widest select-all">{result.code}</p>
                <p className="text-xs text-muted">
                  Получен {formatTashkent(result.received_at)}. Скрывается автоматически в течение минуты.
                </p>
              </>
            )}
            {result && !result.code && <p className="text-xs text-muted">Свежего кода пока нет. После запроса входа проверьте ещё раз.</p>}
          </div>
          {error && <p role="alert" className="text-xs text-danger">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} className={BUTTON} onClick={() => void check()}>
              Проверить код
            </button>
            <button type="button" className={BUTTON} onClick={() => { close(); trigger.current?.focus(); }}>Скрыть</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Step({ label, submitLabel, busy, secret = false, inputMode, onSubmit }: {
  label: string;
  submitLabel: string;
  busy: boolean;
  secret?: boolean;
  inputMode?: 'numeric';
  onSubmit: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState('');

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit(value);
      }}
      className="mt-2 flex flex-wrap items-center gap-2"
    >
      <input
        aria-label={label}
        placeholder={label}
        type={secret ? 'password' : 'text'}
        inputMode={inputMode}
        autoComplete="off"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className={`${FIELD} w-56`}
      />
      <button type="submit" disabled={busy || !value.trim()} className={BUTTON}>
        {submitLabel}
      </button>
    </form>
  );
}
