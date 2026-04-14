import { HTMLAttributes, forwardRef, ReactNode } from 'react';

type BadgeVariant = 'configured' | 'missing' | 'running' | 'error';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant: BadgeVariant;
  label: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  configured: 'bg-accent border-[2px] border-base text-base',
  missing: 'bg-white border-[2px] border-muted text-muted opacity-50',
  running: 'bg-accent border-[2px] border-base text-base',
  error: 'bg-error text-white border-[2px] border-error',
};

const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ variant, label, className = '', ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={`inline-flex items-center gap-1.5 font-black uppercase tracking-widest text-[10px] px-2 py-1 rounded-none ${variantClasses[variant]} ${className}`}
        {...props}
      >
        {variant === 'running' && (
          <span className="inline-block w-2 h-2 bg-base animate-sharp-blink" />
        )}
        {label}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export default Badge;
