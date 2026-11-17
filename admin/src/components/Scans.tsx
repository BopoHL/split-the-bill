'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type ScanFilters, type ScanRow } from '@/lib/api';
import { formatTashkent } from '@/lib/time';
import ScanDetail from './ScanDetail';
import { MODES, MODE_LABELS } from './ScanModes';
import Select from './Select';

const STATUSES = [
  { value: '', label: 'Любой статус' },
  { value: 'completed', label: 'Готово' },
  { value: 'failed', label: 'Ошибка' },
  { value: 'processing', label: 'Распознаётся' },
  { value: 'structuring', label: 'Разбирается' },
];

const SOURCES = [
  { value: '', label: 'Любой источник' },
  { value: 'photo', label: 'Фото' },
  { value: 'soliq_qr', label: 'Soliq QR' },
  { value: 'manual_photo', label: 'Фото без распознавания' },
];

const MODE_FILTERS = [{ value: '', label: 'Любой режим' }, ...MODES];

const QUALITIES = [
  { value: '', label: 'Любая оценка' },
  { value: 'low', label: 'Низкая (до 3)' },
  { value: 'rated', label: 'С оценкой' },
  { value: 'unrated', label: 'Без оценки' },
];

export default function Scans() {
  const [rows, setRows] = useState<ScanRow[]>([]);
  const [filters, setFilters] = useState<ScanFilters>({});
  const [openId, setOpenId] = useState<number | null>(null);

  const load = useCallback(() => {
    api.scans(filters).then(setRows).catch(console.error);
  }, [filters]);

  useEffect(load, [load]);

  if (openId !== null) {
    return <ScanDetail id={openId} onClose={() => setOpenId(null)} />;
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        <Select
          options={STATUSES}
          value={filters.status ?? ''}
          onChange={(status) => setFilters({ ...filters, status })}
        />
        <Select
          options={SOURCES}
          value={filters.source ?? ''}
          onChange={(source) => setFilters({ ...filters, source })}
        />
        <Select
          options={MODE_FILTERS}
          value={filters.mode ?? ''}
          onChange={(mode) => setFilters({ ...filters, mode })}
        />
        <Select
          options={QUALITIES}
          value={filters.quality ?? ''}
          onChange={(quality) => setFilters({ ...filters, quality })}
        />
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Скан</th>
              <th className="px-3 py-2">Источник</th>
              <th className="px-3 py-2">Режим</th>
              <th className="px-3 py-2">Модель</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2 text-right">Позиций</th>
              <th className="px-3 py-2 text-right">Оценка</th>
              <th className="px-3 py-2">Когда</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((scan) => (
              <tr key={scan.id} className="border-t border-border">
                <td className="px-3 py-2">
                  <button
                    onClick={() => setOpenId(scan.id)}
                    className="text-left transition-colors hover:text-accent"
                  >
                    <div className="font-medium">#{scan.id} {scan.bill_title ?? 'без названия'}</div>
                    <div className="text-xs text-muted-2">
                      {scan.user ? `@${scan.user}` : 'без пользователя'}
                      {scan.has_photo ? ' · фото' : ''}
                    </div>
                  </button>
                </td>
                <td className="px-3 py-2 text-muted">{scan.source}</td>
                <td className="px-3 py-2 text-muted-2">
                  {scan.scan_mode ? MODE_LABELS[scan.scan_mode] ?? scan.scan_mode : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-2">{scan.llm_model ?? '—'}</td>
                <td className="px-3 py-2">
                  {scan.status}
                  {scan.error_message && (
                    <div className="truncate text-xs text-danger">{scan.error_message}</div>
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{scan.items_count}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {scan.scan_quality ?? '—'}
                </td>
                <td className="px-3 py-2 text-muted-2">{formatTashkent(scan.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="px-3 py-6 text-center text-muted">Ничего не нашлось</p>}
      </div>
    </div>
  );
}

