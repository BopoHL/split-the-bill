'use client';

import { useEffect, useState } from 'react';
import { api, type FeedbackRow, type Page } from '@/lib/api';
import { formatTashkent } from '@/lib/time';
import Pagination from './Pagination';

interface Props {
  onOpenUser: (id: number) => void;
}

const PAGE_LIMIT = 50;

/** What people wrote in the app's feedback form, newest first. */
export default function Feedback({ onOpenUser }: Props) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<FeedbackRow>>({
    items: [],
    total: 0,
    limit: PAGE_LIMIT,
    offset: 0,
  });

  useEffect(() => {
    api.feedback(page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [page]);

  return (
    <div className="rounded-lg border border-border">
      <ul>
        {data.items.map((row) => (
          <li key={row.id} className="border-t border-border px-4 py-3 first:border-t-0">
            <div className="mb-1.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
              <span className="tabular-nums">{formatTashkent(row.created_at)}</span>
              <span aria-hidden="true">·</span>
              {row.user_id != null ? (
                <button
                  onClick={() => onOpenUser(row.user_id!)}
                  className="font-medium text-foreground transition-colors hover:text-accent"
                >
                  {row.user ?? `#${row.user_id}`}
                </button>
              ) : (
                <span>аноним</span>
              )}
              {row.name && <span className="text-muted-2">подписался «{row.name}»</span>}
            </div>
            <p className="whitespace-pre-wrap break-words text-sm">{row.message}</p>
          </li>
        ))}
      </ul>
      {data.items.length === 0 && <p className="px-3 py-6 text-center text-muted">Пусто</p>}
      <Pagination page={page} limit={data.limit} total={data.total} onPageChange={setPage} />
    </div>
  );
}
