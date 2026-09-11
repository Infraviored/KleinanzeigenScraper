import React from 'react';
import { cn } from '../../utils/cn';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:
    | 'primary'
    | 'secondary'
    | 'danger'
    | 'quiet'
    | 'badge'
    | 'icon'
    | 'action-emerald'
    | 'action-sky'
    | 'action-indigo'
    | 'mini-emerald'
    | 'mini-slate';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  loading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  children,
  ...props
}) => {
  const baseStyle = 'inline-flex items-center justify-center font-bold transition-all duration-200 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 shrink-0 select-none';

  const variants: Record<string, string> = {
    primary: 'bg-brand-accent hover:bg-[#f09587] text-white rounded-xl shadow-lg shadow-brand-accent/10 hover:shadow-[#f09587]/20 border border-transparent',
    secondary: 'bg-bg-surface hover:bg-bg-surface-hover border border-border-subtle text-text-secondary hover:text-text-primary rounded-xl',
    danger: 'bg-status-danger/10 hover:bg-status-danger/20 text-status-danger border border-status-danger/30 rounded-xl',
    quiet: 'bg-transparent hover:bg-bg-surface border border-transparent hover:border-border-subtle text-text-muted hover:text-text-primary rounded-xl',
    badge: 'text-text-muted hover:text-text-primary bg-bg-surface hover:bg-bg-surface-hover border border-border-subtle rounded-xl',
    icon: 'rounded-xl bg-bg-surface hover:bg-bg-surface-hover text-text-muted hover:text-brand-accent border border-border-subtle hover:border-border-brand shadow-sm group',
    // Backward-compatible mappings for legacy variant names
    'action-emerald': 'bg-bg-surface hover:bg-bg-surface-hover text-text-muted hover:text-brand-accent border border-border-subtle rounded-xl shadow-sm',
    'action-sky': 'bg-bg-surface hover:bg-bg-surface-hover text-text-muted hover:text-text-primary border border-border-subtle rounded-xl shadow-sm',
    'action-indigo': 'bg-bg-surface hover:bg-bg-surface-hover text-text-muted hover:text-text-primary border border-border-subtle rounded-xl shadow-sm',
    'mini-emerald': 'bg-brand-accent hover:bg-[#f09587] text-white rounded-lg font-bold transition-colors border border-transparent',
    'mini-slate': 'bg-bg-surface hover:bg-bg-surface-hover text-text-secondary rounded-lg transition-colors border border-border-subtle',
  };

  const sizes = {
    xs: 'min-h-[44px] px-3 text-xs rounded-xl gap-1',
    sm: 'min-h-[44px] px-4 text-xs rounded-xl gap-1.5 whitespace-nowrap',
    md: 'min-h-[44px] px-5 text-sm rounded-xl gap-1.5 whitespace-nowrap',
    lg: 'min-h-[44px] px-6 text-base rounded-xl gap-2',
  };

  const isBtnDisabled = disabled || loading;

  // Icon buttons are square with minimum 44x44px touch target
  const finalSizeClass = variant === 'icon' && !props.style?.width && !className.includes('w-')
    ? (size === 'lg' ? 'min-h-[48px] min-w-[48px] p-3' : 'min-h-[44px] min-w-[44px] p-2.5')
    : sizes[size];

  return (
    <button
      className={cn(baseStyle, variants[variant], finalSizeClass, className)}
      disabled={isBtnDisabled}
      {...props}
    >
      {loading && (
        <svg
          className="animate-spin -ml-1 mr-2 h-3.5 w-3.5 text-current shrink-0"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      {children}
    </button>
  );
};

