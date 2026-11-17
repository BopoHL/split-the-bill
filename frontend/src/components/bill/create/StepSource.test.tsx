import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en' };
  return {
    useStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

vi.mock('@/lib/utils/platform', () => ({ isIOS: vi.fn() }));
vi.mock('../CameraCapture', () => ({
  default: () => <div data-testid="camera" />,
}));

import { isIOS } from '@/lib/utils/platform';
import { usePro } from '@/lib/store/usePro';
import type { ProOverview } from '@/types/pro';
import StepSource from './StepSource';

const withScansLeft = (left: number | null) =>
  usePro.setState({
    paywall: null,
    overview: {
      active: left === null,
      until: null,
      trial: false,
      subscription: false,
      plans: [],
      free_scans_per_day: 3,
      scans_left_today: left,
      free_reminders_per_month: 3,
      reminders_left_this_month: left === null ? null : 3,
    } satisfies ProOverview,
  });

const setup = () => {
  const onPhoto = vi.fn();
  render(<StepSource qrAvailable onPhoto={onPhoto} onScanQr={vi.fn()} onManual={vi.fn()} />);
  return onPhoto;
};

const startScan = () => fireEvent.click(screen.getByText('AI scan'));

describe('StepSource — where the photo comes from', () => {
  beforeEach(() => {
    vi.mocked(isIOS).mockReturnValue(false);
    usePro.setState({ overview: null, paywall: null });
  });

  it('asks before opening the camera on Android', () => {
    setup();

    startScan();

    // The OS picker there offers the gallery and nothing else, so the question
    // is ours to ask — going straight to the camera left no way to the gallery.
    expect(screen.getByText(/take a photo/i)).toBeInTheDocument();
    expect(screen.getByText(/from gallery/i)).toBeInTheDocument();
    expect(screen.queryByTestId('camera')).toBeNull();
  });

  it('opens the camera only once it has been asked for', () => {
    setup();
    startScan();

    fireEvent.click(screen.getByText(/take a photo/i));

    expect(screen.getByTestId('camera')).toBeInTheDocument();
  });

  it('reaches the file picker from the gallery option', () => {
    setup();
    startScan();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const click = vi.spyOn(input, 'click');

    fireEvent.click(screen.getByText(/from gallery/i));

    expect(click).toHaveBeenCalled();
  });

  it('backs out of the question without picking anything', () => {
    setup();
    startScan();

    fireEvent.click(screen.getByText(/cancel/i));

    expect(screen.getByText('AI scan')).toBeInTheDocument();
  });

  it('leaves iOS alone — its own picker already asks', () => {
    vi.mocked(isIOS).mockReturnValue(true);
    setup();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const click = vi.spyOn(input, 'click');

    startScan();

    expect(screen.queryByText(/take a photo/i)).toBeNull();
    expect(click).toHaveBeenCalled();
  });
});

describe('StepSource — today’s free scans', () => {
  beforeEach(() => vi.mocked(isIOS).mockReturnValue(false));

  it('shows on both ways that spend one how many are left', () => {
    withScansLeft(2);
    setup();

    expect(screen.getAllByLabelText('Free scans left today: 2 of 3')).toHaveLength(2);
    expect(screen.getAllByText('2/3')).toHaveLength(2);
  });

  it('locks them once none are left, and opens the paywall instead', () => {
    withScansLeft(0);
    setup();

    expect(screen.getAllByText('0/3')).toHaveLength(2);
    expect(screen.getAllByText('Today’s free scans are used up. Unlimited with Pro')).toHaveLength(2);
    startScan();

    expect(usePro.getState().paywall).toBe('scans');
    expect(screen.queryByText(/take a photo/i)).toBeNull();
  });

  it('counts nothing with Pro', () => {
    withScansLeft(null);
    setup();

    expect(screen.queryByText(/\d\/3/)).toBeNull();
  });
});

describe('StepSource — saying the bill', () => {
  const sayIt = () => screen.getByText('Say it out loud').closest('button') as HTMLButtonElement;
  const setupVoice = () => {
    const onVoice = vi.fn();
    render(<StepSource qrAvailable onPhoto={vi.fn()} onScanQr={vi.fn()} onManual={vi.fn()} onVoice={onVoice} />);
    return onVoice;
  };

  it('starts the bill to be said with Pro', () => {
    withScansLeft(null);
    const onVoice = setupVoice();

    fireEvent.click(sayIt());

    expect(onVoice).toHaveBeenCalled();
    expect(sayIt()).not.toHaveTextContent('Pro');
  });

  it('wears Pro’s stamp without it, and opens the paywall on voice instead', () => {
    withScansLeft(2);
    const onVoice = setupVoice();

    expect(sayIt()).toHaveTextContent('Pro');
    fireEvent.click(sayIt());

    expect(onVoice).not.toHaveBeenCalled();
    expect(usePro.getState().paywall).toBe('voice');
  });
});
