'use client';

import { useCallback, useEffect } from 'react';
import Modal from '@/components/ui/Modal';
import StepSource from '@/components/bill/create/StepSource';
import ProcessingScreen from '@/components/bill/create/ProcessingScreen';
import { useReceiptScan } from '@/components/bill/create/useReceiptScan';
import { receiptsApi } from '@/lib/api/receipts';
import { compressImage } from '@/lib/utils/image';
import { scanQrCode, closeQrScanner, hapticFeedback } from '@/lib/telegram/init';
import { parseSoliqUrl } from '@/lib/utils/soliq';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { usePro } from '@/lib/store/usePro';
import { useTranslation } from '@/lib/i18n/useTranslation';
import type { Currency } from '@/lib/utils/currency';

interface AddReceiptDialogProps {
  isOpen: boolean;
  billId: number;
  currency?: Currency;
  userId?: number;
  /** Opened from the bot's scan link: go straight for the camera. */
  autoScan?: boolean;
  onClose: () => void;
  onAdded: () => void;
}

/**
 * Adding a receipt to an open bill.
 *
 * A sheet rather than its own screen: it is one short choice made while looking
 * at the bill, and a full page navigation threw the bill away and back for it.
 * The scan itself keeps running after the sheet closes — progress shows on the
 * receipt card.
 */
export default function AddReceiptDialog({
  isOpen,
  billId,
  currency,
  userId,
  autoScan = false,
  onClose,
  onAdded,
}: AddReceiptDialogProps) {
  const { t } = useTranslation();

  const finish = useCallback(() => {
    onAdded();
    onClose();
  }, [onAdded, onClose]);

  // Closing as soon as the scan starts: the bill already shows this receipt as a
  // card with its own spinner, so a full-screen pipeline on top of it says the
  // same thing twice and hides the bill while it runs.
  const scan = useReceiptScan({
    userId,
    billId,
    onScanned: onAdded,
    onStarted: finish,
  });

  const handleScanQr = useCallback(() => {
    const started = scanQrCode((text) => {
      const url = parseSoliqUrl(text);
      if (url) {
        closeQrScanner();
        scan.scanQr(url);
        return true;
      }
      hapticFeedback('error');
      return false;
    }, t('receipt.scanQrHint'));
    if (!started) showToast(t('receipt.qrUnsupported'));
  }, [scan, t]);

  // Clients without a scanner (desktop, web) fall back on their own: the
  // sheet stays open on the photo option and says the scanner is unavailable.
  const allowScan = usePro((state) => state.allowScan);
  useEffect(() => {
    if (isOpen && autoScan && allowScan()) handleScanQr();
  }, [isOpen, autoScan, allowScan, handleScanQr]);

  const attachWithoutScan = async (file: File) => {
    if (!userId) return;
    try {
      await receiptsApi.attachToBill(billId, await compressImage(file), userId);
      track(AnalyticsEvent.ReceiptAttached, { bill_id: billId });
      finish();
    } catch {
      showToast(t('common.error'));
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('receipt.addReceipt')} size="sm">
      {scan.failed ? (
        <ProcessingScreen
          mode={scan.mode}
          phase={scan.phase}
          failed
          onRetry={scan.retry}
          onFallbackToManual={onClose}
        />
      ) : (
        <StepSource
          qrAvailable={(currency ?? 'uzs') === 'uzs'}
          onPhoto={scan.scanPhoto}
          onScanQr={handleScanQr}
          onAttachWithoutScan={attachWithoutScan}
        />
      )}
    </Modal>
  );
}
