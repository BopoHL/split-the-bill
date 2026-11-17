'use client';

import { useEffect, useState } from 'react';
import { api, type BillRow, type UserDetail as Detail } from '@/lib/api';
import { formatTashkent } from '@/lib/time';
import ProGrants from './ProGrants';
import UserSettingsForm from './UserSettingsForm';

interface Props {
  id: number;
  onClose: () => void;
  onOpenBill: (id: number) => void;
}

export default function UserDetail({ id, onClose, onOpenBill }: Props) {
  const [user, setUser] = useState<Detail | null>(null);

  useEffect(() => {
    api.user(id).then(setUser).catch(console.error);
  }, [id]);

  if (!user) return <p className="py-10 text-center text-muted">Загрузка…</p>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onClose}
          className="min-h-10 rounded-md border border-border px-3 text-sm text-muted transition-colors hover:text-foreground"
        >
          ← Назад
        </button>
        {user.avatar_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={user.avatar_url}
            alt=""
            className="h-10 w-10 rounded-md object-cover"
            style={{ outline: '1px solid rgba(0, 0, 0, 0.1)' }}
          />
        )}
        <h2 className="text-lg font-bold">
          {userLabel(user)}
          <span className="ml-2 text-sm font-normal text-muted-2">#{user.id}</span>
        </h2>
        {user.bot_blocked ? (
          <span className="rounded-md bg-surface px-2 py-0.5 text-xs text-danger">
            бот заблокирован
          </span>
        ) : (
          <span className="rounded-md bg-surface px-2 py-0.5 text-xs text-success">
            бот доступен
          </span>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border border-border bg-surface p-4 text-sm md:grid-cols-6">
        <Fact label="Telegram ID" value={String(user.telegram_id)} />
        <Fact label="Username" value={user.username ? `@${user.username}` : '—'} />
        <Fact label="Имя" value={[user.name, user.surname].filter(Boolean).join(' ') || '—'} />
        <Fact label="Язык" value={(user.language || '—').toUpperCase()} />
        <Fact label="Валюта" value={(user.currency || '—').toUpperCase()} />
        <Fact label="Онбординг" value={user.onboarding_completed ? 'пройден' : 'не пройден'} />
        <Fact label="Своих счетов" value={String(user.bills_count)} />
        <Fact label="Участий" value={String(user.participant_bills_count)} />
        <Fact label="Создан" value={formatTashkent(user.created_at)} />
      </dl>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <BillsBlock title="Его счета" rows={user.owned_bills} onOpenBill={onOpenBill} />
          <BillsBlock
            title="Счета, где участвовал"
            rows={user.participant_bills}
            onOpenBill={onOpenBill}
          />
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Pro</h3>
            <ProGrants userId={user.id} />
          </section>
        </div>

        <UserSettingsForm key={user.id} user={user} onSaved={setUser} />
      </div>
    </div>
  );
}

function BillsBlock({
  title,
  rows,
  onOpenBill,
}: {
  title: string;
  rows: BillRow[];
  onOpenBill: (id: number) => void;
}) {
  return (
    <section className="overflow-x-auto rounded-lg border border-border bg-surface">
      <h3 className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted">
        {title}
      </h3>
      {rows.length === 0 ? (
        <p className="border-t border-border px-4 py-6 text-center text-sm text-muted">Пусто</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="border-t border-border text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-2">Счёт</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2 text-right">Сумма</th>
              <th className="px-3 py-2 text-right">Люди</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((bill) => (
              <tr key={bill.id} className="border-t border-border">
                <td className="px-4 py-2">
                  <button
                    onClick={() => onOpenBill(bill.id)}
                    className="min-h-10 text-left font-medium transition-colors hover:text-accent"
                  >
                    {bill.title || `Счёт #${bill.id}`}
                    <span className="ml-1 text-xs font-normal text-muted-2">#{bill.id}</span>
                  </button>
                </td>
                <td className="px-3 py-2">{bill.is_deleted ? 'удалён' : statusLabel(bill.status)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMoney(bill.total_sum, bill.currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{bill.participants_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
      <dd className="mt-0.5 tabular-nums">{value}</dd>
    </div>
  );
}

function userLabel(user: Detail): string {
  return user.username || [user.name, user.surname].filter(Boolean).join(' ') || `#${user.id}`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: 'открыт',
    paid: 'оплачен',
    closed: 'закрыт',
  };
  return labels[status] ?? status;
}

function formatMoney(amount: number, currency: string): string {
  return `${amount.toLocaleString('ru-RU')} ${currency.toUpperCase()}`;
}
