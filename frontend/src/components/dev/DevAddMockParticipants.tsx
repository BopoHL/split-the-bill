'use client';

/**
 * Dev-only widget on the bill detail screen that lets the owner add
 * other mock users (Alice / Bob / Leonid except current) as
 * participants without going through the Telegram invite link — that
 * link doesn't work in mock mode.
 *
 * Loaded via dynamic import behind `process.env.NODE_ENV !== 'production'`
 * in bill/[id]/page.tsx, so this file (and its devMock dependency)
 * never ends up in production bundles.
 */

import { useMemo, useState } from 'react';
import { UserPlus, Loader2, Check } from 'lucide-react';
import {
  MOCK_USERS,
  buildMockInitData,
  resolveMockUser,
  type MockUserKey,
} from '@/lib/telegram/devMock';
import { getUserByTelegramId } from '@/lib/api/users';
import { addBillParticipant } from '@/lib/api/bills';

interface Props {
  billId: number;
  /**
   * Usernames of users already on this bill (incl. current owner).
   * We match by username because `BillParticipant.user_id` is the
   * backend ID, not the Telegram ID we have in MOCK_USERS.
   */
  existingUsernames: string[];
  /** Called after a successful add so the parent can re-fetch the bill. */
  onAdded?: () => void;
}

type RowStatus = 'idle' | 'loading' | 'done' | 'error';

export default function DevAddMockParticipants({
  billId,
  existingUsernames,
  onAdded,
}: Props) {
  const activeKey = resolveMockUser().key;
  const [rowStatus, setRowStatus] = useState<Record<MockUserKey, RowStatus>>(
    {} as Record<MockUserKey, RowStatus>,
  );

  // Show only mock users who are NOT the currently logged-in mock and
  // NOT already participants of this bill.
  const availableKeys = useMemo(() => {
    const taken = new Set(existingUsernames.filter(Boolean));
    return (Object.keys(MOCK_USERS) as MockUserKey[]).filter((key) => {
      if (key === activeKey) return false;
      const username = MOCK_USERS[key].username;
      return !username || !taken.has(username);
    });
  }, [activeKey, existingUsernames]);

  const addUser = async (key: MockUserKey) => {
    const user = MOCK_USERS[key];
    setRowStatus((s) => ({ ...s, [key]: 'loading' }));
    try {
      // Upsert the target user on the backend, then the owner seats them.
      // The backend accepts the fake hash only with ALLOW_UNSIGNED_INIT_DATA.
      const upserted = await getUserByTelegramId(
        user.id,
        user.username,
        user.photo_url,
        buildMockInitData(user),
      );
      if (!upserted) throw new Error('upsert returned null');
      await addBillParticipant(billId, upserted.id);
      setRowStatus((s) => ({ ...s, [key]: 'done' }));
      onAdded?.();
    } catch (err) {
      console.error('[dev] failed to add mock participant', key, err);
      setRowStatus((s) => ({ ...s, [key]: 'error' }));
    }
  };

  if (availableKeys.length === 0) return null;

  return (
    <div
      style={{
        marginTop: 16,
        padding: '10px 12px',
        border: '1px dashed rgba(0,0,0,0.25)',
        borderRadius: 8,
        background: 'rgba(252,196,25,0.08)',
        fontFamily: 'ui-monospace, monospace',
        fontSize: 12,
      }}
    >
      <div style={{ opacity: 0.65, marginBottom: 6 }}>
        DEV: add mock user as participant
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {availableKeys.map((key) => {
          const status = rowStatus[key] ?? 'idle';
          const isLoading = status === 'loading';
          const isDone = status === 'done';
          return (
            <button
              key={key}
              onClick={() => addUser(key)}
              disabled={isLoading || isDone}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                borderRadius: 999,
                border: '1px solid rgba(0,0,0,0.2)',
                background: isDone ? 'rgba(16,185,129,0.15)' : 'white',
                cursor: isLoading || isDone ? 'default' : 'pointer',
                font: 'inherit',
              }}
            >
              {isLoading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : isDone ? (
                <Check className="w-3 h-3" />
              ) : (
                <UserPlus className="w-3 h-3" />
              )}
              <span>{MOCK_USERS[key].first_name}</span>
              {status === 'error' && (
                <span style={{ color: '#dc2626' }}>!</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
