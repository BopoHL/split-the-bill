'use client';

import { useEffect, useState } from 'react';
import { Download, ExternalLink, Send } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import type { AnalyticsPeriodQuery } from '@/types/analytics';
import { getAnalyticsPictures, prepareAnalyticsShare } from '@/lib/api/analytics';
import { canShareMessage, shareMessage } from '@/lib/telegram/share';
import { canDownloadFile, downloadFile } from '@/lib/telegram/media';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { downloadAddress, periodLabel } from '@/lib/utils/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';

/**
 * The period's report receipt as the server draws it, and the ways to pass it
 * on: to a chat as a photo, or saved to the phone. Its address is asked for
 * once the sheet first opens.
 */
export default function ReportSheet({ userId, period, open, onClose }: {
  userId: number;
  period: AnalyticsPeriodQuery;
  open: boolean;
  onClose: () => void;
}) {
  const { t, language } = useTranslation();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [shown, setShown] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!open || url) return;
    let current = true;
    getAnalyticsPictures(userId, period)
      .then((pictures) => {
        if (current) setUrl(pictures.receipt);
      })
      .catch((error) => {
        console.error('Error loading the report:', error);
        if (current) setFailed(true);
      });
    return () => {
      current = false;
    };
  }, [open, url, userId, period]);

  const send = async () => {
    if (sending) return;
    setSending(true);
    try {
      const preparedId = await prepareAnalyticsShare(userId, period);
      if (shareMessage(preparedId)) track(AnalyticsEvent.ShareAnalytics, { picture: 'receipt', method: 'message' });
      else showToast(t('analytics.shareUnsupported'));
    } catch (error) {
      console.error('Error sharing the report:', error);
      showToast(t('common.error'));
    } finally {
      setSending(false);
    }
  };

  const save = () => {
    if (url && downloadFile(downloadAddress(url), 'split-bill-report.jpg')) {
      track(AnalyticsEvent.ShareAnalytics, { picture: 'receipt', method: 'download' });
    } else {
      showToast(t('analytics.shareUnsupported'));
    }
  };

  const canSend = canShareMessage();
  const canSave = canDownloadFile();

  return (
    <Modal isOpen={open} onClose={onClose} title={t('analytics.reportTitle')}>
      {failed ? (
        <p className="py-10 text-center text-[14px] text-muted">{t('common.error')}</p>
      ) : (
        <>
          <div className="relative min-h-[320px]">
            {!shown && (
              <div className="absolute inset-0 flex items-center justify-center" aria-hidden>
                <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-accent" />
              </div>
            )}
            {url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={url}
                alt={t('analytics.reportAlt', { period: periodLabel(period, language, t) })}
                onLoad={() => setShown(true)}
                onError={() => setFailed(true)}
                className={`block h-auto w-full transition-opacity ${shown ? 'opacity-100' : 'opacity-0'}`}
              />
            )}
          </div>
          <div className="sticky -bottom-5 -mx-5 -mb-5 mt-4 flex gap-2.5 border-t-[1.5px] border-border bg-surface px-5 py-3">
            {canSend && (
              <Button className="flex-1" onClick={() => void send()} isLoading={sending} disabled={!url}>
                <Send className="h-[18px] w-[18px]" />
                {t('analytics.sendToChat')}
              </Button>
            )}
            {canSave && (
              <Button variant="outline" className="flex-1" onClick={save} disabled={!url}>
                <Download className="h-[18px] w-[18px]" />
                {t('analytics.savePicture')}
              </Button>
            )}
            {!canSend && !canSave && url && (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="flex min-h-[50px] flex-1 items-center justify-center gap-2 rounded-lg border-[1.5px] border-outline font-display text-[15px] font-bold text-foreground"
              >
                <ExternalLink className="h-[18px] w-[18px]" />
                {t('analytics.openPicture')}
              </a>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
