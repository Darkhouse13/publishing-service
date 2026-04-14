import { HTMLAttributes, forwardRef } from 'react';

/* ----------------------------------------------------------------
   LiveDot — Neo-Brutalist Blinking Square Indicator
   - 8x8 square with accent (#ffcc00) background
   - Uses sharp-blink animation (1.5s steps)
   - Zero border-radius
   - Used to indicate active/live states (e.g., running runs)
   ---------------------------------------------------------------- */

interface LiveDotProps extends HTMLAttributes<HTMLSpanElement> {
  /** Whether the dot is active/blinking. Defaults to true */
  active?: boolean;
  /** Custom size in pixels. Defaults to 8 */
  size?: number;
}

const LiveDot = forwardRef<HTMLSpanElement, LiveDotProps>(
  ({ active = true, size = 8, className = '', ...props }, ref) => {
    if (!active) return null;

    return (
      <span
        ref={ref}
        className={`inline-block bg-accent rounded-none animate-sharp-blink ${className}`}
        style={{ width: `${size}px`, height: `${size}px` }}
        {...props}
      />
    );
  }
);

LiveDot.displayName = 'LiveDot';

export default LiveDot;
