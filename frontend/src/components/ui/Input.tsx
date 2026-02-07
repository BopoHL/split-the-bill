'use client';

import { InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  handwritten?: boolean;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', label, error, handwritten = false, ...props }, ref) => {
    const fontClass = handwritten ? 'font-handwritten text-xl' : '';
    
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-ink mb-1">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`
            w-full px-3 py-2
            bg-transparent
            border-b-2 border-accent/40
            text-ink placeholder:text-ink/40
            focus:outline-none focus:border-accent
            transition-colors
            ${fontClass}
            ${error ? 'border-red-500' : ''}
            ${className}
          `}
          {...props}
        />
        {error && (
          <p className="mt-1 text-sm text-red-500">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export default Input;
