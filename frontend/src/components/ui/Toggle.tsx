'use client';

import { forwardRef, InputHTMLAttributes } from 'react';

/* ----------------------------------------------------------------
   Toggle — Neo-Brutalist On/Off Switch
   - w-12 h-6 track with 3px border
   - Accent background when on
   - Smooth transition for knob and background
   ---------------------------------------------------------------- */

interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  /** Whether the toggle is on */
  checked?: boolean;
  /** Called when toggle state changes */
  onCheckedChange?: (checked: boolean) => void;
  /** Optional label displayed above the toggle */
  label?: string;
}

const Toggle = forwardRef<HTMLInputElement, ToggleProps>(
  ({ checked = false, onCheckedChange, label, className = '', id, disabled, ...props }, ref) => {
    const toggleId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className={`inline-flex flex-col gap-2 ${className}`}>
        {label && (
          <label
            htmlFor={toggleId}
            className="block font-black uppercase tracking-widest text-xs text-base"
          >
            {label}
          </label>
        )}
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={disabled}
          id={toggleId}
          ref={ref as React.Ref<HTMLButtonElement>}
          onClick={() => onCheckedChange?.(!checked)}
          className={`
            relative inline-flex items-center
            w-12 h-6
            border-[3px] border-base
            rounded-none
            transition-colors duration-150
            focus:outline-none
            ${checked ? 'bg-accent' : 'bg-white'}
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
          {...(props as React.ButtonHTMLAttributes<HTMLButtonElement>)}
        >
          <span
            className={`
              block
              w-4 h-4
              bg-base
              rounded-none
              transition-transform duration-150
              ${checked ? 'translate-x-[22px]' : 'translate-x-[2px]'}
            `}
          />
        </button>
      </div>
    );
  }
);

Toggle.displayName = 'Toggle';

export default Toggle;
