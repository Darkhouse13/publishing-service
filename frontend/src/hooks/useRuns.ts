'use client';

import useSWR from 'swr';
import { runsApi } from '@/lib/api';
import type { Run } from '@/lib/types';
import { mockRuns } from '@/lib/mock-data';

export function useRuns(fallback?: Run[]) {
  const { data, error, isLoading, mutate } = useSWR<Run[]>(
    '/runs',
    () => runsApi.list(),
    {
      fallbackData: fallback ?? mockRuns,
      revalidateOnFocus: false,
    }
  );

  const hasActiveRuns = (data ?? []).some(
    (run) => run.status === 'generating' || run.status === 'running' || run.status === 'pending'
  );

  return {
    runs: data ?? [],
    error,
    isLoading,
    mutate,
    hasActiveRuns,
  };
}

export function useRun(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Run>(
    id ? `/runs/${id}` : null,
    () => (id ? runsApi.get(id) : Promise.resolve(null as unknown as Run)),
    {
      revalidateOnFocus: false,
    }
  );

  return {
    run: data,
    error,
    isLoading,
    mutate,
  };
}
