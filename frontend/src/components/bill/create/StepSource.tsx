'use client';

import { useRef, useState } from 'react';
import { Camera, ChevronRight, Image as ImageIcon, ImagePlus, Lock, Mic, PenLine, QrCode, ScanLine } from 'lucide-react';
import CameraCapture from '../CameraCapture';
import { isIOS } from '@/lib/utils/platform';
import { blurBeforeNativeSurface } from '@/hooks/useViewportRestore';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { TourAnchor, type TourAnchorId } from '@/lib/tour/anchors';
import { usePro, useProGate } from '@/lib/store/usePro';
import { useScanAllowance, type ScanAllowance } from '@/hooks/useScanAllowance';
import ProCorner from '@/components/pro/ProCorner';

interface StepSourceProps {
  /** Soliq receipts are denominated in sum, so the QR import is UZS-only. */
  qrAvailable: boolean;
  onPhoto: (file: File) => void;
  onScanQr: () => void;
  /** Creating a bill: start empty and type the items in. */
  onManual?: () => void;
  /** Creating a bill: start empty and say the items and who had them. Pro. */
  onVoice?: () => void;
  /** Adding to a bill: keep the photo, add the lines by hand afterwards. */
  onAttachWithoutScan?: (file: File) => void;
}

interface SourceOptionProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  primary?: boolean;
  disabled?: boolean;
  /** Today's free scans, for a way that spends one; none left opens the paywall instead. */
  allowance?: ScanAllowance | null;
  /** A way only Pro has, for someone without it. */
  locked?: boolean;
  onClick: () => void;
  tourAnchor?: TourAnchorId;
}

/** «2/3» of today's free scans, and a lock once there are none. */
function AllowancePill({ left, total }: ScanAllowance) {
  const { t } = useTranslation();
  const out = left === 0;
  return (
    <span
      aria-label={t('pro.scansLeftOf', { left: String(left), total: String(total) })}
      className={`inline-flex h-6 shrink-0 items-center gap-1 rounded-full border-[1.5px] px-2 font-mono text-[11px] font-bold tabular-nums ${
        out ? 'border-border bg-surface-2 text-muted' : 'border-outline bg-background text-foreground'
      }`}
    >
      {out && <Lock aria-hidden="true" className="h-3 w-3" strokeWidth={2.5} />}
      {left}/{total}
    </span>
  );
}

function SourceOption({
  icon,
  title,
  description,
  primary,
  disabled,
  allowance,
  locked,
  onClick,
  tourAnchor,
}: SourceOptionProps) {
  const { t } = useTranslation();
  const out = allowance?.left === 0;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      data-tour={tourAnchor}
      className={`relative flex w-full items-center gap-3.5 rounded-[10px] border-[1.5px] p-3.5 text-left ${
        disabled ? 'border-border bg-surface-2 opacity-55' : 'btn-hard-sm border-outline bg-surface'
      }`}
    >
      <span
        className={`flex h-[46px] w-[46px] flex-shrink-0 items-center justify-center rounded-[9px] border-[1.5px] border-outline ${
          out ? 'bg-surface-2 text-muted' : primary ? 'bg-accent text-accent-fg' : 'bg-background text-accent'
        }`}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-foreground">{title}</span>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-2">
          {out ? t('pro.scansOutHint') : description}
        </span>
      </span>
      {allowance && <AllowancePill {...allowance} />}
      {(out || locked) && <ProCorner />}
      {!disabled && <ChevronRight className="h-[18px] w-[18px] flex-shrink-0 text-muted-2" />}
    </button>
  );
}

function ChooserRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-surface-2"
    >
      <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-background text-accent">
        {icon}
      </span>
      <span className="font-display text-sm font-bold text-foreground">{label}</span>
    </button>
  );
}

/**
 * Step 3 — how the bill gets its items.
 *
 * Every route ends in the same place, so they're offered side by side instead of
 * one being hidden behind a link: scan a photo, import a fiscal QR, or start
 * empty and type the items on the bill page.
 */
export default function StepSource({
  qrAvailable,
  onPhoto,
  onScanQr,
  onManual,
  onVoice,
  onAttachWithoutScan,
}: StepSourceProps) {
  const { t } = useTranslation();
  const galleryRef = useRef<HTMLInputElement>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  // Where the photo comes from is a question only Android has to be asked: its
  // WebView ignores `capture`, so the OS picker there offers the gallery and
  // nothing else, and the camera is ours to open.
  const [sourceOpen, setSourceOpen] = useState(false);
  // Which handler the next picked file belongs to — the same picker serves both
  // the AI scan and the "keep the photo, no recognition" route.
  const [pickFor, setPickFor] = useState<'scan' | 'attach'>('scan');
  const allowance = useScanAllowance();
  const allowScan = usePro((state) => state.allowScan);
  const voice = useProGate('voice');

  const openPicker = (target: 'scan' | 'attach' = 'scan') => {
    setPickFor(target);
    // Handing the screen to a native surface with a focused field is what leaves
    // the webview zoomed when it comes back.
    blurBeforeNativeSurface();
    galleryRef.current?.click();
  };

  const handlePicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (pickFor === 'attach' && onAttachWithoutScan) onAttachWithoutScan(file);
    else onPhoto(file);
  };

  if (sourceOpen) {
    return (
      <div className="flex flex-col gap-3">
        <input
          ref={galleryRef}
          type="file"
          accept="image/*"
          onChange={handlePicked}
          className="hidden"
        />
        <div className="overflow-hidden rounded-lg border-[1.5px] border-outline bg-surface shadow-[var(--shadow-lifted)]">
          <ChooserRow
            icon={<Camera className="h-[18px] w-[18px]" />}
            label={t('receipt.takePhoto')}
            onClick={() => {
              setSourceOpen(false);
              setPickFor('scan');
              setCameraOpen(true);
            }}
          />
          <div className="border-t-[1.5px] border-dashed border-border" />
          <ChooserRow
            icon={<ImageIcon className="h-[18px] w-[18px]" />}
            label={t('receipt.fromGallery')}
            onClick={() => {
              setSourceOpen(false);
              openPicker('scan');
            }}
          />
          <div className="border-t-[1.5px] border-dashed border-border" />
          <button
            type="button"
            onClick={() => setSourceOpen(false)}
            className="w-full px-4 py-2.5 text-center font-display text-[11px] font-bold uppercase tracking-[0.08em] text-muted-2 transition-colors hover:text-accent"
          >
            {t('common.cancel')}
          </button>
        </div>

        {cameraOpen && (
          <CameraCapture
            onCapture={(file) => {
              setCameraOpen(false);
              onPhoto(file);
            }}
            onClose={() => setCameraOpen(false)}
            onFallback={() => {
              setCameraOpen(false);
              openPicker('scan');
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <input
        ref={galleryRef}
        type="file"
        accept="image/*"
        onChange={handlePicked}
        className="hidden"
      />

      <SourceOption
        primary
        tourAnchor={TourAnchor.ScanReceipt}
        icon={<ScanLine className="h-[21px] w-[21px]" />}
        title={t('receipt.sourceScan')}
        description={t('receipt.sourceScanHint')}
        allowance={allowance}
        onClick={() => {
          if (!allowScan()) return;
          // iOS' native picker already asks Camera or Library, so asking again
          // would be the same question twice.
          if (isIOS()) openPicker('scan');
          else setSourceOpen(true);
        }}
      />

      <SourceOption
        icon={<QrCode className="h-[21px] w-[21px]" />}
        title={t('receipt.scanQr')}
        description={qrAvailable ? t('receipt.sourceQrHint') : t('receipt.sourceQrUzsOnly')}
        disabled={!qrAvailable}
        allowance={qrAvailable ? allowance : null}
        onClick={() => allowScan() && onScanQr()}
      />

      {onVoice && (
        <SourceOption
          icon={<Mic className="h-[21px] w-[21px]" />}
          title={t('voice.sourceTitle')}
          description={t('voice.sourceHint')}
          locked={voice.locked}
          onClick={voice.gated(onVoice)}
        />
      )}

      {onManual && (
        <SourceOption
          icon={<PenLine className="h-[21px] w-[21px]" />}
          title={t('receipt.sourceManual')}
          description={t('receipt.sourceManualHint')}
          onClick={onManual}
        />
      )}

      {onAttachWithoutScan && (
        <SourceOption
          icon={<ImagePlus className="h-[21px] w-[21px]" />}
          title={t('receipt.sourcePlainPhoto')}
          description={t('receipt.sourcePlainPhotoHint')}
          onClick={() => openPicker('attach')}
        />
      )}

      {cameraOpen && (
        <CameraCapture
          onCapture={(file) => {
            setCameraOpen(false);
            onPhoto(file);
          }}
          onClose={() => setCameraOpen(false)}
          onFallback={() => {
            setCameraOpen(false);
            openPicker('scan');
          }}
        />
      )}
    </div>
  );
}
