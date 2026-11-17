import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { BillDetail } from '@/types/api';

const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/toast', () => toast);
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string>) => (params ? `${key} ${JSON.stringify(params)}` : key),
  }),
}));
const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));
vi.mock('@/lib/api/bills', () => ({ tellBill: vi.fn(), hearBill: vi.fn() }));

import { hearBill, tellBill } from '@/lib/api/bills';
import VoiceSheet from './VoiceSheet';

const bill = { id: 7 } as BillDetail;
const told = { heard: 'кола 15', added: 1, assigned: 0, held: [], unseated: [], bill };

// jsdom has no microphone, so the sheet opens on typing — the same words, the same request.
const typeAndSend = (words: string) => {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: words } });
  fireEvent.click(screen.getByRole('button', { name: 'voice.send' }));
};

describe('VoiceSheet', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends what was typed, hands the new bill up and closes', async () => {
    vi.mocked(tellBill).mockResolvedValue(told);
    const onClose = vi.fn();
    const onBillUpdate = vi.fn();
    render(<VoiceSheet billId={7} isOpen onClose={onClose} onBillUpdate={onBillUpdate} />);

    typeAndSend('  кола 15 ');

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(tellBill).toHaveBeenCalledWith(7, 'кола 15');
    expect(hearBill).not.toHaveBeenCalled();
    expect(onBillUpdate).toHaveBeenCalledWith(bill);
    expect(toast.showToast).toHaveBeenCalledWith('voice.done {"added":"1","assigned":"0"}', 'success');
    expect(track).toHaveBeenCalledWith('voice_input_sent', { bill_id: 7, input: 'text' });
    expect(track).toHaveBeenCalledWith('voice_input_result', { bill_id: 7, input: 'text', ok: true, added: 1, assigned: 0 });
  });

  it('says what it heard when it could not tell what to change, and stays open', async () => {
    vi.mocked(tellBill).mockRejectedValue({
      response: { status: 422, data: { detail: { code: 'VOICE_NOTHING', heard: 'э-э-э' } } },
    });
    const onClose = vi.fn();
    render(<VoiceSheet billId={7} isOpen onClose={onClose} onBillUpdate={vi.fn()} />);

    typeAndSend('э-э-э');

    expect(await screen.findByRole('alert')).toHaveTextContent('voice.notUnderstood {"heard":"э-э-э"}');
    expect(onClose).not.toHaveBeenCalled();
    expect(track).toHaveBeenCalledWith('voice_input_result', { bill_id: 7, input: 'text', ok: false, reason: 'VOICE_NOTHING' });
  });

  it('says what it left alone because it was paid, and who it could not seat', async () => {
    vi.mocked(tellBill).mockResolvedValue({ ...told, added: 0, held: ['Плов'], unseated: ['Саша'] });
    const onClose = vi.fn();
    render(<VoiceSheet billId={7} isOpen onClose={onClose} onBillUpdate={vi.fn()} />);

    typeAndSend('плов мой, сок Саше');

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast.showToast).toHaveBeenCalledWith('voice.held {"names":"Плов"}. voice.unseated {"names":"Саша"}', 'info');
  });

  it('nothing typed, nothing sent — and no way back to a microphone there is not', () => {
    render(<VoiceSheet billId={7} isOpen onClose={vi.fn()} onBillUpdate={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'voice.send' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'voice.speakInstead' })).toBeNull();
  });
});

describe('VoiceSheet — recording', () => {
  const stopTrack = vi.fn();

  /** A recorder that hands over one chunk when it stops, as browsers do. */
  class FakeRecorder {
    state = 'inactive';
    mimeType = 'audio/webm;codecs=opus';
    ondataavailable: ((event: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    start() {
      this.state = 'recording';
    }
    stop() {
      this.state = 'inactive';
      this.ondataavailable?.({ data: new Blob(['voice'], { type: this.mimeType }) });
      this.onstop?.();
    }
  }

  const microphone = (value: unknown) => Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    microphone({ getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }) });
    vi.mocked(hearBill).mockResolvedValue('кола 15');
    vi.mocked(tellBill).mockResolvedValue(told);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    microphone(undefined);
  });

  const mic = () => screen.getByRole('button', { name: /voice\.(record|stop)/ });
  const recordingStarted = () => screen.findByRole('button', { name: 'voice.stop' });
  const sheet = (onClose = vi.fn()) => render(<VoiceSheet billId={7} isOpen onClose={onClose} onBillUpdate={vi.fn()} />);

  it('held down, records until let go — then shows what it heard while it fills the bill', async () => {
    let finish: (value: typeof told) => void = () => {};
    vi.mocked(tellBill).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    sheet();

    fireEvent.pointerDown(mic());
    await recordingStarted();
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    fireEvent.pointerUp(mic());

    await waitFor(() => expect(tellBill).toHaveBeenCalledWith(7, 'кола 15'));
    const [, recording] = vi.mocked(hearBill).mock.calls[0];
    expect(recording.type).toBe('audio/webm;codecs=opus');
    expect(stopTrack).toHaveBeenCalled();
    expect(screen.getByText('«кола 15»')).toBeInTheDocument();
    expect(screen.getByText('voice.stepFill')).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith('voice_input_sent', { bill_id: 7, input: 'voice' });
    await act(async () => finish(told));
  });

  it('a quick tap keeps it recording until the next tap', async () => {
    sheet();

    fireEvent.pointerDown(mic());
    fireEvent.pointerUp(mic());
    await recordingStarted();
    expect(hearBill).not.toHaveBeenCalled();

    fireEvent.pointerDown(mic());

    await waitFor(() => expect(hearBill).toHaveBeenCalledTimes(1));
  });

  it('throws away a recording cut short by closing the sheet', async () => {
    const onClose = vi.fn();
    sheet(onClose);
    fireEvent.click(mic());
    await recordingStarted();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
    expect(hearBill).not.toHaveBeenCalled();
  });

  it('closed while the microphone is being asked for, leaves it off', async () => {
    let allow: (stream: unknown) => void = () => {};
    microphone({ getUserMedia: vi.fn().mockReturnValue(new Promise((resolve) => { allow = resolve; })) });
    const onClose = vi.fn();
    sheet(onClose);
    fireEvent.pointerDown(mic());

    fireEvent.keyDown(document, { key: 'Escape' });
    await act(async () => allow({ getTracks: () => [{ stop: stopTrack }] }));

    expect(onClose).toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'voice.stop' })).not.toBeInTheDocument();
  });

  it('stops by itself after ninety seconds and sends what it has', async () => {
    sheet();
    fireEvent.click(mic());
    await recordingStarted();

    await act(async () => {
      vi.advanceTimersByTime(90_000);
    });

    await waitFor(() => expect(hearBill).toHaveBeenCalledTimes(1));
  });
});
