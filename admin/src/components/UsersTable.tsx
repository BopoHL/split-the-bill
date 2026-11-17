'use client';

import { useEffect, useState } from 'react';
import { api, type Page, type UserRow } from '@/lib/api';
import Pagination from './Pagination';

interface Props {
  onOpenUser: (id: number) => void;
}

const PAGE_LIMIT = 50;

export default function UsersTable({ onOpenUser }: Props) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<UserRow>>({
    items: [],
    total: 0,
    limit: PAGE_LIMIT,
    offset: 0,
  });

  useEffect(() => {
    api.users(page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [page]);

  const rows = data.items;

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
          <tr>
            <th className="px-3 py-2">Пользователь</th>
            <th className="px-3 py-2">Telegram ID</th>
            <th className="px-3 py-2">Язык</th>
            <th className="px-3 py-2">Валюта</th>
            <th className="px-3 py-2">Онбординг</th>
            <th className="px-3 py-2 text-right">Счета</th>
            <th className="px-3 py-2">Бот</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((user) => (
            <tr key={user.id} className="border-t border-border">
              <td className="px-3 py-2">
                <button
                  onClick={() => onOpenUser(user.id)}
                  className="min-h-10 text-left font-medium transition-colors hover:text-accent"
                >
                  {userLabel(user)}
                  <span className="ml-1 text-xs font-normal text-muted-2">#{user.id}</span>
                </button>
              </td>
              <td className="px-3 py-2 tabular-nums text-muted">{user.telegram_id}</td>
              <td className="px-3 py-2 uppercase text-muted">{user.language || '—'}</td>
              <td className="px-3 py-2 uppercase text-muted">{user.currency || '—'}</td>
              <td className="px-3 py-2">
                {user.onboarding_completed ? (
                  <span className="text-success">пройден</span>
                ) : (
                  <span className="text-muted">нет</span>
                )}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {user.bills_count}
                {user.participant_bills_count > 0 && (
                  <span className="ml-1 text-muted-2">+{user.participant_bills_count}</span>
                )}
              </td>
              <td className="px-3 py-2">
                {user.bot_blocked ? (
                  <span className="text-danger">заблокирован</span>
                ) : (
                  <span className="text-success">доступен</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="px-3 py-6 text-center text-muted">Пусто</p>}
      <Pagination page={page} limit={data.limit} total={data.total} onPageChange={setPage} />
    </div>
  );
}

function userLabel(user: UserRow): string {
  return user.username || [user.name, user.surname].filter(Boolean).join(' ') || `#${user.id}`;
}
