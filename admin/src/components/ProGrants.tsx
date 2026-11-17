'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  api,
  type Page,
  type ProGrant,
  type ProGrantAction,
  type ProGrantFilters,
  type ProGrantState,
  type ProPlan,
  type ProSource,
} from '@/lib/api';
import { formatTashkent, formatTashkentDay } from '@/lib/time';
import Pagination from './Pagination';
import Select from './Select';

const PAGE_LIMIT = 50;
const SEARCH_DELAY_MS = 300;

const SOURCES = [
  { value: '', label: 'Все виды' },
  { value: 'purchase', label: 'Покупки' },
  { value: 'subscription', label: 'Подписки' },
  { value: 'promo', label: 'Промокоды' },
  { value: 'trial', label: 'Пробные' },
];

const PLAN_LABELS: Record<ProPlan, string> = { month: 'месяц', half_year: '6 месяцев', year: 'год' };

const STATE_LABELS: Record<ProGrantState, string> = {
  active: 'действует',
  upcoming: 'впереди',
  ended: 'закончился',
  revoked: 'забран',
  refunded: 'звёзды возвращены',
};

const STATE_STYLES: Record<ProGrantState, string> = {
  active: 'text-success',
  upcoming: 'text-foreground',
  ended: 'text-muted',
  revoked: 'text-danger',
  refunded: 'text-danger',
};

const ACTION_LABELS: Record<ProGrantAction, string> = {
  stop_renewal: 'Остановить продление',
  allow_renewal: 'Разрешить продление',
  revoke: 'Забрать Pro',
  refund: 'Вернуть звёзды',
};

// Least drastic first.
const ACTION_ORDER: ProGrantAction[] = ['stop_renewal', 'allow_renewal', 'revoke', 'refund'];

const BUTTON =
  'whitespace-nowrap rounded-md border border-border px-2.5 py-1 text-xs transition-colors hover:bg-background disabled:opacity-50';

const EMPTY: Page<ProGrant> = { items: [], total: 0, limit: PAGE_LIMIT, offset: 0 };

/**
 * Every stretch of Pro: bought, renewed by a subscription, from a promo code or
 * a trial — whose, since when, for how long — and taking one back. Given a
 * `userId`, only that person's, without the search.
 */
export default function ProGrants({ userId, onOpenUser }: { userId?: number; onOpenUser?: (id: number) => void }) {
  const [data, setData] = useState<Page<ProGrant>>(EMPTY);
  const [page, setPage] = useState(1);
  const [source, setSource] = useState('');
  const [running, setRunning] = useState(false);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setTerm(search.trim());
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(() => {
    const filters: ProGrantFilters = userId
      ? { user_id: userId }
      : { source: (source || undefined) as ProSource | undefined, running, q: term || undefined };
    api.proGrants(filters, page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [userId, source, running, term, page]);

  useEffect(load, [load]);

  const act = async (grant: ProGrant, action: ProGrantAction) => {
    if (action !== 'allow_renewal' && !window.confirm(confirmation(grant, action))) return;
    setBusy(grant.id);
    setError(null);
    try {
      await perform(grant, action);
      // Taking a grant back moves the ones queued after it, so the whole page is asked again.
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не получилось');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      {!userId && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Select
            options={SOURCES}
            value={source}
            onChange={(next) => {
              setSource(next);
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
              checked={running}
              onChange={(e) => {
                setRunning(e.target.checked);
                setPage(1);
              }}
            />
            Только действующие и впереди
          </label>
        </div>
      )}
      {error && <p className="mb-2 text-sm text-danger">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              {!userId && <th className="px-2.5 py-2">Кто</th>}
              <th className="px-2.5 py-2">Что</th>
              <th className="px-2.5 py-2 text-right">Звёзды</th>
              <th className="px-2.5 py-2">Выдан</th>
              <th className="px-2.5 py-2">Pro с — по</th>
              <th className="px-2.5 py-2">Статус</th>
              <th className="px-2.5 py-2" />
            </tr>
          </thead>
          <tbody>
            {data.items.map((grant) => (
              <GrantRow
                key={grant.id}
                grant={grant}
                withPerson={!userId}
                busy={busy !== null}
                onOpenUser={onOpenUser}
                onAct={(action) => void act(grant, action)}
              />
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && <p className="px-3 py-6 text-center text-muted">Pro никому не выдавался</p>}
        {data.total > PAGE_LIMIT && (
          <Pagination page={page} limit={PAGE_LIMIT} total={data.total} onPageChange={setPage} />
        )}
      </div>
    </div>
  );
}

function GrantRow({
  grant,
  withPerson,
  busy,
  onOpenUser,
  onAct,
}: {
  grant: ProGrant;
  withPerson: boolean;
  busy: boolean;
  onOpenUser?: (id: number) => void;
  onAct: (action: ProGrantAction) => void;
}) {
  const note = renewal(grant);
  return (
    <tr className="border-t border-border align-top">
      {withPerson && (
        <td className="px-2.5 py-2">
          <button onClick={() => onOpenUser?.(grant.user.id)} className="text-left transition-colors hover:text-accent">
            {who(grant)}
          </button>
        </td>
      )}
      <td className="px-2.5 py-2">
        {kind(grant)}
        {grant.days !== null && <span className="ml-1 whitespace-nowrap text-xs text-muted-2">{grant.days} дн.</span>}
      </td>
      <td className="px-2.5 py-2 text-right tabular-nums">{grant.stars ?? '—'}</td>
      <td className="px-2.5 py-2 text-muted-2">{formatTashkent(grant.created_at)}</td>
      <td className="whitespace-nowrap px-2.5 py-2 tabular-nums">
        {formatTashkentDay(grant.starts_at)} — {formatTashkentDay(grant.ends_at)}
      </td>
      <td className="px-2.5 py-2">
        <span className={STATE_STYLES[grant.state]}>{STATE_LABELS[grant.state]}</span>
        {note && <span className="block text-xs text-muted">{note}</span>}
      </td>
      <td className="px-2.5 py-2">
        <div className="flex flex-wrap justify-end gap-1.5">
          {ACTION_ORDER.filter((action) => grant.actions.includes(action)).map((action) => (
            <button
              key={action}
              type="button"
              disabled={busy}
              onClick={() => onAct(action)}
              className={`${BUTTON} ${action === 'revoke' || action === 'refund' ? 'text-danger' : ''}`}
            >
              {ACTION_LABELS[action]}
            </button>
          ))}
        </div>
      </td>
    </tr>
  );
}

function perform(grant: ProGrant, action: ProGrantAction): Promise<ProGrant> {
  if (action === 'revoke') return api.revokeProGrant(grant.id);
  if (action === 'refund') return api.refundProGrant(grant.id);
  return api.setProRenewal(grant.subscription_id as number, action === 'stop_renewal');
}

function confirmation(grant: ProGrant, action: ProGrantAction): string {
  const person = who(grant);
  const renews = grant.actions.includes('stop_renewal');
  if (action === 'revoke') {
    return `Забрать Pro у ${person}? Оно закончится сейчас${renews ? ', подписка перестанет продлеваться' : ''}. Звёзды не вернутся.`;
  }
  if (action === 'refund') {
    return `Вернуть ${grant.stars} ★ ${person}? Pro по этому платежу закончится сейчас${renews ? ', подписка перестанет продлеваться' : ''}.`;
  }
  return `Telegram перестанет продлевать подписку ${person}. Pro останется до ${formatTashkentDay(grant.ends_at)}.`;
}

function who(grant: ProGrant): string {
  return grant.user.username ? `@${grant.user.username}` : grant.user.name || String(grant.user.telegram_id);
}

function kind(grant: ProGrant): string {
  if (grant.source === 'subscription') return 'Подписка на месяц';
  if (grant.source === 'purchase') return `Покупка: ${grant.plan ? PLAN_LABELS[grant.plan] : '—'}`;
  if (grant.source === 'promo') return `Промокод ${grant.promo_code ?? ''}`.trim();
  return 'Пробный период';
}

function renewal(grant: ProGrant): string | null {
  if (grant.actions.includes('stop_renewal')) return 'продлевается';
  if (grant.actions.includes('allow_renewal')) return 'продление остановлено';
  return null;
}
