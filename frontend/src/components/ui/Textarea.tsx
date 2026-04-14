'use client';

import { TextareaHTMLAttributes, forwardRef } from 'react';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className = '', id, ...props }, ref) => {
    const textareaId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={textareaId}
            className="block font-black uppercase tracking-widest text-xs text-base mb-2"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={`w-full border-[3px] border-base p-4 font-bold outline-none rounded-none bg-white resize-y transition-colors placeholder:text-muted ${
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

Textarea.displayName = 'Textarea';

export default Textarea;
