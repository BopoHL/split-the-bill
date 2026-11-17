'use client';

import { InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', label, error, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="mb-1.5 block font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`
            w-full px-3.5 py-2.5
            bg-background rounded-md
            border-[1.5px] border-outline
            font-mono text-[15px] font-semibold
            text-foreground placeholder:font-normal placeholder:text-muted-2
            focus:outline-none focus:border-accent
            transition-colors
            ${error ? 'border-danger focus:border-danger' : ''}
            ${className}
          `}
          {...props}
        />
        {error && <p className="mt-1.5 text-xs font-medium text-danger">{error}</p>}
      </div>
    );
  },
);

Input.displayName = 'Input';

export default Input;
