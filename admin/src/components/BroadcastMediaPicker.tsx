'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { describeBroadcastError } from '@/lib/broadcastErrors';

interface Props {
  /** Puts `<img src>` into the text being written, where its cursor is. */
  onInsert: (tag: string) => void;
}

/**
 * Pictures for a rich message. Each is uploaded once and then placed between
 * paragraphs by its address — Telegram downloads it from there while sending.
 */
export default function BroadcastMediaPicker({ onInsert }: Props) {
  const [pictures, setPictures] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const { url } = await api.uploadBroadcastMedia(file);
      setPictures((current) => [...current, url]);
    } catch (err) {
      setError(describeBroadcastError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-3">
      <label
        htmlFor="broadcast-media"
        className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted"
      >
        Картинки в тексте
      </label>
      <input
        id="broadcast-media"
        type="file"
        accept="image/*"
        disabled={busy}
        onChange={(e) => {
          upload(e.target.files?.[0]);
          e.target.value = '';
        }}
        className="mb-2 w-full text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-sm"
      />
      {error && <p className="mb-2 text-xs text-danger">{error}</p>}
      {pictures.length > 0 && (
        <ul className="space-y-1.5">
          {pictures.map((url) => (
            <li key={url} className="flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- a remote upload, shown as is */}
              <img src={url} alt="" className="h-10 w-14 rounded border border-border object-cover" />
              <span className="min-w-0 flex-1 truncate text-xs text-muted-2">{url}</span>
              <button
                type="button"
                onClick={() => onInsert(`<img src="${url}"/>`)}
                className="rounded border border-border px-2 py-1 text-xs hover:border-accent hover:text-accent"
              >
                Вставить
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
