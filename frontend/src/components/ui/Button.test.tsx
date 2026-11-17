import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import Button from './Button';

describe('Button — the press', () => {
  it('gives the quiet secondary button a shadow to sink onto', () => {
    // It used to carry a big soft shadow and move one pixel on :active, so the
    // one place it is used — «Skip» in the create wizard — read as unpressable
    // next to the hard-shadowed actions around it.
    render(<Button variant="secondary">Skip</Button>);

    expect(screen.getByRole('button', { name: 'Skip' })).toHaveClass('btn-hard-sm');
  });

  it('keeps the secondary button from competing with the step it skips', () => {
    render(<Button variant="secondary">Skip</Button>);

    const skip = screen.getByRole('button', { name: 'Skip' });
    expect(skip.className).toContain('text-muted');
    expect(skip.className).not.toContain('bg-accent');
  });

  it('keeps the sinking variants off the motion scale', () => {
    // .btn-hard-sm / .btn-hard drive the press from CSS. A framer-motion scale
    // on top of that is a second, slower gesture fighting the first.
    render(
      <>
        <Button variant="secondary">Sinks</Button>
        <Button variant="ghost">Flat</Button>
      </>,
    );

    expect(screen.getByRole('button', { name: 'Sinks' })).not.toHaveClass('active:translate-y-px');
    expect(screen.getByRole('button', { name: 'Flat' })).not.toHaveClass('btn-hard-sm');
  });
});
