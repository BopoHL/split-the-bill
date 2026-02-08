'use client';

import { forwardRef } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface ButtonProps extends Omit<HTMLMotionProps<"button">, "children"> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  handwritten?: boolean;
  isLoading?: boolean;
  children?: React.ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className = '',
      variant = 'primary',
      size = 'md',
      handwritten = false,
      isLoading = false,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();
    const baseStyles = 'inline-flex items-center justify-center rounded-lg font-medium transition-all focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';
    
    const variants = {
      primary: 'bg-accent text-white hover:bg-[#ff7a2e] shadow-md hover:shadow-lg',
      secondary: 'bg-accent-light text-ink hover:bg-[#ffc252] shadow-md hover:shadow-lg',
      ghost: 'bg-transparent text-ink hover:bg-paper-highlight',
      outline: 'bg-transparent border-2 border-accent text-accent hover:bg-accent hover:text-white',
    };
    
    const sizes = {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2 text-base',
      lg: 'px-6 py-3 text-lg',
    };
    
    const fontClass = handwritten ? 'font-handwritten' : '';
    
    return (
      <motion.button
        ref={ref}
        className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${fontClass} ${className}`}
        disabled={disabled || isLoading}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        {...props}
      >
        {isLoading ? (
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            <span>{t('common.loading')}</span>
          </div>
        ) : (
          children
        )}
      </motion.button>
    );
  }
);

Button.displayName = 'Button';

export default Button;
