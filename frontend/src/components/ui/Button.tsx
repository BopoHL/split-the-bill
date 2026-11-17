'use client';

import { forwardRef } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface ButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger' | 'success';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  /** Disable the tactile scale-on-press when the motion would be distracting. */
  static?: boolean;
  children?: React.ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className = '',
      variant = 'primary',
      size = 'md',
      isLoading = false,
      static: isStatic = false,
      disabled,
      children,
      ...props
    },
    ref,
  ) => {
    const { t } = useTranslation();
    // «Bold» ticket look: 1.5px ink border + hard offset shadow on the solid
    // actions; flat ghost/danger for subtle ones. Display typeface, bold.
    const base =
      'inline-flex items-center justify-center gap-2 rounded-lg font-display font-bold leading-none transition-[transform,box-shadow,background-color] disabled:opacity-50 disabled:cursor-not-allowed';

    // Solid variants carry the hard offset shadow and «sink» into it on press
    // (translate + shadow removal live in the shared .btn-hard CSS).
    const variants = {
      primary: 'border-[1.5px] border-outline bg-accent text-accent-fg btn-hard hover:bg-accent-hover',
      success: 'border-[1.5px] border-outline bg-success text-success-fg btn-hard',
      // The quiet one: a way past a step, not an action competing with it. Grey
      // and small, but it still presses like everything else here — the hard
      // shadow snaps off under it.
      secondary:
        'border-[1.5px] border-border bg-surface text-muted btn-hard-sm hover:border-outline hover:text-foreground',
      outline: 'border-[1.5px] border-outline bg-transparent text-foreground hover:bg-surface-2',
      ghost: 'bg-transparent text-foreground hover:bg-surface-2',
      danger: 'bg-transparent text-danger hover:bg-danger/10',
    };

    // Comfortable mobile tap targets — md/lg clear the 44px guideline.
    const sizes = {
      sm: 'min-h-[44px] px-4 py-2.5 text-[13px]',
      md: 'min-h-[50px] px-[18px] py-3 text-[15px]',
      lg: 'min-h-[58px] px-6 py-4 text-base',
    };

    // Shadowed variants sink onto their own shadow via pure CSS (.btn-hard /
    // .btn-hard-sm :active) so the press is the crisp keypad feel — transform
    // eases, shadow snaps off instantly. Flat variants (no shadow to fall onto)
    // keep the subtle motion scale instead; on a sinking button the two read as
    // one mushy gesture and cancel each other out.
    const sinks = variant === 'primary' || variant === 'success' || variant === 'secondary';
    const whileTap = isStatic || disabled || isLoading || sinks ? undefined : { scale: 0.96 };

    return (
      <motion.button
        ref={ref}
        className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
        disabled={disabled || isLoading}
        whileTap={whileTap}
        {...props}
      >
        {isLoading ? (
          <>
            <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            <span>{t('common.loading')}</span>
          </>
        ) : (
          children
        )}
      </motion.button>
    );
  },
);

Button.displayName = 'Button';

export default Button;
