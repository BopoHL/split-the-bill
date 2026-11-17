'use client';

import { useEffect, useState } from 'react';
import { api, type Stats } from '@/lib/api';

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1.5 text-2xl font-bold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-2">{hint}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch(console.error);
  }, []);

  if (!stats) return <p className="text-muted">Загрузка…</p>;

  const scanSuccess = stats.scans_total
    ? Math.round(((stats.scans_total - stats.scans_failed) / stats.scans_total) * 100)
    : 0;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Metric
        label="Пользователи"
        value={String(stats.users_total)}
        hint={`+${stats.users_new_7d} за неделю`}
      />
      <Metric
        label="Счета"
        value={String(stats.bills_total)}
        hint={`${stats.bills_open} открыто · ${stats.bills_closed} закрыто`}
      />
      <Metric
        label="Сканы"
        value={String(stats.scans_total)}
        hint={`${scanSuccess}% успешных`}
      />
      <Metric label="Средний счёт" value={stats.average_bill.toLocaleString('ru-RU')} />
      <Metric
        label="Удалённые счета"
        value={String(stats.bills_deleted)}
        hint="можно восстановить"
      />
    </div>
  );
}
