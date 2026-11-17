'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Search, Send } from 'lucide-react';
import { getAssignableUsers } from '@/lib/api/bills';
import { useTranslation } from '@/lib/i18n/useTranslation';
import type { AssignableUser } from '@/types/api';
import Modal from '@/components/ui/Modal';

interface Props {
  billId: number;
  isOpen: boolean;
  onClose: () => void;
  onPick: (user: AssignableUser) => Promise<void>;
  /** Hand the invite over yourself, for the person the app has never seen. */
  onSendPersonalInvite?: () => Promise<void>;
}

const SEARCH_DELAY_MS = 300;
/** Matches the backend: shorter than this is not a username lookup. */
const SEARCH_MIN_LENGTH = 3;

/**
 * Who to put on a guest seat.
 *
 * The list is people the app has actually seen the owner with; the search box
 * is for the person it hasn't. Somebody who once blocked the bot is still
 * offered — they may have come back since — and the seat is only taken once
 * the invite has actually reached them.
 *
 * And when it reaches nobody — a person with no account yet, or one the bot
 * cannot write to — the way out is at the bottom: send the invite by hand. That
 * used to be a second button on the seat itself, which made filling one seat
 * look like two unrelated features.
 */
export default function AssignUserPicker({
  billId,
  isOpen,
  onClose,
  onPick,
  onSendPersonalInvite,
}: Props) {
  const { t } = useTranslation();
  const [sendingInvite, setSendingInvite] = useState(false);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [pickingId, setPickingId] = useState<number | null>(null);
  // Which request the list is waiting for. Typing fires one per pause, and
  // the answers need not come back in order — only the latest may be shown.
  const requestRef = useRef(0);

  useEffect(() => {
    if (!isOpen) {
      setSearch('');
      setTerm('');
      setUsers([]);
    }
  }, [isOpen]);

  useEffect(() => {
    const timer = setTimeout(() => setTerm(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  // The «@» is how people write a username, not part of it — the server
  // strips it too, so it must not count toward the minimum.
  const typed = term.replace(/^@+/, '');
  const searchTooShort = typed.length > 0 && typed.length < SEARCH_MIN_LENGTH;

  const load = useCallback(() => {
    if (!isOpen) return;
    if (searchTooShort) {
      // Two letters is not a lookup, and the server would only answer with an
      // empty list anyway.
      setUsers([]);
      return;
    }
    const request = ++requestRef.current;
    const latest = () => request === requestRef.current;
    setLoading(true);
    getAssignableUsers(billId, typed || undefined)
      .then((found) => {
        if (latest()) setUsers(found);
      })
      .catch((e) => {
        console.error(e);
        if (latest()) setUsers([]);
      })
      .finally(() => {
        if (latest()) setLoading(false);
      });
  }, [billId, typed, isOpen, searchTooShort]);

  useEffect(load, [load]);

  const handlePick = async (user: AssignableUser) => {
    if (pickingId != null) return;
    setPickingId(user.user_id);
    try {
      await onPick(user);
    } finally {
      setPickingId(null);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('bill.assignUser')} size="sm">
      <div className="flex min-h-0 flex-col gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-2" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('bill.assignUserSearch')}
            className="w-full rounded-lg border-[1.5px] border-border bg-surface py-2 pl-9 pr-3 text-[14px] text-foreground placeholder:text-muted-2 focus:border-outline focus:outline-none"
          />
        </div>

        <div className="max-h-72 min-h-0 overflow-y-auto overscroll-contain">
          {loading && <p className="py-6 text-center text-[13px] text-muted">{t('common.loading')}</p>}
          {!loading && searchTooShort && (
            <p className="py-6 text-center text-[13px] text-muted">{t('bill.assignUserKeepTyping')}</p>
          )}
          {!loading && !searchTooShort && users.length === 0 && (
            <p className="py-6 text-center text-[13px] text-muted">{t('bill.assignUserEmpty')}</p>
          )}
          {!loading &&
            users.map((user) => (
              <button
                key={user.user_id}
                type="button"
                onClick={() => void handlePick(user)}
                disabled={pickingId != null}
                className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface-2 disabled:opacity-50"
              >
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border-[1.5px] border-outline bg-surface font-mono text-[12px] font-bold uppercase text-foreground">
                  {user.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    assignableInitial(user)
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-bold text-foreground">
                    {assignableLabel(user)}
                  </span>
                  {user.username && (
                    <span className="block truncate font-mono text-[11px] text-muted-2">
                      @{user.username}
                    </span>
                  )}
                </span>
              </button>
            ))}
        </div>

        <p className="text-[11px] leading-snug text-muted-2">{t('bill.assignUserHint')}</p>

        {onSendPersonalInvite && (
          <div className="border-t-[1.5px] border-dashed border-border pt-3">
            <button
              type="button"
              disabled={sendingInvite}
              onClick={async () => {
                setSendingInvite(true);
                try {
                  await onSendPersonalInvite();
                } finally {
                  setSendingInvite(false);
                }
              }}
              className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2.5 text-left text-accent transition-colors hover:bg-surface-2 disabled:opacity-60"
            >
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border-[1.5px] border-dashed border-accent">
                {sendingInvite ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" strokeWidth={2.25} />
                )}
              </span>
              <span className="text-[14px] font-bold leading-snug">
                {sendingInvite ? t('bill.preparingShare') : t('bill.sendPersonalInvite')}
              </span>
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function assignableLabel(user: AssignableUser): string {
  const full = [user.name, user.surname].filter(Boolean).join(' ').trim();
  return full || user.username || `#${user.user_id}`;
}

function assignableInitial(user: AssignableUser): string {
  return assignableLabel(user).charAt(0);
}
