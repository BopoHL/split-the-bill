'use client';

import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import { useStore } from '@/lib/store/useStore';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { chooseBadge, getBadges, type ProfileBadge, type ProfileBadges } from '@/lib/api/badges';
import { NO_BADGE, PRO_BADGE } from '@/lib/utils/badges';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import UserBadge from './UserBadge';

/**
 * The badge by the person's name that everyone at their bills sees: one of the
 * titles their bills earned them, Pro while they have it, or none.
 */
export default function BadgePicker({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { currentUser, setCurrentUser } = useStore();
  const [badges, setBadges] = useState<ProfileBadges | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const userId = currentUser?.id;

  useEffect(() => {
    if (!isOpen || !userId) return;
    getBadges(userId)
      .then(setBadges)
      .catch((error) => {
        console.error('Error loading badges:', error);
        showToast(t('common.error'));
      });
  }, [isOpen, userId, t]);

  const pick = async (badge: string) => {
    if (!currentUser || saving) return;
    setSaving(badge);
    try {
      const next = await chooseBadge(currentUser.id, badge);
      setBadges(next);
      track(AnalyticsEvent.BadgeChosen, { badge: next.chosen ?? null });
      setCurrentUser({ ...currentUser, settings: { ...currentUser.settings, badge: next.chosen ?? undefined } });
    } catch (error) {
      console.error('Error choosing a badge:', error);
      showToast(t('common.error'));
    } finally {
      setSaving(null);
    }
  };

  const selected = badges?.shown ?? NO_BADGE;
  const options: ProfileBadge[] = badges ? [{ key: NO_BADGE, value: null, subject: null }, ...badges.available] : [];
  const describe = (badge: ProfileBadge) => {
    if (badge.key === NO_BADGE) return t('settings.badgeNoneHint');
    if (badge.key === PRO_BADGE) return t('settings.badgeProHint');
    if (badge.value === null && badge.subject === null) return t('settings.badgeKeptHint');
    return t(`analytics.badge.${badge.key}.detail`, { value: String(badge.value ?? ''), subject: badge.subject ?? '' });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('settings.badge')} size="md">
      <div className="overflow-y-auto p-4">
        <p className="text-[13px] leading-snug text-muted">{t('settings.badgeHint')}</p>
        {!badges ? (
          <div className="flex justify-center py-10">
            <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-accent" />
          </div>
        ) : (
          <div role="radiogroup" aria-label={t('settings.badge')} className="mt-3 flex flex-col gap-2">
            {options.map((badge) => {
              const chosen = selected === badge.key;
              return (
                <button
                  key={badge.key}
                  type="button"
                  role="radio"
                  aria-checked={chosen}
                  disabled={saving !== null}
                  onClick={() => void pick(badge.key)}
                  className={`flex min-h-[52px] items-center gap-3 rounded-lg border-[1.5px] px-3 py-2 text-left transition-colors ${
                    chosen ? 'border-accent bg-accent-weak' : 'border-border hover:border-outline'
                  }`}
                >
                  <span className="flex w-[7.5rem] shrink-0">
                    {badge.key === NO_BADGE ? (
                      <span className="font-display text-[13px] font-bold">{t('settings.badgeNone')}</span>
                    ) : (
                      <UserBadge badge={badge.key} />
                    )}
                  </span>
                  <span className="min-w-0 flex-1 text-[12px] leading-snug text-muted">{describe(badge)}</span>
                  {chosen && <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-accent" strokeWidth={3} />}
                </button>
              );
            })}
            {badges.available.every((badge) => badge.key === PRO_BADGE) && (
              <p className="mt-1 text-[12px] leading-snug text-muted">{t('settings.badgeEmpty')}</p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
