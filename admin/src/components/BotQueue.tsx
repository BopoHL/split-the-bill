'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  api,
  type BotQueue as Queue,
  type BotUpdate,
  type BotUpdateAction,
  type BotUpdateKind,
  type BotUpdateState,
  type BotUpdateView,
  type Page,
} from '@/lib/api';
import { formatTashkent, parseUtc } from '@/lib/time';
import Pagination from './Pagination';

const PAGE_LIMIT = 50;
const POLL_MS = 5000;
const SEARCH_DELAY_MS = 300;

const VIEWS: { value: BotUpdateView; label: string }[] = [
  { value: 'queue', label: 'Очередь' },
  { value: 'failed', label: 'Ошибки' },
  { value: 'payments', label: 'Оплаты без Pro' },
  { value: 'all', label: 'Все' },
];

const EMPTY_TEXT: Record<BotUpdateView, string> = {
  queue: 'Очередь пуста — бот успевает за всеми',
  failed: 'Ошибок нет',
  payments: 'Все оплаты дошли до Pro',
  all: 'За неделю апдейтов не было',
};

const KIND_LABELS: Record<BotUpdateKind, string> = {
  command: 'Команда',
  message: 'Сообщение',
  photo: 'Фото',
  button: 'Кнопка',
  post_button: 'Кнопка под постом',
  shared_post: 'Пост в чате',
  membership: 'Доступ к боту',
  payment: 'Оплата',
  other: 'Другое',
};

const STATE_LABELS: Record<BotUpdateState, string> = {
  waiting: 'ждёт',
  in_hand: 'в работе',
  retry_later: 'повтор',
  handled: 'обработан',
  failed: 'не обработан',
  settled: 'разобран вручную',
};

const STATE_STYLES: Record<BotUpdateState, string> = {
  waiting: 'text-muted',
  in_hand: 'font-medium text-foreground',
  retry_later: 'text-foreground',
  handled: 'text-success',
  failed: 'text-danger',
  settled: 'text-muted',
};

const ACTION_LABELS: Record<BotUpdateAction, string> = { retry: 'Повторить', settle: 'Разобрано' };

const BUTTON =
  'whitespace-nowrap rounded-md border border-border px-2.5 py-1 text-xs transition-colors hover:bg-background disabled:opacity-50';

const EMPTY: Page<BotUpdate> = { items: [], total: 0, limit: PAGE_LIMIT, offset: 0 };

/**
 * Telegram's updates on their way through the bot: the webhook keeps them and
 * the bot's worker handles them in the background — one at a time per chat or
 * post, several chats at once. What waits, what is in hand, what failed, and
 * the payments that never became Pro.
 */
export default function BotQueue() {
  const [queue, setQueue] = useState<Queue | null>(null);
  const [data, setData] = useState<Page<BotUpdate>>(EMPTY);
  const [view, setView] = useState<BotUpdateView>('queue');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setTerm(search.trim());
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(() => {
    api.botQueue().then(setQueue).catch(console.error);
    api.botUpdates(view, term, page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [view, term, page]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const act = async (update: BotUpdate, action: BotUpdateAction) => {
    if (!window.confirm(confirmation(update, action))) return;
    setBusy(true);
    setError(null);
    try {
      await (action === 'retry' ? api.retryBotUpdate(update.update_id) : api.settleBotUpdate(update.update_id));
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не получилось');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mb-1 font-bold">Очередь бота</h2>
        <p className="text-sm text-muted">
          Вебхук сохраняет апдейты Telegram, воркер бота обрабатывает их в фоне: в одном чате и под одним постом — по
          одному и по порядку, разные чаты — одновременно.
        </p>
      </div>

      {queue && <Summary queue={queue} />}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {VIEWS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={view === item.value}
              onClick={() => {
                setView(item.value);
                setPage(1);
                setOpen(null);
              }}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                view === item.value ? 'bg-foreground text-background' : 'text-muted hover:bg-surface hover:text-foreground'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="id чата или человека"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
        />
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-2.5 py-2">№</th>
              <th className="px-2.5 py-2">Получен</th>
              <th className="px-2.5 py-2">Что</th>
              <th className="px-2.5 py-2">Дорожка</th>
              <th className="px-2.5 py-2 text-right">Попытки</th>
              <th className="px-2.5 py-2">Статус</th>
              <th className="px-2.5 py-2" />
            </tr>
          </thead>
          <tbody>
            {data.items.map((update) => (
              <UpdateRow
                key={update.update_id}
                update={update}
                open={open === update.update_id}
                busy={busy}
                onToggle={() => setOpen(open === update.update_id ? null : update.update_id)}
                onAct={(action) => void act(update, action)}
              />
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && <p className="px-3 py-6 text-center text-muted">{EMPTY_TEXT[view]}</p>}
        {data.total > PAGE_LIMIT && (
          <Pagination page={page} limit={PAGE_LIMIT} total={data.total} onPageChange={setPage} />
        )}
      </div>
    </div>
  );
}

function Summary({ queue }: { queue: Queue }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <Metric
        label="Ждут"
        value={queue.waiting}
        hint={queue.oldest_waiting_at ? `самый старый — ${age(queue.oldest_waiting_at)}` : 'никто'}
      />
      <Metric label="В работе" value={queue.in_hand} hint={`из ${queue.slots} слотов`} />
      <Metric label="Повтор позже" value={queue.retrying} hint="оплаты после ошибки" />
      <Metric label="За час" value={queue.handled_last_hour} hint="обработано" />
      <Metric label="Ошибок за сутки" value={queue.failed_last_day} alarm={queue.failed_last_day > 0} />
      <Metric
        label="Оплаты без Pro"
        value={queue.unsettled_payments}
        hint="звёзды списаны, Pro не выдан"
        alarm={queue.unsettled_payments > 0}
      />
    </div>
  );
}

function Metric({ label, value, hint, alarm = false }: { label: string; value: number; hint?: string; alarm?: boolean }) {
  return (
    <div className={`rounded-lg border bg-surface p-3 ${alarm ? 'border-danger' : 'border-border'}`}>
      <div className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${alarm ? 'text-danger' : ''}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-2">{hint}</div>}
    </div>
  );
}

function UpdateRow({
  update,
  open,
  busy,
  onToggle,
  onAct,
}: {
  update: BotUpdate;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onAct: (action: BotUpdateAction) => void;
}) {
  const note = stateNote(update);
  return (
    <>
      <tr className="border-t border-border align-top">
        <td className="px-2.5 py-2 font-mono text-xs text-muted">{update.update_id}</td>
        <td className="whitespace-nowrap px-2.5 py-2 text-muted-2">{formatTashkent(update.received_at)}</td>
        <td className="px-2.5 py-2">
          <span className="font-medium">{KIND_LABELS[update.kind]}</span>
          {update.who && <span className="ml-1.5 text-muted">{update.who}</span>}
          {update.what && <span className="block break-all text-xs text-muted-2">{update.what}</span>}
        </td>
        <td className="px-2.5 py-2 font-mono text-xs text-muted">{update.lane}</td>
        <td className="px-2.5 py-2 text-right tabular-nums">{update.attempts}</td>
        <td className="px-2.5 py-2">
          <span className={STATE_STYLES[update.state]}>{STATE_LABELS[update.state]}</span>
          {note && <span className="block text-xs text-muted">{note}</span>}
          {update.error && (
            <span title={update.error} className="block max-w-xs truncate text-xs text-danger">
              {update.error}
            </span>
          )}
        </td>
        <td className="px-2.5 py-2">
          <div className="flex flex-wrap justify-end gap-1.5">
            {update.actions.map((action) => (
              <button key={action} type="button" disabled={busy} onClick={() => onAct(action)} className={BUTTON}>
                {ACTION_LABELS[action]}
              </button>
            ))}
            <button type="button" aria-expanded={open} onClick={onToggle} className={BUTTON}>
              JSON
            </button>
          </div>
        </td>
      </tr>
      {open && (
        <tr className="border-t border-border bg-background">
          <td colSpan={7} className="px-2.5 py-2">
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all font-mono text-xs">
              {JSON.stringify(update.payload, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

function stateNote(update: BotUpdate): string | null {
  if (update.state === 'retry_later' && update.not_before) return `в ${formatTashkent(update.not_before)}`;
  if (update.state === 'handled' && update.done_at) return formatTashkent(update.done_at);
  if (update.state === 'settled' && update.settled_at) return formatTashkent(update.settled_at);
  return null;
}

function confirmation(update: BotUpdate, action: BotUpdateAction): string {
  if (action === 'settle') {
    return `Отметить оплату №${update.update_id} разобранной? Сделайте это, когда звёзды вернули или Pro выдали вручную.`;
  }
  if (update.kind === 'payment') {
    return `Обработать оплату №${update.update_id} снова? Pro по одному платежу выдаётся один раз — повтор безопасен.`;
  }
  return `Обработать апдейт №${update.update_id} снова? Если в первый раз бот успел что-то отправить, человек может получить это ещё раз.`;
}

/** How long ago, roughly: «сейчас», «4 мин», «2 ч 5 мин», «3 дн». */
function age(value: string): string {
  const minutes = Math.floor((Date.now() - parseUtc(value).getTime()) / 60_000);
  if (minutes < 1) return 'сейчас';
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? `${hours} ч ${minutes % 60} мин` : `${hours} ч`;
  return `${Math.floor(hours / 24)} дн`;
}
