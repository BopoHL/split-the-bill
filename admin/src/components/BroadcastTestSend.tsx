'use client';

import { useState } from 'react';
import { api, type BroadcastMessage } from '@/lib/api';
import { describeBroadcastError } from '@/lib/broadcastErrors';

const TARGET_KEY = 'broadcast-test-target';

interface Props {
  message: () => BroadcastMessage;
  photo: File | null;
  disabled: boolean;
}

/**
 * Sends every language of the draft to one person — usually the operator, to
 * look at it on a phone before everyone gets it. Who that is stays remembered
 * in this browser.
 */
export default function BroadcastTestSend({ message, photo, disabled }: Props) {
  const [target, setTarget] = useState(readStored);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const send = async () => {
    setBusy(true);
    setResult(null);
    store(target.trim());
    try {
      const { sent } = await api.testBroadcast(message(), target.trim(), photo);
      setResult({ ok: true, text: `Отправлено: ${sent.join(', ')}` });
    } catch (err) {
      setResult({ ok: false, text: describeBroadcastError(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 rounded-md border border-dashed border-border p-3">
      <label htmlFor="broadcast-test-target" className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted">
        Проверить на себе
      </label>
      <div className="flex gap-2">
        <input
          id="broadcast-test-target"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="@username или telegram id"
          className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent"
        />
        <button
          type="button"
          disabled={disabled || busy || !target.trim()}
          onClick={send}
          className="rounded-md border border-border px-3 py-1.5 text-sm font-semibold hover:border-accent hover:text-accent disabled:opacity-50"
        >
          Отправить себе
        </button>
      </div>
      {result && (
        <p className={`mt-1.5 text-xs ${result.ok ? 'text-success' : 'text-danger'}`}>{result.text}</p>
      )}
    </div>
  );
}

function readStored(): string {
  if (typeof window === 'undefined') return '';
  try {
    return localStorage.getItem(TARGET_KEY) ?? '';
  } catch {
    return '';
  }
}

function store(target: string): void {
  try {
    localStorage.setItem(TARGET_KEY, target);
  } catch {
    /* a private window: the field just starts empty next time */
  }
}
