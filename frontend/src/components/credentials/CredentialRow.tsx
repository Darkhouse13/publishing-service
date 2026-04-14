'use client';

import Badge from '@/components/ui/Badge';
import { TableCell, TableRow } from '@/components/ui/Table';
import type { Credential } from '@/lib/types';
import { formatDate } from '@/lib/utils';

interface CredentialRowProps {
  credential: Credential;
  onClick: (credential: Credential) => void;
}

export default function CredentialRow({ credential, onClick }: CredentialRowProps) {
  const isConfigured = true; // If it exists in the list, it's configured

  return (
    <TableRow
      className="cursor-pointer hover:bg-panel/50 transition-colors"
      onClick={() => onClick(credential)}
    >
      <TableCell className="font-black uppercase tracking-wider text-base">
        {credential.provider}
      </TableCell>
      <TableCell className="text-muted">
        {credential.key_name}
      </TableCell>
      <TableCell>
        <span className="tracking-widest text-base select-none">
          ••••••••
        </span>
      </TableCell>
      <TableCell>
        <Badge
          variant={isConfigured ? 'configured' : 'missing'}
          label={isConfigured ? 'Configured' : 'Missing'}
        />
      </TableCell>
      <TableCell className="text-muted text-xs">
        {formatDate(credential.updated_at)}
      </TableCell>
    </TableRow>
  );
}
