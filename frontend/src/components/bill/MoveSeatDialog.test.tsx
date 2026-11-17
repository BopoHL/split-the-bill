import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/store/useStore', () => ({
  useStore: (selector?: (s: { language: string }) => unknown) =>
    selector ? selector({ language: 'en' }) : { language: 'en' },
}));

import MoveSeatDialog from './MoveSeatDialog';

describe('MoveSeatDialog', () => {
  it('says what a move costs before anyone agrees to it', () => {
    render(<MoveSeatDialog isOpen onCancel={vi.fn()} onConfirm={vi.fn()} />);

    // The consequence, not just the question: the dishes are what changes.
    expect(screen.getByText(/items assigned to you will be replaced/i)).toBeInTheDocument();
  });

  it('moves only on an explicit yes, and backing out changes nothing', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<MoveSeatDialog isOpen onCancel={onCancel} onConfirm={onConfirm} />);

    await userEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: /yes, move/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('stays out of the way until the server asks for it', () => {
    render(<MoveSeatDialog isOpen={false} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByText(/items assigned to you will be replaced/i)).toBeNull();
  });
});
