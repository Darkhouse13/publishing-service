import { HTMLAttributes, forwardRef, ReactNode } from 'react';

/* ----------------------------------------------------------------
   StatCard — Neo-Brutalist Big Number Dashboard Card
   - Large number display (text-5xl font-black)
   - Subtitle text in muted color
   - shadow-solid-md card wrapper with hover lift
   - Zero border-radius, 3px borders
   ---------------------------------------------------------------- */

interface StatCardProps extends HTMLAttributes<HTMLDivElement> {
  /** The big number or main value to display */
  value: string | number;
  /** Descriptive label below the value */
  label: string;
  /** Optional subtitle / helper text in muted */
  subtitle?: string;
  /** Optional icon or element rendered above the value */
  icon?: ReactNode;
}

const StatCard = forwardRef<HTMLDivElement, StatCardProps>(
  ({ value, label, subtitle, icon, className = '', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`bg-white border-[3px] border-base shadow-solid-md hover:-translate-y-1 hover:shadow-solid-lg rounded-none transition-all duration-150 p-6 ${className}`}
        {...props}
      >
        {icon && (
          <div className="mb-3 text-base">
            {icon}
          </div>
        )}
        <div className="text-5xl font-black text-base leading-none">
          {value}
        </div>
        <div className="mt-2 font-black uppercase tracking-widest text-xs text-base">
          {label}
        </div>
        {(subtitle || children) && (
          <div className="mt-1 text-sm text-muted">
            {subtitle}
            {children}
          </div>
        )}
      </div>
    );
  }
);

StatCard.displayName = 'StatCard';

export default StatCard;
