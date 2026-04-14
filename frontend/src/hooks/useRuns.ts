'use client';

import { useCallback } from 'react';
import useSWR from 'swr';
import { runsApi } from '@/lib/api';
import type { Run, RunCreate } from '@/lib/types';
import { mockRuns } from '@/lib/mock-data';

const ACTIVE_STATUSES: Set<string> = new Set(['generating', 'running', 'pending']);

export function useRuns(fallback?: Run[]) {
  const { data, error, isLoading, mutate } = useSWR<Run[]>(
    '/runs',
    () => runsApi.list(),
    {
      fallbackData: fallback ?? mockRuns,
      revalidateOnFocus: false,
      refreshInterval: 3000,
    },
  );

  const runs = data ?? [];
  const hasActiveRuns = runs.some((run) => ACTIVE_STATUSES.has(run.status));

  const createRun = useCallback(
    async (runData: RunCreate) => {
      const newRun = await runsApi.create(runData);
      await mutate((current) => [...(current ?? []), newRun], false);
      return newRun;
    },
    [mutate],
  );

  return {
    runs,
    error,
    isLoading,
    mutate,
    hasActiveRuns,
    createRun,
  };
}

export function useRun(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Run>(
    id ? `/runs/${id}` : null,
    () => (id ? runsApi.get(id) : Promise.resolve(null as unknown as Run)),
    {
      revalidateOnFocus: false,
      refreshInterval: 3000,
    },
  );

  const isActive = data != null && ACTIVE_STATUSES.has(data.status);

  return {
    run: data,
    error,
    isLoading,
    mutate,
    isActive,
  };
}
