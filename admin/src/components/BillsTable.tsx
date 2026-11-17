'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type BillRow, type Page } from '@/lib/api';
import { formatMoney } from '@/lib/money';
import Pagination from './Pagination';

interface Props {
  onOpenBill: (id: number) => void;
  onOpenUser: (id: number) => void;
}

const PAGE_LIMIT = 50;

export default function BillsTable({ onOpenBill, onOpenUser }: Props) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<BillRow>>({
    items: [],
    total: 0,
    limit: PAGE_LIMIT,
    offset: 0,
  });
  const [includeDeleted, setIncludeDeleted] = useState(false);

  const load = useCallback(() => {
    api.bills(includeDeleted, page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [includeDeleted, page]);

  useEffect(load, [load]);

  const rows = data.items;

  return (
    <div>
      <label className="mb-3 flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={includeDeleted}
          onChange={(e) => {
            setIncludeDeleted(e.target.checked);
            setPage(1);
          }}
        />
        Показывать удалённые
      </label>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Счёт</th>
              <th className="px-3 py-2">Владелец</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2 text-right">Сумма</th>
              <th className="px-3 py-2 text-right">Люди</th>
              <th className="px-3 py-2 text-right">Чеки</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((bill) => (
              <tr
                key={bill.id}
                className={`border-t border-border ${bill.is_deleted ? 'opacity-55' : ''}`}
              >
                <td className="px-3 py-2">
                  <button
                    onClick={() => onOpenBill(bill.id)}
                    className="min-h-10 text-left font-medium transition-colors hover:text-accent"
                  >
                    {bill.title || `#${bill.id}`}
                    <span className="ml-1 text-xs font-normal text-muted-2">#{bill.id}</span>
                  </button>
                </td>
                <td className="px-3 py-2">
                  <button
                    onClick={() => onOpenUser(bill.owner_id)}
                    className="min-h-10 text-left text-muted transition-colors hover:text-accent"
                  >
                    {bill.owner || `#${bill.owner_id}`}
                  </button>
                </td>
                <td className="px-3 py-2">{bill.is_deleted ? 'удалён' : statusLabel(bill.status)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMoney(bill.total_sum, bill.currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{bill.participants_count}</td>
                <td className="px-3 py-2 text-right tabular-nums">{bill.receipts_count}</td>
                <td className="px-3 py-2 text-right">
                  {bill.is_deleted && (
                    <button
                      onClick={() => api.restoreBill(bill.id).then(load)}
                      className="rounded border border-border px-2 py-1 text-xs transition-colors hover:border-success hover:text-success"
                    >
                      Восстановить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="px-3 py-6 text-center text-muted">Пусто</p>}
        <Pagination
          page={page}
          limit={data.limit}
          total={data.total}
          onPageChange={setPage}
        />
      </div>
    </div>
  );
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: 'открыт',
    paid: 'оплачен',
    closed: 'закрыт',
  };
  return labels[status] ?? status;
}
