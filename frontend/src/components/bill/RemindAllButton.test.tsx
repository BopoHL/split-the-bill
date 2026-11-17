import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/lib/toast', () => toast);
vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import RemindAllButton from './RemindAllButton';

describe('RemindAllButton', () => {
  it('stands out with how many it will remind', () => {
    const onPress = vi.fn();
    render(<RemindAllButton label="Remind everyone" ready={3} busy={false} locked={false} onPress={onPress} />);

    const button = screen.getByRole('button', { name: /Remind everyone/ });
    expect(button).toHaveTextContent(/^Remind everyone3$/);
    expect(button).toHaveClass('bg-accent');
    fireEvent.click(button);
    expect(onPress).toHaveBeenCalled();
  });

  it('wears a lock and Pro’s stamp without Pro, and still opens what the press leads to', () => {
    const onPress = vi.fn();
    render(<RemindAllButton label="Remind everyone" ready={3} busy={false} locked onPress={onPress} />);

    const button = screen.getByRole('button', { name: /Remind everyone/ });
    expect(button).toHaveAccessibleName(/pro\.locked/);
    expect(button.querySelector('.lucide-lock')).not.toBeNull();
    expect(button).not.toHaveTextContent('3');
    fireEvent.click(button);
    expect(onPress).toHaveBeenCalled();
  });

  it('goes quiet once there is nobody to remind', () => {
    render(<RemindAllButton label="Everyone reminded" ready={0} busy={false} locked={false} onPress={vi.fn()} />);

    const button = screen.getByRole('button', { name: 'Everyone reminded' });
    expect(button).toBeDisabled();
    expect(button).not.toHaveClass('bg-accent');
  });

  it('with nobody to remind looks off, and a press says what to do first — even before Pro', () => {
    const onPress = vi.fn();
    render(
      <RemindAllButton label="Remind everyone" ready={0} hint="Assign the items first" busy={false} locked onPress={onPress} />,
    );

    const button = screen.getByRole('button', { name: /Remind everyone/ });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).not.toHaveClass('bg-accent');
    fireEvent.click(button);
    expect(toast.showToast).toHaveBeenCalledWith('Assign the items first', 'info');
    expect(onPress).not.toHaveBeenCalled();
  });

  it('keeps the hint for when there is nobody to wait for either', () => {
    render(
      <RemindAllButton label="Everyone reminded" ready={0} wait="12:00" hint="Assign the items first" busy={false} locked={false} onPress={vi.fn()} />,
    );

    expect(screen.getByRole('button')).toBeDisabled();
  });
});
