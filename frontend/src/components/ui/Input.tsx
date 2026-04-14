'use client';

import { InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block font-black uppercase tracking-widest text-xs text-base mb-2"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`w-full border-[3px] border-base p-4 font-bold outline-none rounded-none bg-white transition-colors placeholder:text-muted ${
            error
              ? 'border-error text-error focus:bg-error/10'
              : 'focus:bg-accent/10'
          } ${className}`}
          {...props}
        />
        {error && (
          <p className="mt-1 text-xs font-bold text-error uppercase tracking-widest">
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export default Input;
