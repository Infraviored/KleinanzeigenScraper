import React, { forwardRef } from 'react';
import { cn } from '../../utils/cn';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ error = false, className = '', ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          'bg-bg-input border text-sm rounded-xl px-4 min-h-[44px] focus:outline-none placeholder-text-muted/40 w-full text-text-secondary font-semibold transition-all shadow-inner focus:ring-2 focus:ring-brand-accent/10',
          error
            ? 'border-status-danger/50 focus:border-status-danger focus:ring-status-danger/10'
            : 'border-border-subtle focus:border-brand-accent',
          className
        )}
        {...props}
      />
    );
  }
);

Input.displayName = 'Input';

