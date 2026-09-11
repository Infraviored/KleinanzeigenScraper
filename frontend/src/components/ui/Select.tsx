import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../utils/cn';
import { useTranslation } from '../../hooks/useTranslation';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  className?: string;
  placeholder?: string;
  error?: boolean;
}

export const Select: React.FC<SelectProps> = ({
  value,
  onChange,
  options,
  className = '',
  placeholder = 'Select option...',
  error = false,
}) => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const handleSelect = (val: string) => {
    onChange(val);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={cn('relative w-full shrink-0', className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'w-full flex items-center justify-between bg-bg-input border text-sm rounded-xl px-4 min-h-[44px] text-left text-text-secondary font-semibold cursor-pointer focus:outline-none transition-all shadow-inner focus:ring-2 focus:ring-brand-accent/10',
          error
            ? 'border-status-danger/50 focus:border-status-danger focus:ring-status-danger/10'
            : 'border-border-subtle focus:border-brand-accent',
          isOpen && 'border-brand-accent ring-2 ring-brand-accent/10'
        )}
      >
        <span className={cn(!selectedOption && 'text-text-muted/40')}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown className={cn('h-4 w-4 text-text-muted transition-transform duration-200', isOpen && 'transform rotate-180')} />
      </button>

      {isOpen && (
        <div className="absolute left-0 right-0 mt-2 z-50 bg-bg-surface border border-border-subtle rounded-xl shadow-xl overflow-hidden animate-fade-in max-h-60 overflow-y-auto">
          <div className="py-1">
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleSelect(option.value)}
                className={cn(
                  'w-full text-left px-4 py-3 min-h-[44px] flex items-center text-sm text-text-secondary hover:bg-bg-surface-hover hover:text-text-primary font-semibold transition-colors',
                  option.value === value && 'bg-brand-accent/10 text-brand-accent hover:bg-brand-accent/20'
                )}
              >
                {option.label}
              </button>
            ))}
            {options.length === 0 && (
              <div className="px-4 py-3 text-sm text-text-muted italic">
                {t('common.noOptions')}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
