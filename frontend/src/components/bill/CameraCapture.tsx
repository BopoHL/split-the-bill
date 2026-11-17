'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { X, Image as ImageIcon } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface CameraCaptureProps {
  /** Called with the captured photo as a JPEG File. */
  onCapture: (file: File) => void;
  /** Close the camera without capturing. */
  onClose: () => void;
  /** Camera unavailable / denied — fall back to the gallery picker. */
  onFallback: () => void;
}

/**
 * In-app camera via getUserMedia — the reliable way to capture a photo inside
 * Telegram's Android WebView, where `<input capture>` is ignored and only opens
 * the gallery. Falls back to the gallery if the camera can't be accessed.
 */
export default function CameraCapture({ onCapture, onClose, onFallback }: CameraCaptureProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState(false);
  const [ready, setReady] = useState(false);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError(true);
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
          setReady(true);
        }
      } catch {
        if (!cancelled) setError(true);
      }
    };
    void start();
    return () => {
      cancelled = true;
      stop();
    };
  }, [stop]);

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        stop();
        onCapture(new File([blob], `receipt-${Date.now()}.jpg`, { type: 'image/jpeg' }));
      },
      'image/jpeg',
      0.92,
    );
  }, [onCapture, stop]);

  // Telegram's own close and menu buttons float over the top of a fullscreen
  // page, and this view is drawn edge to edge under them — so the frame is what
  // fills the screen, and the controls keep clear of the client's chrome.
  return (
    <div className="fixed inset-0 z-[80] flex flex-col bg-black">
      {error ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-5 p-6 text-center">
          <p className="max-w-[260px] text-sm font-medium text-white/80">
            {t('receipt.cameraUnavailable')}
          </p>
          <button
            type="button"
            onClick={() => {
              stop();
              onFallback();
            }}
            className="inline-flex items-center gap-2 rounded-lg border-[1.5px] border-white bg-white/10 px-5 py-3 font-display text-[14px] font-bold text-white"
          >
            <ImageIcon className="h-[18px] w-[18px]" />
            {t('receipt.fromGallery')}
          </button>
          <button
            type="button"
            onClick={() => {
              stop();
              onClose();
            }}
            className="text-[13px] font-medium text-white/60"
          >
            {t('common.cancel')}
          </button>
        </div>
      ) : (
        <>
          <video ref={videoRef} playsInline muted className="h-full w-full object-cover" />

          <button
            type="button"
            onClick={() => {
              stop();
              onClose();
            }}
            aria-label={t('common.cancel')}
            style={{
              top: 'calc(1rem + var(--content-safe-top))',
              right: 'calc(1rem + var(--content-safe-right))',
            }}
            className="absolute flex h-10 w-10 items-center justify-center rounded-full bg-black/45 text-white"
          >
            <X className="h-5 w-5" />
          </button>

          <div
            style={{ paddingBottom: 'calc(2.25rem + var(--content-safe-bottom))' }}
            className="absolute inset-x-0 bottom-0 flex justify-center pt-6"
          >
            <button
              type="button"
              onClick={capture}
              disabled={!ready}
              aria-label={t('receipt.capture')}
              className="h-[70px] w-[70px] rounded-full border-4 border-white bg-white/25 transition-transform active:scale-95 disabled:opacity-40"
            />
          </div>
        </>
      )}
    </div>
  );
}
