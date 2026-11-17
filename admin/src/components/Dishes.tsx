'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type DishGroup, type DishKind, type DishRow, type Page } from '@/lib/api';
import Pagination from './Pagination';
import Select from './Select';

const PAGE_LIMIT = 50;
const SEARCH_DELAY_MS = 300;
const EMPTY: Page<DishRow> = { items: [], total: 0, limit: PAGE_LIMIT, offset: 0 };

const GROUPS: { value: DishGroup; label: string }[] = [
  { value: 'food', label: 'Еда' },
  { value: 'drink', label: 'Напитки' },
  { value: 'dessert', label: 'Десерты' },
  { value: 'alcohol', label: 'Алкоголь' },
  { value: 'fee', label: 'Сбор' },
  { value: 'discount', label: 'Скидка' },
  { value: 'other', label: 'Другое' },
];
const NO_KIND = '';

/**
 * What each receipt line was labelled as, the most frequent first. The group
 * says where the money went in analytics, the kind which dish it counts as;
 * a correction is kept as the admin's and never relabelled.
 */
export default function Dishes() {
  const [data, setData] = useState<Page<DishRow>>(EMPTY);
  const [kinds, setKinds] = useState<DishKind[]>([]);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [group, setGroup] = useState('');
  const [kind, setKind] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setTerm(search.trim());
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    api.dishes({ q: term, group, kind }, page, PAGE_LIMIT).then(setData).catch(console.error);
  }, [term, group, kind, page]);

  const loadKinds = useCallback(() => {
    api.dishKinds().then(setKinds).catch(console.error);
  }, []);
  useEffect(loadKinds, [loadKinds]);

  const correct = async (dish: DishRow, nextGroup: DishGroup, nextKind: string | null) => {
    setError(null);
    try {
      const fixed = await api.correctDish(dish.name_key, nextGroup, nextKind);
      setData((shown) => ({ ...shown, items: shown.items.map((item) => (item.name_key === fixed.name_key ? fixed : item)) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не сохранилось');
    }
  };

  const kindOptions = kinds.map((option) => ({ value: option.key, label: option.ru }));

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline gap-3">
        <h2 className="font-bold">Блюда и категории</h2>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Название в чеке"
          aria-label="Поиск блюд"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
        />
        <Select
          options={[{ value: '', label: 'Любая группа' }, ...GROUPS]}
          value={group}
          onChange={(next) => {
            setGroup(next);
            setPage(1);
          }}
        />
        <Select
          options={[{ value: '', label: 'Любой тип' }, ...kindOptions]}
          value={kind}
          onChange={(next) => {
            setKind(next);
            setPage(1);
          }}
        />
        <span className="ml-auto text-sm text-muted">
          Всего: <span className="tabular-nums">{data.total}</span>
        </span>
      </div>
      {error && <p className="mb-2 text-sm text-danger">{error}</p>}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Как в чеке</th>
              <th className="px-3 py-2 text-right">Строк</th>
              <th className="px-3 py-2">Группа</th>
              <th className="px-3 py-2">Тип</th>
              <th className="px-3 py-2">Разметил</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((dish) => (
              <tr key={dish.name_key} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{dish.name_key}</td>
                <td className="px-3 py-2 text-right tabular-nums">{dish.lines}</td>
                <td className="px-3 py-2">
                  <select
                    aria-label={`Группа: ${dish.name_key}`}
                    value={dish.group}
                    onChange={(event) => void correct(dish, event.target.value as DishGroup, dish.kind)}
                    className="rounded-md border border-border bg-background px-2 py-1 text-sm"
                  >
                    {GROUPS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <select
                    aria-label={`Тип: ${dish.name_key}`}
                    value={dish.kind ?? NO_KIND}
                    onChange={(event) => void correct(dish, dish.group, event.target.value || null)}
                    className="rounded-md border border-border bg-background px-2 py-1 text-sm"
                  >
                    <option value={NO_KIND}>— не блюдо</option>
                    {kindOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </td>
                <td className={`px-3 py-2 ${dish.model === 'admin' ? 'font-medium text-success' : 'text-muted-2'}`}>
                  {dish.model === 'admin' ? 'вручную' : dish.model ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && <p className="px-3 py-6 text-center text-muted">Ничего не найдено</p>}
        <Pagination page={page} limit={PAGE_LIMIT} total={data.total} onPageChange={setPage} />
      </div>
      <NewKind onCreated={loadKinds} />
    </section>
  );
}

const EMPTY_KIND: DishKind = { key: '', ru: '', uz: '', en: '' };

/** A kind the model has not named yet, in each language the app speaks. */
function NewKind({ onCreated }: { onCreated: () => void }) {
  const [draft, setDraft] = useState<DishKind>(EMPTY_KIND);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const kind = await api.createDishKind(draft);
      setMade(kind.ru);
      setDraft(EMPTY_KIND);
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не создался');
    } finally {
      setBusy(false);
    }
  };

  const field = 'rounded-md border border-border bg-background px-3 py-1.5 text-sm';
  const fields: { key: keyof DishKind; label: string; placeholder: string }[] = [
    { key: 'key', label: 'Ключ', placeholder: 'lagman' },
    { key: 'ru', label: 'По-русски', placeholder: 'Лагман' },
    { key: 'uz', label: 'По-узбекски', placeholder: 'Lag‘mon' },
    { key: 'en', label: 'По-английски', placeholder: 'Lagman' },
  ];

  return (
    <form
      className="mt-4 rounded-lg border border-border bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault();
        void create();
      }}
    >
      <h3 className="mb-1 text-sm font-bold">Новый тип блюда</h3>
      <p className="mb-3 text-xs text-muted">Если нужного типа нет в списке. Ключ — латиницей, как lagman или green_tea.</p>
      <div className="flex flex-wrap items-end gap-3">
        {fields.map(({ key, label, placeholder }) => (
          <label key={key} className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{label}</span>
            <input
              required
              value={draft[key]}
              onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
              placeholder={placeholder}
              className={`${field} w-40 ${key === 'key' ? 'font-mono' : ''}`}
            />
          </label>
        ))}
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background disabled:opacity-50"
        >
          {busy ? 'Создаём…' : 'Добавить'}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      {made && <p className="mt-2 text-sm">Добавлен тип «{made}»</p>}
    </form>
  );
}
