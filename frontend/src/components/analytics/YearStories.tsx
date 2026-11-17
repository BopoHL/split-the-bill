'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, ExternalLink, Sparkles, X } from 'lucide-react';
import Button from '@/components/ui/Button';
import type { AnalyticsPictures } from '@/types/analytics';
import { getAnalyticsPictures } from '@/lib/api/analytics';
import { canDownloadFile, canShareToStory, downloadFile, shareToStory } from '@/lib/telegram/media';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { downloadAddress } from '@/lib/utils/analytics';
import { useScrollLock } from '@/hooks/useScrollLock';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';

/**
 * The year told as stories, one picture at a time, the way Telegram shows
 * them: a tap on the right goes on, on the left goes back. Each one goes to the
 * story editor as it is. The pictures are asked for once the year is opened.
 */
export default function YearStories({ userId, year, open, onClose }: {
  userId: number;
  year: number;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [pictures, setPictures] = useState<AnalyticsPictures | null>(null);
  const [failed, setFailed] = useState(false);
  const [index, setIndex] = useState(0);
  useScrollLock(open);

  useEffect(() => {
    if (!open || pictures) return;
    let current = true;
    getAnalyticsPictures(userId, { kind: 'year', year })
      .then((answer) => {
        if (current) setPictures(answer);
      })
      .catch((error) => {
        console.error('Error loading the year:', error);
        if (current) setFailed(true);
      });
    return () => {
      current = false;
    };
  }, [open, pictures, userId, year]);

  const stories = pictures?.stories ?? [];
  const total = stories.length;
  const step = (by: number) => setIndex((at) => Math.min(Math.max(at + by, 0), Math.max(total - 1, 0)));

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'ArrowRight') setIndex((at) => Math.min(at + 1, Math.max(total - 1, 0)));
      if (event.key === 'ArrowLeft') setIndex((at) => Math.max(at - 1, 0));
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose, total]);

  if (!open || typeof document === 'undefined') return null;

  const story = stories[index];

  const share = () => {
    if (!story) return;
    if (shareToStory(story.url, pictures?.story_text ? { text: pictures.story_text } : undefined)) {
      track(AnalyticsEvent.ShareAnalytics, { picture: story.story, method: 'story' });
    } else {
      showToast(t('analytics.shareUnsupported'));
    }
  };

  const save = () => {
    if (story && downloadFile(downloadAddress(story.url), `split-bill-${year}-${story.story}.jpg`)) {
      track(AnalyticsEvent.ShareAnalytics, { picture: story.story, method: 'download' });
    } else {
      showToast(t('analytics.shareUnsupported'));
    }
  };

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('analytics.yearStories')}
      className="fixed inset-0 z-50 flex flex-col gap-3 bg-bar px-3 pb-[calc(12px+var(--content-safe-bottom))] pt-[calc(10px+var(--content-safe-top))] text-bar-fg"
    >
      <div className="flex items-center gap-2">
        <div className="flex flex-1 gap-1" aria-hidden>
          {stories.map((item, at) => (
            <span key={item.story} className={`h-[3px] flex-1 rounded-full ${at <= index ? 'bg-bar-fg' : 'bg-bar-fg/30'}`} />
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('common.close')}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md opacity-80 hover:opacity-100"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="relative min-h-0 flex-1">
        {failed ? (
          <p className="flex h-full items-center justify-center text-[14px] opacity-80">{t('common.error')}</p>
        ) : !story ? (
          <div className="flex h-full items-center justify-center" aria-hidden>
            <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-accent" />
          </div>
        ) : (
          <>
            {stories.map((item, at) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={item.story}
                src={item.url}
                alt={t(`analytics.story.${item.story}`)}
                aria-hidden={at !== index}
                className={`absolute inset-0 h-full w-full rounded-lg object-contain transition-opacity ${at === index ? 'opacity-100' : 'opacity-0'}`}
              />
            ))}
            <button
              type="button"
              onClick={() => step(-1)}
              disabled={index === 0}
              aria-label={t('analytics.previousStory')}
              className="absolute inset-y-0 left-0 w-1/3"
            />
            <button
              type="button"
              onClick={() => step(1)}
              disabled={index === total - 1}
              aria-label={t('analytics.nextStory')}
              className="absolute inset-y-0 right-0 w-2/3"
            />
            <span className="sr-only" aria-live="polite">
              {t('analytics.storyOf', { index: String(index + 1), total: String(total) })}
            </span>
          </>
        )}
      </div>

      {story && (
        <div className="flex gap-2.5">
          {canShareToStory() && (
            <Button className="flex-1" onClick={share}>
              <Sparkles className="h-[18px] w-[18px]" />
              {t('analytics.shareStory')}
            </Button>
          )}
          {canDownloadFile() && (
            <Button variant="outline" className="flex-1 border-bar-fg/60 text-bar-fg hover:bg-bar-fg/10" onClick={save}>
              <Download className="h-[18px] w-[18px]" />
              {t('analytics.savePicture')}
            </Button>
          )}
          {!canShareToStory() && !canDownloadFile() && (
            <a
              href={story.url}
              target="_blank"
              rel="noreferrer"
              className="flex min-h-[50px] flex-1 items-center justify-center gap-2 rounded-lg border-[1.5px] border-bar-fg/60 font-display text-[15px] font-bold"
            >
              <ExternalLink className="h-[18px] w-[18px]" />
              {t('analytics.openPicture')}
            </a>
          )}
        </div>
      )}
    </div>,
    document.body,
  );
}
