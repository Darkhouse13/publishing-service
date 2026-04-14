'use client';

import useSWR from 'swr';

/**
 * Generic polling hook that revalidates a key at a fixed interval
 * when `shouldPoll` is true. Stops polling when false.
 */
export function usePolling<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  shouldPoll: boolean,
  interval: number = 3000,
) {
  const { data, error, isLoading, mutate } = useSWR<T>(
    key,
    fetcher,
    {
      refreshInterval: shouldPoll ? interval : 0,
      revalidateOnFocus: false,
    },
  );

  return {
    data,
    error,
    isLoading,
    mutate,
  };
}
