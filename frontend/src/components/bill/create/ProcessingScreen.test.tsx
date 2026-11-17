import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector?: (s: { language: string }) => unknown) =>
    selector ? selector({ language: 'en' }) : { language: 'en' },
}));

import ProcessingScreen from './ProcessingScreen';

const show = (props: Partial<React.ComponentProps<typeof ProcessingScreen>> = {}) => {
  const onAbort = vi.fn();
  render(
    <ProcessingScreen
      mode="photo"
      phase="llm"
      failed={false}
      onRetry={vi.fn()}
      onFallbackToManual={vi.fn()}
      onAbort={onAbort}
      {...props}
    />,
  );
  return onAbort;
};

describe('ProcessingScreen — leaving a scan that drags on', () => {
  it('shows only the pipeline while the scan is within its normal time', () => {
    show();
    expect(screen.getByText(/filling in the bill/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /abort/i })).toBeNull();
  });

  it('offers the way out under the pipeline once the scan has dragged on', async () => {
    const onAbort = show({ abortable: true });

    await userEvent.click(screen.getByRole('button', { name: /abort/i }));

    expect(onAbort).toHaveBeenCalledTimes(1);
  });

  it('keeps the out to itself where the caller has already moved on', () => {
    render(
      <ProcessingScreen
        mode="photo"
        phase="llm"
        failed={false}
        abortable
        onRetry={vi.fn()}
        onFallbackToManual={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /abort/i })).toBeNull();
  });
});
