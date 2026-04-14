'use client';

import { useState } from 'react';
import { PageHeader } from '@/components/layout';
import Button from '@/components/ui/Button';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
} from '@/components/ui/Table';
import CredentialRow from '@/components/credentials/CredentialRow';
import AddCredentialModal from '@/components/credentials/AddCredentialModal';
import { useCredentials } from '@/hooks/useCredentials';
import type { Credential, CredentialCreate } from '@/lib/types';

export default function CredentialsPage() {
  const { credentials, isLoading, createCredential } = useCredentials();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCredential, setEditingCredential] = useState<Credential | null>(null);

  const handleRowClick = (credential: Credential) => {
    setEditingCredential(credential);
    setIsModalOpen(true);
  };

  const handleAddClick = () => {
    setEditingCredential(null);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingCredential(null);
  };

  const handleSubmit = async (data: CredentialCreate) => {
    await createCredential(data);
  };

  const handleRegenerateAll = () => {
    // Opens the modal for batch regeneration context
    setEditingCredential(null);
    setIsModalOpen(true);
  };

  return (
    <div>
      <PageHeader title="Credentials">
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={handleRegenerateAll}>
            Regenerate All
          </Button>
          <Button variant="primary" onClick={handleAddClick}>
            + Add Credential
          </Button>
        </div>
      </PageHeader>

      <div className="p-8">
        {/* Credentials Table inside bordered card */}
        <div className="bg-white border-[3px] border-base shadow-solid-md overflow-hidden rounded-none">
          {isLoading ? (
            <div className="p-12 text-center">
              <div className="inline-block w-8 h-8 border-[3px] border-base border-t-transparent animate-spin rounded-none" />
              <p className="mt-4 text-muted font-bold uppercase tracking-widest text-sm">
                Loading credentials...
              </p>
            </div>
          ) : credentials.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Provider</TableHeaderCell>
                  <TableHeaderCell>Key Type</TableHeaderCell>
                  <TableHeaderCell>Secret</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Last Updated</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {credentials.map((credential) => (
                  <CredentialRow
                    key={credential.id}
                    credential={credential}
                    onClick={handleRowClick}
                  />
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="p-12 text-center">
              <p className="text-muted font-black uppercase tracking-widest text-lg">
                No Credentials Configured
              </p>
              <p className="text-muted font-bold text-sm mt-2">
                Add your first API key to get started.
              </p>
            </div>
          )}
        </div>

        {/* Yellow alert box with security notice */}
        <div className="mt-6 bg-accent border-[3px] border-base p-6 rounded-none">
          <div className="flex items-start gap-3">
            <span className="text-xl leading-none flex-shrink-0 mt-0.5">⚠</span>
            <div>
              <h3 className="font-black uppercase tracking-widest text-sm text-base">
                Security Notice
              </h3>
              <p className="text-sm font-bold text-base mt-1">
                API keys and secrets are stored encrypted and never returned in full by the API.
                All values are masked as •••••••• for security. If you need to update a credential,
                click on its row to enter a new value. The previous value will be permanently replaced.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Add/Edit Credential Modal */}
      <AddCredentialModal
        credential={editingCredential}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
