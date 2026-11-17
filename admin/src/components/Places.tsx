'use client';

import { useEffect, useState } from 'react';
import { api, type Page, type PlaceRow } from '@/lib/api';
import { formatTashkent } from '@/lib/time';
import Pagination from './Pagination';

const PAGE_LIMIT = 50;
const SEARCH_DELAY_MS = 300;
const EMPTY: Page<PlaceRow> = { items: [], total: 0, limit: PAGE_LIMIT, offset: 0 };

/** Where bills were run up, the most used first — as the labelling named them. */
export default function Places() {
  const [data, setData] = useState<Page<PlaceRow>>(EMPTY);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setTerm(search.trim());
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    api.places(term, page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [term, page]);

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline gap-3">
        <h2 className="font-bold">Места</h2>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Название места"
          aria-label="Поиск мест"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
        />
        <span className="ml-auto text-sm text-muted">
          Всего: <span className="tabular-nums">{data.total}</span>
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Место</th>
              <th className="px-3 py-2 text-right">Счетов</th>
              <th className="px-3 py-2 text-right">Людей</th>
              <th className="px-3 py-2">Первый счёт</th>
              <th className="px-3 py-2">Последний</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((place) => (
              <tr key={place.id} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{place.name}</td>
                <td className="px-3 py-2 text-right tabular-nums">{place.bills}</td>
                <td className="px-3 py-2 text-right tabular-nums">{place.people}</td>
                <td className="px-3 py-2 text-muted-2">{place.first_bill_at ? formatTashkent(place.first_bill_at) : '—'}</td>
                <td className="px-3 py-2 text-muted-2">{place.last_bill_at ? formatTashkent(place.last_bill_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && <p className="px-3 py-6 text-center text-muted">Мест пока нет</p>}
        <Pagination page={page} limit={PAGE_LIMIT} total={data.total} onPageChange={setPage} />
      </div>
    </section>
  );
}
