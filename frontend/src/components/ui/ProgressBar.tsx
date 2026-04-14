'use client';

import { forwardRef, HTMLAttributes } from 'react';

/* ----------------------------------------------------------------
   ProgressBar — Segmented 6-Step Stepper
   - 6 segments representing pipeline steps
   - Filled segments: bg-base (completed) or bg-accent (current)
   - Current step: accent color with sharp-blink animation
   - Failed step: error color
   - Pending segments: panel bg with border
   ---------------------------------------------------------------- */

export type StepStatus = 'completed' | 'current' | 'failed' | 'pending';

export interface ProgressBarStep {
  /** Display label for this step */
  label: string;
  /** Current status of this step */
  status: StepStatus;
}

interface ProgressBarProps extends HTMLAttributes<HTMLDivElement> {
  /** The 6 steps to display */
  steps: ProgressBarStep[];
  /** Optional title displayed above the bar */
  title?: string;
}

const stepStatusClasses: Record<StepStatus, string> = {
  completed: 'bg-base',
  current: 'bg-accent animate-sharp-blink',
  failed: 'bg-error',
  pending: 'bg-panel border-[2px] border-base',
};

const stepLabelClasses: Record<StepStatus, string> = {
  completed: 'text-base',
  current: 'text-accent',
  failed: 'text-error',
  pending: 'text-muted',
};

const ProgressBar = forwardRef<HTMLDivElement, ProgressBarProps>(
  ({ steps, title, className = '', ...props }, ref) => {
    return (
      <div ref={ref} className={`w-full ${className}`} {...props}>
        {title && (
          <p className="font-black uppercase tracking-widest text-xs text-base mb-3">
            {title}
          </p>
        )}
        <div className="flex gap-1">
          {steps.map((step, index) => (
            <div key={index} className="flex-1 flex flex-col gap-1.5">
              {/* Segment bar */}
              <div
                className={`h-3 rounded-none transition-colors duration-150 ${stepStatusClasses[step.status]}`}
                aria-label={`Step ${index + 1}: ${step.label} — ${step.status}`}
              />
              {/* Step label */}
              <span
                className={`font-black uppercase tracking-widest text-[9px] leading-tight text-center ${stepLabelClasses[step.status]}`}
              >
                {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
);

ProgressBar.displayName = 'ProgressBar';

export default ProgressBar;
