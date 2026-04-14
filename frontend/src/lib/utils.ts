// ---------------------------------------------------------------------------
// Formatting helpers — dates, numbers, and display utilities
// ---------------------------------------------------------------------------

/**
 * Format an ISO date string as a human-readable date.
 * Example: "Jan 15, 2026"
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Format an ISO date string as a human-readable date + time.
 * Example: "Jan 15, 2026, 3:45 PM"
 */
export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format a number with commas for thousands separators.
 * Example: 12345 → "12,345"
 */
export function formatNumber(value: number | null | undefined): string {
  if (value == null) return '0';
  return value.toLocaleString('en-US');
}

/**
 * Format a relative time string from an ISO date string.
 * Examples: "2 minutes ago", "3 hours ago", "Jan 15, 2026"
 */
export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '—';

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return 'just now';
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
  }
  if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
  }
  if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  }

  // Fall back to absolute date for older timestamps
  return formatDate(dateString);
}

/**
 * Format a duration in seconds as a human-readable string.
 * Example: 3665 → "1h 1m 5s"
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '—';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

/**
 * Calculate duration between two ISO date strings in seconds.
 * If `end` is null, uses current time.
 */
export function calculateDurationSeconds(
  start: string | null | undefined,
  end: string | null | undefined
): number | null {
  if (!start) return null;
  const startDate = new Date(start);
  const endDate = end ? new Date(end) : new Date();
  return Math.max(0, Math.floor((endDate.getTime() - startDate.getTime()) / 1000));
}

/**
 * Mask a secret value for display.
 * Always returns "••••••••" regardless of input length.
 */
export function maskSecret(_value: string | null | undefined): string {
  return '••••••••';
}

/**
 * Capitalize the first letter of a string.
 */
export function capitalize(str: string): string {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Truncate a string to a maximum length, appending "..." if truncated.
 */
export function truncate(str: string, maxLength: number): string {
  if (!str || str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + '...';
}

/**
 * Format a percentage value for display.
 * Example: 0.856 → "85.6%"
 */
export function formatPercentage(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}
