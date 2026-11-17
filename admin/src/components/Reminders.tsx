'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type ReminderRow, type RemindersPage } from '@/lib/api';
import { formatMoney } from '@/lib/money';
import { formatTashkent } from '@/lib/time';
import Pagination from './Pagination';
import Select from './Select';

interface Props {
  onOpenBill: (id: number) => void;
  onOpenUser: (id: number) => void;
}

const PAGE_LIMIT = 50;
const SEARCH_DELAY_MS = 300;

const STATES = [
  { value: '', label: 'Любое состояние' },
  { value: 'scheduled', label: 'Ждёт отправки' },
  { value: 'muted', label: 'Бот заблокирован' },
  { value: 'stopped', label: 'Остановлено' },
];

const STATE_LABELS: Record<string, string> = {
  scheduled: 'ждёт отправки',
  muted: 'бот заблокирован',
  stopped: 'остановлено',
};

const STATE_STYLES: Record<string, string> = {
  scheduled: 'text-foreground',
  muted: 'text-danger',
  stopped: 'text-muted',
};

const EMPTY: RemindersPage = { items: [], total: 0, limit: PAGE_LIMIT, offset: 0, sent_total: 0 };

/**
 * Payment reminders as the scheduler keeps them.
 *
 * There is one row per seat rather than one per message: the job stores where a
 * nudge stands, not a log of what it said, so this screen answers «did anything
 * reach this person, and when» — not «what went out at 15:04».
 */
export default function Reminders({ onOpenBill, onOpenUser }: Props) {
  const [data, setData] = useState<RemindersPage>(EMPTY);
  const [page, setPage] = useState(1);
  const [state, setState] = useState('');
  const [onlySent, setOnlySent] = useState(false);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setTerm(search.trim());
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(() => {
    api
      .reminders({ state, only_sent: onlySent, q: term || undefined }, page, PAGE_LIMIT)
      .then(setData)
      .catch(console.error);
  }, [state, onlySent, term, page]);

  useEffect(load, [load]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          options={STATES}
          value={state}
          onChange={(next) => {
            setState(next);
            setPage(1);
          }}
        />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="@username или telegram id"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
        />
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={onlySent}
            onChange={(e) => {
              setOnlySent(e.target.checked);
              setPage(1);
            }}
          />
          Только те, кому уже отправляли
        </label>
        <span className="ml-auto text-sm text-muted">
          Сообщений отправлено: <span className="tabular-nums">{data.sent_total}</span>
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Кому</th>
              <th className="px-3 py-2">Счёт</th>
              <th className="px-3 py-2 text-right">Долг</th>
              <th className="px-3 py-2">Состояние</th>
              <th className="px-3 py-2 text-right">Отправок</th>
              <th className="px-3 py-2">Последняя</th>
              <th className="px-3 py-2">Следующая</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((reminder) => (
              <Row
                key={reminder.id}
                reminder={reminder}
                onOpenBill={onOpenBill}
                onOpenUser={onOpenUser}
              />
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && (
          <p className="px-3 py-6 text-center text-muted">Напоминаний нет</p>
        )}
        <Pagination
          page={page}
          limit={PAGE_LIMIT}
          total={data.total}
          onPageChange={setPage}
        />
      </div>
    </div>
  );
}

function Row({
  reminder,
  onOpenBill,
  onOpenUser,
}: {
  reminder: ReminderRow;
  onOpenBill: (id: number) => void;
  onOpenUser: (id: number) => void;
}) {
  return (
    <tr className="border-t border-border">
      <td className="px-3 py-2">
        {reminder.user_id === null ? (
          <span className="text-muted">гость</span>
        ) : (
          <button
            onClick={() => onOpenUser(reminder.user_id as number)}
            className="transition-colors hover:text-accent"
          >
            {reminder.username ? `@${reminder.username}` : reminder.telegram_id}
          </button>
        )}
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() => onOpenBill(reminder.bill_id)}
          className="text-left transition-colors hover:text-accent"
        >
          {reminder.bill_title ?? 'без названия'}
          <span className="ml-1 text-xs text-muted-2">#{reminder.bill_id}</span>
        </button>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {formatMoney(reminder.amount, reminder.currency)}
        {reminder.is_paid && <span className="ml-1 text-xs text-muted">оплачен</span>}
      </td>
      <td className={`px-3 py-2 ${STATE_STYLES[reminder.state] ?? ''}`}>
        {STATE_LABELS[reminder.state] ?? reminder.state}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{reminder.sent_count}</td>
      <td className="px-3 py-2 text-muted-2">
        {reminder.last_sent_at ? formatTashkent(reminder.last_sent_at) : 'ещё ни разу'}
      </td>
      <td className="px-3 py-2 text-muted-2">
        {reminder.next_due_at ? formatTashkent(reminder.next_due_at) : '—'}
      </td>
    </tr>
  );
}
