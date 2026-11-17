'use client';

import { useEffect, useRef, useState } from 'react';
import { compressImage } from '@/lib/utils/image';
import { receiptsApi, type ReceiptTaskResponse } from '@/lib/api/receipts';
import { requestSseTicket } from '@/lib/api/auth';
import { track, AnalyticsEvent } from '@/lib/analytics';
import type { Currency } from '@/lib/utils/currencyCatalog';
import { isPaymentRequired } from '@/lib/api/client';
import { usePro } from '@/lib/store/usePro';

/** How long a single phase may take before the scan is called dead.
 *
 *  Per phase rather than for the whole scan: OCR answers in about a second,
 *  but the model regularly spends half a minute on a long receipt. One clock
 *  covering both was firing while the model's answer was still in flight — the
 *  worker then finished, found the task cancelled, and threw a good parse away. */
const PHASE_TIMEOUT_MS = 90000;

/** When a scan that is still running offers a way out of itself. Long enough
 *  that an ordinary scan never shows it, short enough that nobody is left
 *  watching a stuck pipeline with no way back to the bill. */
const ABORT_OFFER_MS = 30000;

export type ScanMode = 'photo' | 'qr';
export type ScanPhase = 'creating' | 'ocr' | 'llm';

interface UseReceiptScanArgs {
  userId?: number;
  expectedPeople?: number;
  paymentDetails?: string;
  currency?: Currency;
  /** Set when scanning INTO an existing bill — it adds another receipt to it. */
  billId?: number;
  onScanned: (billId: number) => void;
  /** Adding to an existing bill doesn't need to be watched: the caller can
   *  leave straight away and follow the progress on the receipt card. */
  onStarted?: () => void;
}

/**
 * Owns the life of a receipt scan: upload, the status stream, the timeout and
 * the retry. Photo and QR share it — the worker reports the same statuses for
 * both, only the step labels differ.
 */
export function useReceiptScan({
  userId,
  expectedPeople,
  paymentDetails,
  currency,
  billId,
  onScanned,
  onStarted,
}: UseReceiptScanArgs) {
  const [running, setRunning] = useState(false);
  const [mode, setMode] = useState<ScanMode>('photo');
  const [phase, setPhase] = useState<ScanPhase>('creating');
  const [failed, setFailed] = useState(false);
  /** The scan has run long enough to be worth offering an out. */
  const [abortable, setAbortable] = useState(false);

  const esRef = useRef<EventSource | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortOfferRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const taskIdRef = useRef<number | null>(null);
  const retryRef = useRef<() => void>(() => {});
  // Which scan the async steps belong to. Bumped by every start and by an
  // abort, so an upload that comes back after the person has walked away is
  // recognised as stale and its task dropped instead of streamed.
  const generationRef = useRef(0);

  const cleanup = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = null;
    if (abortOfferRef.current) clearTimeout(abortOfferRef.current);
    abortOfferRef.current = null;
    esRef.current?.close();
    esRef.current = null;
  };

  /** Tell the worker to drop a scan nobody is waiting for any more, so it
   *  doesn't finish into an orphan bill. */
  const dropTask = () => {
    if (taskIdRef.current) void receiptsApi.cancelTask(taskIdRef.current).catch(() => {});
  };

  // Stop any in-flight scan when the wizard unmounts.
  useEffect(() => cleanup, []);

  const target = billId ? 'existing_bill' : 'new_bill';

  const begin = (next: ScanMode) => {
    generationRef.current += 1;
    track(AnalyticsEvent.ReceiptScanStarted, { mode: next, target });
    setMode(next);
    setRunning(true);
    // The bill is created during the upload request, so «creating» is what the
    // user sees first; the later phases come from the stream.
    setPhase('creating');
    setFailed(false);
    setAbortable(false);
    cleanup();
  };

  /** Give the phase that just started a full clock of its own. */
  const armPhaseTimeout = (scanMode: ScanMode) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      cleanup();
      // Cancel the worker so it doesn't create an orphan bill later.
      dropTask();
      track(AnalyticsEvent.ReceiptScanResult, { mode: scanMode, target, ok: false, reason: 'timeout' });
      setFailed(true);
    }, PHASE_TIMEOUT_MS);
  };

  /** True when the scan this step belongs to is still the one being watched. */
  const stillWanted = (generation: number) => generation === generationRef.current;

  /** The upload has answered for a scan nobody is waiting for any more. */
  const dropStaleTask = (task: ReceiptTaskResponse) => {
    void receiptsApi.cancelTask(task.id).catch(() => {});
  };

  const attachStream = async (
    task: ReceiptTaskResponse,
    scanMode: ScanMode,
    generation: number,
  ) => {
    taskIdRef.current = task.id;
    setPhase('ocr');

    onStarted?.();

    armPhaseTimeout(scanMode);
    // A scan still going after this long isn't failed — the model may simply be
    // slow — but the person watching it gets a button out of here.
    abortOfferRef.current = setTimeout(() => setAbortable(true), ABORT_OFFER_MS);

    // EventSource cannot send the identity header, so the stream is opened with
    // a one-shot ticket.
    let ticket: string;
    try {
      ticket = await requestSseTicket('receipt_task', task.id);
    } catch {
      track(AnalyticsEvent.ReceiptScanResult, {
        mode: scanMode,
        target,
        ok: false,
        reason: 'stream_error',
      });
      cleanup();
      setFailed(true);
      return;
    }
    if (!stillWanted(generation)) {
      dropStaleTask(task);
      return;
    }

    const es = new EventSource(receiptsApi.getStreamUrl(task.id, ticket));
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as { status: string; bill_id: number | null };
        if (data.status === 'completed' && data.bill_id) {
          track(AnalyticsEvent.ReceiptScanResult, { mode: scanMode, target, ok: true });
          if (!billId) track(AnalyticsEvent.BillCreated, { source: scanMode, bill_id: data.bill_id });
          cleanup();
          onScanned(data.bill_id);
        } else if (data.status === 'failed' || data.status === 'cancelled') {
          track(AnalyticsEvent.ReceiptScanResult, {
            mode: scanMode,
            target,
            ok: false,
            reason: data.status,
          });
          cleanup();
          setFailed(true);
        } else if (data.status === 'structuring') {
          setPhase('llm');
          // The model is the slow step and a step of its own, so it starts on a
          // full clock instead of whatever the OCR phase left over.
          armPhaseTimeout(scanMode);
        } else {
          setPhase('ocr');
        }
      } catch {
        /* ignore malformed frames */
      }
    };

    es.onerror = () => {
      track(AnalyticsEvent.ReceiptScanResult, {
        mode: scanMode,
        target,
        ok: false,
        reason: 'stream_error',
      });
      // The server would finish the scan anyway, and «Retry» would make it a
      // second bill from the same receipt.
      dropTask();
      cleanup();
      setFailed(true);
    };
  };

  /** Give up on a scan by hand. Cancelling it server-side takes the still-empty
   *  provisional bill with it, so an abandoned scan leaves nothing behind. */
  const abort = () => {
    generationRef.current += 1;
    cleanup();
    dropTask();
    track(AnalyticsEvent.ReceiptScanResult, { mode, target, ok: false, reason: 'aborted' });
    taskIdRef.current = null;
    setAbortable(false);
    setRunning(false);
  };

  const onUploaded = (scanMode: ScanMode, generation: number) => (task: ReceiptTaskResponse) => {
    // One of today's free scans is spent; what is left is the server's to say.
    if (userId) void usePro.getState().load(userId);
    if (stillWanted(generation)) void attachStream(task, scanMode, generation);
    else dropStaleTask(task);
  };

  /** A refusal for want of free scans is not a failed scan: the paywall opens
   *  over it, and closing that leaves the person where they chose the source. */
  const onUploadFailed = (scanMode: ScanMode, generation: number) => (error: unknown) => {
    if (!stillWanted(generation)) return;
    if (isPaymentRequired(error)) {
      track(AnalyticsEvent.ReceiptScanResult, { mode: scanMode, target, ok: false, reason: 'scan_limit' });
      setRunning(false);
      return;
    }
    track(AnalyticsEvent.ReceiptScanResult, { mode: scanMode, target, ok: false, reason: 'upload_error' });
    setFailed(true);
  };

  const scanPhoto = (file: File) => {
    retryRef.current = () => scanPhoto(file);
    begin('photo');
    const generation = generationRef.current;
    // Re-encode on the device first so the upload is small — a multi-MB photo
    // over a mobile uplink otherwise stalls. compressImage falls back to the
    // original if it can't shrink it.
    compressImage(file)
      .then((compressed) =>
        receiptsApi.upload(compressed, userId, expectedPeople, paymentDetails, billId, currency),
      )
      .then(onUploaded('photo', generation))
      .catch(onUploadFailed('photo', generation));
  };

  const scanQr = (qrUrl: string) => {
    retryRef.current = () => scanQr(qrUrl);
    begin('qr');
    const generation = generationRef.current;
    receiptsApi
      .uploadQr(qrUrl, userId, expectedPeople, paymentDetails, billId)
      .then(onUploaded('qr', generation))
      .catch(onUploadFailed('qr', generation));
  };

  return {
    running,
    mode,
    phase,
    failed,
    abortable,
    scanPhoto,
    scanQr,
    abort,
    retry: () => retryRef.current(),
  };
}
