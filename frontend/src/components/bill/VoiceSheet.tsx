'use client';

import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Keyboard, Mic, Square } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import PipelineSteps from '@/components/ui/PipelineSteps';
import ProCorner from '@/components/pro/ProCorner';
import { hearBill, tellBill } from '@/lib/api/bills';
import { isPaymentRequired } from '@/lib/api/client';
import { useProGate } from '@/lib/store/usePro';
import { translateApiError } from '@/lib/utils/apiError';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import type { BillDetail } from '@/types/api';

/** Long enough to say a dinner; a recorder left on stops by itself. */
const MAX_SECONDS = 90;
/** Held at least this long, the mic records until it is let go; a shorter
 *  press is a tap, and the next tap ends the recording. */
const HOLD_MS = 350;

type Stage = 'idle' | 'recording' | 'hearing' | 'filling';

interface VoiceSheetProps {
  billId: number;
  isOpen: boolean;
  onClose: () => void;
  onBillUpdate: (bill: BillDetail) => void;
}

/** Telegram Desktop and older webviews have no microphone to give. */
const canRecord = () =>
  typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

/** The round mic over the bill's dock that opens the sheet; Pro's stamp without Pro. */
export function VoiceButton({ onPress }: { onPress: () => void }) {
  const { t } = useTranslation();
  const { locked, gated } = useProGate('voice');
  return (
    <motion.button
      type="button"
      onClick={gated(onPress)}
      aria-label={t('voice.title')}
      className="btn-hard pointer-events-auto relative flex h-[60px] w-[60px] items-center justify-center rounded-full border-[1.5px] border-outline bg-accent text-accent-fg"
      whileTap={{ x: 3, y: 4 }}
      transition={{ x: { duration: 0 }, y: { duration: 0 } }}
    >
      <Mic className="h-7 w-7" strokeWidth={2.25} />
      {locked && <ProCorner />}
    </motion.button>
  );
}

/**
 * The owner says what was ordered and who had it: the recording is heard, the
 * words are shown, and the server adds the lines and hands them out. Where the
 * phone can't record, the same words are typed. The recording is never kept.
 */
export default function VoiceSheet({ billId, isOpen, onClose, onBillUpdate }: VoiceSheetProps) {
  const { t } = useTranslation();
  const calm = useReducedMotion();
  const [stage, setStage] = useState<Stage>('idle');
  const [typing, setTyping] = useState(() => !canRecord());
  const [text, setText] = useState('');
  const [heard, setHeard] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [problem, setProblem] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pressedAtRef = useRef(0);
  // A recording cut short by closing the sheet is thrown away, not sent.
  const keepRef = useRef(true);

  const release = () => {
    if (tickRef.current) clearInterval(tickRef.current);
    tickRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };
  const stop = () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  };
  const discard = () => {
    keepRef.current = false;
    stop();
    release();
  };

  // Leaving mid-recording drops it; the recorder's stop lets the microphone go.
  useEffect(() => {
    const recorder = recorderRef;
    const keep = keepRef;
    return () => {
      keep.current = false;
      if (recorder.current?.state === 'recording') recorder.current.stop();
    };
  }, []);

  const busy = stage === 'hearing' || stage === 'filling';

  const close = () => {
    if (busy) return;
    discard();
    setStage('idle');
    setProblem(null);
    setHeard(null);
    onClose();
  };

  const fail = (input: 'voice' | 'text', error: unknown) => {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    const { code, heard: understood } = (typeof detail === 'object' && detail ? detail : {}) as { code?: string; heard?: string };
    track(AnalyticsEvent.VoiceInputResult, { bill_id: billId, input, ok: false, reason: code ?? 'request_error' });
    setStage('idle');
    // The paywall opens over a refusal for want of Pro; this sheet has nothing to add.
    if (isPaymentRequired(error)) {
      onClose();
      return;
    }
    setProblem(understood ? t('voice.notUnderstood', { heard: understood }) : translateApiError(detail, t));
  };

  const fill = async (words: string, input: 'voice' | 'text') => {
    setHeard(words);
    setStage('filling');
    try {
      const told = await tellBill(billId, words);
      onBillUpdate(told.bill);
      track(AnalyticsEvent.VoiceInputResult, {
        bill_id: billId, input, ok: true, added: told.added, assigned: told.assigned,
      });
      // What was left alone, and why, is said along with what was done.
      const changed = told.added > 0 || told.assigned > 0;
      const notes = [
        changed && t('voice.done', { added: String(told.added), assigned: String(told.assigned) }),
        told.held.length > 0 && t('voice.held', { names: told.held.join(', ') }),
        told.unseated.length > 0 && t('voice.unseated', { names: told.unseated.join(', ') }),
      ].filter(Boolean);
      if (notes.length > 0) showToast(notes.join('. '), changed ? 'success' : 'info');
      setText('');
      setHeard(null);
      setStage('idle');
      onClose();
    } catch (error) {
      fail(input, error);
    }
  };

  const hear = async (recording: Blob) => {
    setProblem(null);
    setHeard(null);
    setStage('hearing');
    track(AnalyticsEvent.VoiceInputSent, { bill_id: billId, input: 'voice' });
    let words: string;
    try {
      words = await hearBill(billId, recording);
    } catch (error) {
      fail('voice', error);
      return;
    }
    await fill(words, 'voice');
  };

  const send = (words: string) => {
    setProblem(null);
    track(AnalyticsEvent.VoiceInputSent, { bill_id: billId, input: 'text' });
    void fill(words, 'text');
  };

  const record = async () => {
    setProblem(null);
    keepRef.current = true;
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setTyping(true);
      setProblem(t('voice.micUnavailable'));
      return;
    }
    if (!keepRef.current) {
      // Closed while the microphone was being asked for: it must not stay on.
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const recorder = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    recorder.onstop = () => {
      release();
      if (keepRef.current) void hear(new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type }));
    };
    streamRef.current = stream;
    recorderRef.current = recorder;
    recorder.start();
    const startedAt = Date.now();
    setSeconds(0);
    setStage('recording');
    tickRef.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      setSeconds(elapsed);
      if (elapsed >= MAX_SECONDS) stop();
    }, 250);
  };

  const recording = stage === 'recording';

  // Pressed: recording starts at once, whether the finger stays or not.
  const press = (event: PointerEvent<HTMLButtonElement>) => {
    if (recording) {
      stop();
      return;
    }
    if (stage !== 'idle') return;
    // The finger may slide off while held; the release still comes here.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    pressedAtRef.current = Date.now();
    void record();
  };
  const lift = () => {
    if (pressedAtRef.current && Date.now() - pressedAtRef.current >= HOLD_MS) stop();
    pressedAtRef.current = 0;
  };

  return (
    <Modal isOpen={isOpen} onClose={close} title={t('voice.title')} size="sm">
      {busy ? (
        <PipelineSteps
          current={stage === 'hearing' ? 0 : 1}
          steps={[
            { key: 'hear', label: t('voice.stepHear'), detail: heard && `«${heard}»` },
            { key: 'fill', label: t('voice.stepFill') },
            { key: 'done', label: t('receipt.stepDone') },
          ]}
        />
      ) : typing ? (
        <form
          className="space-y-3"
          data-no-swipe
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim()) send(text.trim());
          }}
        >
          <label htmlFor="voice-text" className="sr-only">{t('voice.title')}</label>
          <textarea
            id="voice-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={2000}
            rows={4}
            placeholder={t('voice.placeholder')}
            className="w-full resize-none rounded-[6px] border-[1.5px] border-outline bg-background px-3 py-2.5 font-display text-[14px] outline-none focus:border-accent"
          />
          <Button type="submit" className="w-full" disabled={!text.trim()}>
            {t('voice.send')}
          </Button>
        </form>
      ) : (
        <div className="flex flex-col items-center gap-3 py-2">
          <div className="relative">
            {recording && !calm && (
              <motion.span
                aria-hidden="true"
                className="absolute inset-0 rounded-full bg-accent/30"
                animate={{ scale: [1, 1.35], opacity: [0.6, 0] }}
                transition={{ duration: 1.2, repeat: Infinity, ease: 'easeOut' }}
              />
            )}
            <motion.button
              type="button"
              whileTap={{ scale: 0.94 }}
              onPointerDown={press}
              onPointerUp={lift}
              onPointerCancel={lift}
              // A click with no pointer behind it is the keyboard's.
              onClick={(event) => {
                if (event.detail !== 0) return;
                if (recording) stop();
                else void record();
              }}
              onContextMenu={(event) => event.preventDefault()}
              aria-label={recording ? t('voice.stop') : t('voice.record')}
              className="btn-hard-sm relative flex h-24 w-24 touch-none select-none items-center justify-center rounded-full border-[1.5px] border-outline bg-accent text-accent-fg"
            >
              {recording ? <Square className="h-8 w-8 fill-current" /> : <Mic className="h-10 w-10" />}
            </motion.button>
          </div>
          <p className="h-5 font-mono text-[13px] font-bold tabular-nums text-foreground" aria-live="polite">
            {recording && clock(seconds)}
          </p>
        </div>
      )}

      {problem && <p role="alert" className="mt-3 text-center text-[12px] leading-relaxed text-danger [overflow-wrap:anywhere]">{problem}</p>}

      {stage === 'idle' && (!typing || canRecord()) && (
        <button
          type="button"
          onClick={() => {
            setProblem(null);
            setTyping(!typing);
          }}
          aria-label={typing ? t('voice.speakInstead') : t('voice.typeInstead')}
          className="mx-auto mt-3 flex h-10 w-10 items-center justify-center rounded-full text-muted-2 transition-colors hover:text-accent"
        >
          {typing ? <Mic className="h-5 w-5" /> : <Keyboard className="h-5 w-5" />}
        </button>
      )}
    </Modal>
  );
}
