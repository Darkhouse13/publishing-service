'use client';

import { useCallback } from 'react';
import useSWR from 'swr';
import { credentialsApi } from '@/lib/api';
import type { Credential, CredentialCreate } from '@/lib/types';
import { mockCredentials } from '@/lib/mock-data';

export function useCredentials(fallback?: Credential[]) {
  const { data, error, isLoading, mutate } = useSWR<Credential[]>(
    '/credentials',
    () => credentialsApi.list(),
    {
      fallbackData: fallback ?? mockCredentials,
      revalidateOnFocus: false,
    },
  );

  const createCredential = useCallback(
    async (credentialData: CredentialCreate) => {
      const newCredential = await credentialsApi.create(credentialData);
      await mutate((current) => [...(current ?? []), newCredential], false);
      return newCredential;
    },
    [mutate],
  );

  const deleteCredential = useCallback(
    async (id: string) => {
      // Optimistic update
      await mutate(
        (current) => current?.filter((c) => c.id !== id),
        false,
      );

      try {
        await credentialsApi.delete(id);
      } catch {
        // Revert on error
        await mutate();
      }
    },
    [mutate],
  );

  return {
    credentials: data ?? [],
    error,
    isLoading,
    mutate,
    createCredential,
    deleteCredential,
  };
}
