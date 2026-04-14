'use client';

import { forwardRef, HTMLAttributes, useEffect, useState } from 'react';

/* ----------------------------------------------------------------
   ProgressRing — SVG Circle Progress Indicator
   - SVG circle with stroke-dasharray/dashoffset for percentage
   - Centered number showing the percentage
   - Smooth animation of stroke-dashoffset with progress
   ---------------------------------------------------------------- */

interface ProgressRingProps extends HTMLAttributes<HTMLDivElement> {
  /** Progress percentage (0–100) */
  progress: number;
  /** Diameter of the ring in pixels (default 80) */
  size?: number;
  /** Stroke width in pixels (default 8) */
  strokeWidth?: number;
  /** Optional label displayed below the ring */
  label?: string;
}

const ProgressRing = forwardRef<HTMLDivElement, ProgressRingProps>(
  ({ progress, size = 80, strokeWidth = 8, label, className = '', ...props }, ref) => {
    const [animatedProgress, setAnimatedProgress] = useState(0);
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const dashoffset = circumference - (animatedProgress / 100) * circumference;

    // Clamp progress to 0-100
    const clampedProgress = Math.max(0, Math.min(100, progress));

    useEffect(() => {
      setAnimatedProgress(clampedProgress);
    }, [clampedProgress]);

    return (
      <div ref={ref} className={`inline-flex flex-col items-center gap-2 ${className}`} {...props}>
        <div className="relative" style={{ width: size, height: size }}>
          <svg
            width={size}
            height={size}
            viewBox={`0 0 ${size} ${size}`}
            className="transform -rotate-90"
          >
            {/* Background track */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="#000000"
              strokeWidth={strokeWidth}
            />
            {/* Progress arc */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="#ffcc00"
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={dashoffset}
              strokeLinecap="butt"
              style={{ transition: 'stroke-dashoffset 0.5s ease-in-out' }}
            />
          </svg>
          {/* Centered percentage number */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-black text-base text-lg tabular-nums">
              {Math.round(animatedProgress)}%
            </span>
          </div>
        </div>
        {label && (
          <span className="font-black uppercase tracking-widest text-xs text-base">
            {label}
          </span>
        )}
      </div>
    );
  }
);

ProgressRing.displayName = 'ProgressRing';

export default ProgressRing;
