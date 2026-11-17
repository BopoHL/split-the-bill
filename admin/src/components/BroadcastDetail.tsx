'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  api,
  type BroadcastDetail as Detail,
  type BroadcastRecipient,
  type Page,
} from '@/lib/api';
import { formatTashkent } from '@/lib/time';
import Pagination from './Pagination';
import Select from './Select';

const DELIVERY_LABELS: Record<string, string> = {
  pending: 'в очереди',
  sent: 'доставлено',
  failed: 'ошибка',
  blocked: 'бот заблокирован',
};

const DELIVERY_FILTERS = [
  { value: '', label: 'Любой исход' },
  { value: 'sent', label: 'Доставлено' },
  { value: 'failed', label: 'Ошибка' },
  { value: 'blocked', label: 'Бот заблокирован' },
  { value: 'pending', label: 'В очереди' },
];

const PAGE_LIMIT = 50;
const SEARCH_DELAY_MS = 300;

const AUDIENCE_LABELS: Record<string, string> = {
  all: 'Все, кому бот может писать',
  active_30d: 'Активные за 30 дней',
  selected: 'Выбранные получатели',
};

interface Props {
  id: number;
  onClose: () => void;
}

/** What a broadcast actually was: the text as sent, and who it reached. */
export default function BroadcastDetail({ id, onClose }: Props) {
  const [detail, setDetail] = useState<Detail | null>(null);

  useEffect(() => {
    api.broadcast(id).then(setDetail).catch(console.error);
  }, [id]);

  if (!detail) return <p className="py-10 text-center text-muted">Загрузка…</p>;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <button
          onClick={onClose}
          className="rounded-md border border-border px-2.5 py-1 text-sm text-muted transition-colors hover:text-foreground"
        >
          ← Назад
        </button>
        <h2 className="text-lg font-bold">{detail.title}</h2>
        <span className="rounded-md bg-surface px-2 py-0.5 text-xs text-muted">
          {detail.status}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border border-border bg-surface p-4 text-sm md:grid-cols-5">
        <Fact label="Создана" value={formatTashkent(detail.created_at)} />
        <Fact label="Формат" value={detail.format === 'rich' ? 'Rich-сообщение' : 'Обычное'} />
        <Fact
          label="Отправка"
          value={detail.scheduled_at ? formatTashkent(detail.scheduled_at) : 'сразу'}
        />
        <Fact label="Аудитория" value={AUDIENCE_LABELS[detail.audience] ?? detail.audience} />
        <Fact
          label="Доставлено"
          value={`${detail.sent_count} из ${detail.total_count}${
            detail.failed_count ? ` · ошибок ${detail.failed_count}` : ''
          }`}
        />
      </dl>

      {detail.target_usernames.length > 0 && (
        <p className="text-sm text-muted">
          Получатели: {detail.target_usernames.map((name) => `@${name}`).join(', ')}
        </p>
      )}

      <div className="space-y-3">
        {Object.entries(detail.body).map(([lang, text]) =>
          text ? (
            <div key={lang} className="rounded-lg border border-border p-4">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
                {lang}
              </div>
              {/* The stored body is the HTML that went to Telegram, shown as
                  written rather than rendered — the point is to see the tags. */}
              <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                {text}
              </pre>
            </div>
          ) : null,
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm text-muted">
        {detail.button_text && (
          <span>
            Кнопка: <span className="text-foreground">{detail.button_text}</span> →{' '}
            {detail.button_url}
          </span>
        )}
        {detail.has_photo && <span>С фотографией</span>}
      </div>

      <Deliveries broadcastId={id} />
    </div>
  );
}

/**
 * Who the broadcast reached, one row per recipient.
 *
 * Paged and filtered on the server: the list can run to tens of thousands, and
 * what an operator opens it for is the handful that failed.
 */
function Deliveries({ broadcastId }: { broadcastId: number }) {
  const [data, setData] = useState<Page<BroadcastRecipient>>({
    items: [],
    total: 0,
    limit: PAGE_LIMIT,
    offset: 0,
  });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
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
      .broadcastDeliveries(broadcastId, { status, q: term || undefined }, page, PAGE_LIMIT)
      .then(setData)
      .catch(console.error);
  }, [broadcastId, status, term, page]);

  useEffect(load, [load]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          options={DELIVERY_FILTERS}
          value={status}
          onChange={(next) => {
            setStatus(next);
            setPage(1);
          }}
        />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="@username или telegram id"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
        />
        <span className="ml-auto text-sm text-muted">
          Получателей: <span className="tabular-nums">{data.total}</span>
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Получатель</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2">Когда</th>
              <th className="px-3 py-2">Ошибка</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((recipient) => (
              <tr key={recipient.user_id} className="border-t border-border">
                <td className="px-3 py-2">
                  {recipient.username ? `@${recipient.username}` : recipient.telegram_id}
                </td>
                <td className="px-3 py-2">
                  {DELIVERY_LABELS[recipient.status] ?? recipient.status}
                </td>
                <td className="px-3 py-2 text-muted-2">
                  {recipient.sent_at ? formatTashkent(recipient.sent_at) : '—'}
                </td>
                <td className="px-3 py-2 text-danger">{recipient.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && (
          <p className="px-3 py-6 text-center text-muted">Получателей ещё нет</p>
        )}
        <Pagination page={page} limit={PAGE_LIMIT} total={data.total} onPageChange={setPage} />
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}
